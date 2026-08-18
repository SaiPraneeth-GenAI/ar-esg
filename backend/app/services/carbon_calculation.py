"""GHG calculation engine (Prompt 4). Pure functions for unit
normalization and formula execution; a thin DB-touching layer for factor
resolution and persistence. Every number that ends up in an
EmissionCalculation row is Decimal end to end -- rule #1 in Prompt 4 bans
binary floating point for factors/activity/conversion/emissions, so this
module never does float arithmetic on those values, even though the
existing EmissionFactor/IpccReference/Entry columns are mapped as Python
float (see to_decimal() below -- always routed through str() first so a
float's binary representation never leaks into the Decimal).
"""

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy import update as sa_update
from sqlalchemy.orm import Session

from app.core.carbon_mapping import CarbonSourceMapping, get_carbon_mapping
from app.db.models import DataPoint, EmissionCalculation, EmissionFactor, Entry, IpccReference, ProductionVolumeMapping, RevenueMapping

class _Unset:
    """Sentinel distinguishing "no existing calc was passed in, query for
    it" (calculate_entry) from "the caller already checked, there genuinely
    isn't one" (calculate_entries_batch) -- None is a valid value in the
    second case, so it can't double as the sentinel."""


_UNSET = _Unset()

UNRESOLVED_REASONS = {
    "missing_factor": "No approved factor found for this substance/scope/period.",
    "ambiguous_factor": "More than one approved factor matches -- resolve the duplicate before this can calculate.",
    "unit_mismatch": "Activity unit does not match the factor's unit, and no documented conversion applies.",
    "not_approved": "Entry is not in Approved status.",
    "missing_value": "Entry has no recorded value.",
    "unknown_source_type": "No calculation handler for this source type.",
}


def to_decimal(value) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


# ---- Unit normalization (pure) ---------------------------------------------


@dataclass
class UnresolvedResult:
    reason_code: str
    reason_detail: str

    def as_reason(self) -> str:
        return f"{self.reason_code}: {self.reason_detail}"


TONNE_BASIS_SUFFIXES = ("/t", "/tonne", "/tonnes", "/mt")


def normalize_fuel_activity(
    activity_value: Decimal, activity_unit: str, factor_unit: str, density_kg_per_unit: Decimal | None
) -> tuple[Decimal, str] | UnresolvedResult:
    """Fuel factors are expressed per litre or per kg. Converts only when a
    documented density is on file (rule #8) -- never assumes kg == litre."""
    factor_unit_l = factor_unit.lower().replace(" ", "")
    if "litre" in factor_unit_l or "/l" in factor_unit_l:
        factor_basis = "litre"
    elif factor_unit_l.startswith("tco2e") and factor_unit_l.endswith(TONNE_BASIS_SUFFIXES):
        # Solid fuels (coal, biomass, ...) are conventionally factored as
        # tCO2e per tonne, e.g. IPCC/GHG Protocol coal factors -- since
        # both sides of that ratio are scaled by the same 1000x versus
        # kgCO2e/kg, the factor_value carries over unchanged, not just the
        # basis label. Only "tCO2e/t" qualifies for this: a "kgCO2e/t"
        # factor is a genuinely different scale and stays unresolved
        # rather than silently treated as identical.
        factor_basis = "kg"
    elif "kg" in factor_unit_l:
        factor_basis = "kg"
    else:
        return UnresolvedResult("unit_mismatch", f"Could not determine the factor's unit basis from '{factor_unit}'.")

    activity_unit_l = activity_unit.strip().lower()
    if activity_unit_l in ("litre", "litres", "l"):
        entry_basis = "litre"
    elif activity_unit_l == "kg":
        entry_basis = "kg"
    else:
        return UnresolvedResult("unit_mismatch", f"Activity unit '{activity_unit}' is not litres or kg.")

    if entry_basis == factor_basis:
        return activity_value, factor_basis

    if density_kg_per_unit is None:
        return UnresolvedResult(
            "unit_mismatch",
            f"Entry is recorded in {entry_basis}, the factor is per {factor_basis}, and no density conversion is on file.",
        )

    if entry_basis == "kg" and factor_basis == "litre":
        return activity_value / density_kg_per_unit, "litre"
    if entry_basis == "litre" and factor_basis == "kg":
        return activity_value * density_kg_per_unit, "kg"

    return UnresolvedResult("unit_mismatch", "Unsupported unit combination.")


def normalize_grid_activity(activity_value: Decimal, activity_unit: str) -> tuple[Decimal, str] | UnresolvedResult:
    unit = activity_unit.strip().lower()
    if unit == "kwh":
        return activity_value / Decimal("1000"), "MWh"
    if unit == "mwh":
        return activity_value, "MWh"
    return UnresolvedResult("unit_mismatch", f"Grid electricity activity unit '{activity_unit}' is not kWh or MWh.")


def normalize_gwp_activity(activity_value: Decimal, activity_unit: str) -> tuple[Decimal, str] | UnresolvedResult:
    if activity_unit.strip().lower() == "kg":
        return activity_value, "kg"
    return UnresolvedResult("unit_mismatch", f"Refrigerant leakage activity unit '{activity_unit}' is not kg.")


# ---- Formula execution (pure) ----------------------------------------------


def compute_fuel_emissions(normalized_value: Decimal, factor_value: Decimal, normalized_unit: str) -> tuple[Decimal, str]:
    kgco2e = normalized_value * factor_value
    return kgco2e, f"{normalized_value} {normalized_unit} x {factor_value} kgCO2e/{normalized_unit} = {kgco2e} kgCO2e"


def compute_gwp_emissions(normalized_value: Decimal, gwp_value: Decimal) -> tuple[Decimal, str]:
    kgco2e = normalized_value * gwp_value
    return kgco2e, f"{normalized_value} kg x {gwp_value} (GWP-100) = {kgco2e} kgCO2e"


def compute_grid_emissions(normalized_mwh: Decimal, factor_t_per_mwh: Decimal) -> tuple[Decimal, str]:
    tco2e = normalized_mwh * factor_t_per_mwh
    kgco2e = tco2e * Decimal("1000")
    return kgco2e, f"{normalized_mwh} MWh x {factor_t_per_mwh} tCO2e/MWh = {tco2e} tCO2e = {kgco2e} kgCO2e"


# ---- Factor resolution (DB read, deterministic precedence) ----------------


@dataclass
class ResolvedFactor:
    factor_id: uuid.UUID | None
    ipcc_reference_id: uuid.UUID | None
    version: str
    value: Decimal
    unit: str
    source: str
    effective_year: int


def _tenant_factor_matches(factor: EmissionFactor, mapping: CarbonSourceMapping) -> bool:
    if mapping.source_type == "grid_electricity":
        return factor.method == "location-based"
    return (factor.gas_type or "").strip().lower() == mapping.ipcc_substance.strip().lower()


def resolve_factor(
    db: Session, tenant_id: uuid.UUID, mapping: CarbonSourceMapping, period: date
) -> ResolvedFactor | UnresolvedResult:
    """Precedence (rule #3): tenant-specific approved factor first, then
    the seeded reference factor. Within each source, the version whose
    effective_year is the latest one at-or-before the activity's period
    wins -- the factor that was actually in force when the activity
    happened. More than one factor tied at that same effective_year is
    ambiguous, not a coin flip."""
    period_year = period.year

    tenant_candidates = (
        db.query(EmissionFactor)
        .filter(
            EmissionFactor.tenant_id == tenant_id,
            EmissionFactor.scope == mapping.scope,
            EmissionFactor.is_active.is_(True),
            EmissionFactor.effective_date <= period,
        )
        .all()
    )
    tenant_matches = [f for f in tenant_candidates if _tenant_factor_matches(f, mapping)]

    if tenant_matches:
        best_year = max(f.effective_date.year for f in tenant_matches)
        at_best_year = [f for f in tenant_matches if f.effective_date.year == best_year]
        if len(at_best_year) > 1:
            return UnresolvedResult(
                "ambiguous_factor",
                f"{len(at_best_year)} active tenant factors match {mapping.ipcc_substance} at effective year {best_year}.",
            )
        f = at_best_year[0]
        return ResolvedFactor(
            factor_id=f.id,
            ipcc_reference_id=None,
            version=f.version,
            value=to_decimal(f.factor_value),
            unit=f.unit,
            source=f.source_reference or f.source or "Tenant factor",
            effective_year=f.effective_date.year,
        )

    ref_candidates = (
        db.query(IpccReference)
        .filter(
            IpccReference.scope == mapping.scope,
            IpccReference.substance_name == mapping.ipcc_substance,
            IpccReference.effective_year <= period_year,
        )
        .all()
    )
    if not ref_candidates:
        return UnresolvedResult(
            "missing_factor",
            f"No tenant or reference factor found for {mapping.ipcc_substance} (scope {mapping.scope}) at or before {period_year}.",
        )

    best_year = max(r.effective_year for r in ref_candidates)
    at_best_year = [r for r in ref_candidates if r.effective_year == best_year]
    if len(at_best_year) > 1:
        return UnresolvedResult(
            "ambiguous_factor",
            f"{len(at_best_year)} reference factors match {mapping.ipcc_substance} at effective year {best_year}.",
        )
    r = at_best_year[0]
    return ResolvedFactor(
        factor_id=None,
        ipcc_reference_id=r.id,
        version=r.publication,
        value=to_decimal(r.derived_factor_value),
        unit=r.unit,
        source=r.source_reference,
        effective_year=r.effective_year,
    )


# ---- Orchestration ----------------------------------------------------------


@dataclass
class CalculationOutcome:
    status: str  # calculated | unresolved
    scope: int
    calculation_method: str | None = None
    normalized_activity_value: Decimal | None = None
    normalized_activity_unit: str | None = None
    resolved: ResolvedFactor | None = None
    emissions_kgco2e: Decimal | None = None
    formula: str | None = None
    resolution_reason: str | None = None


def run_calculation(
    db: Session, tenant_id: uuid.UUID, mapping: CarbonSourceMapping, activity_value: Decimal, activity_unit: str, period: date
) -> CalculationOutcome:
    """DB-read-only: resolves a factor and executes the formula. No writes
    -- shared by both the persisting calculate/recalculate path and the
    read-only draft preview."""
    resolved = resolve_factor(db, tenant_id, mapping, period)
    if isinstance(resolved, UnresolvedResult):
        return CalculationOutcome(status="unresolved", scope=mapping.scope, resolution_reason=resolved.as_reason())

    density = None
    if mapping.source_type == "fuel" and resolved.ipcc_reference_id:
        ref = db.get(IpccReference, resolved.ipcc_reference_id)
        if ref is not None and ref.density_kg_per_unit is not None:
            density = to_decimal(ref.density_kg_per_unit)

    if mapping.source_type == "fuel":
        norm = normalize_fuel_activity(activity_value, activity_unit, resolved.unit, density)
    elif mapping.source_type == "gwp":
        norm = normalize_gwp_activity(activity_value, activity_unit)
    elif mapping.source_type == "grid_electricity":
        norm = normalize_grid_activity(activity_value, activity_unit)
    else:
        return CalculationOutcome(status="unresolved", scope=mapping.scope, resolution_reason=UNRESOLVED_REASONS["unknown_source_type"])

    if isinstance(norm, UnresolvedResult):
        return CalculationOutcome(status="unresolved", scope=mapping.scope, resolution_reason=norm.as_reason())

    normalized_value, normalized_unit = norm
    calculation_method = "location_based" if mapping.source_type == "grid_electricity" else None

    if mapping.source_type == "fuel":
        kgco2e, formula = compute_fuel_emissions(normalized_value, resolved.value, normalized_unit)
    elif mapping.source_type == "gwp":
        kgco2e, formula = compute_gwp_emissions(normalized_value, resolved.value)
    else:
        kgco2e, formula = compute_grid_emissions(normalized_value, resolved.value)

    return CalculationOutcome(
        status="calculated",
        scope=mapping.scope,
        calculation_method=calculation_method,
        normalized_activity_value=normalized_value,
        normalized_activity_unit=normalized_unit,
        resolved=resolved,
        emissions_kgco2e=kgco2e,
        formula=formula,
    )


def build_calculation_row(
    db: Session,
    entry: Entry,
    dp: DataPoint,
    tenant_id: uuid.UUID,
    calculated_by: uuid.UUID | None,
    existing: "EmissionCalculation | None | _Unset" = _UNSET,
) -> EmissionCalculation | None:
    """Builds (via db.add, not committed) the EmissionCalculation row for
    one entry, superseding whatever was previously current for it. Returns
    None -- writes nothing -- when the data point isn't a mapped GHG
    source at all (Water/Waste/etc stay out of the queue entirely, not
    flagged as perpetually "unresolved").

    `existing` lets a batch caller (calculate_entries_batch) pass in a
    pre-fetched supersede target instead of this function querying for it
    -- the single-entry caller (calculate_entry) leaves it unset and gets
    the query run here, same as before."""
    mapping = get_carbon_mapping(dp.name)
    if mapping is None:
        return None

    if entry.status != "Approved":
        outcome = CalculationOutcome(status="unresolved", scope=mapping.scope, resolution_reason=UNRESOLVED_REASONS["not_approved"])
    elif entry.value is None:
        outcome = CalculationOutcome(status="unresolved", scope=mapping.scope, resolution_reason=UNRESOLVED_REASONS["missing_value"])
    else:
        outcome = run_calculation(db, tenant_id, mapping, to_decimal(entry.value), dp.unit or "", entry.period)

    if existing is _UNSET:
        existing = (
            db.query(EmissionCalculation)
            .filter(EmissionCalculation.entry_id == entry.id, EmissionCalculation.status.in_(["calculated", "unresolved"]))
            .first()
        )
        # Only the single-entry caller reaches here (calculate_entries_batch
        # always passes existing explicitly) -- add immediately, same as
        # this function always did before batching existed.
        add_immediately = True
    else:
        add_immediately = False

    resolved = outcome.resolved
    calc = EmissionCalculation(
        # Generated here instead of left to the server-side default so a
        # caller that batches many of these (calculate_entries_batch) can
        # bulk_save_objects() them -- which skips fetching generated ids
        # back per row -- while still knowing each row's id immediately.
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        location_id=entry.location_id,
        entry_id=entry.id,
        data_point_id=entry.data_point_id,
        reporting_period=entry.period,
        scope=outcome.scope,
        calculation_method=outcome.calculation_method,
        status=outcome.status,
        activity_value=to_decimal(entry.value) if entry.value is not None else Decimal("0"),
        activity_unit=dp.unit or "",
        normalized_activity_value=outcome.normalized_activity_value,
        normalized_activity_unit=outcome.normalized_activity_unit,
        factor_id=resolved.factor_id if resolved else None,
        ipcc_reference_id=resolved.ipcc_reference_id if resolved else None,
        factor_version=resolved.version if resolved else None,
        factor_value=resolved.value if resolved else None,
        factor_unit=resolved.unit if resolved else None,
        factor_source=resolved.source if resolved else None,
        factor_effective_year=resolved.effective_year if resolved else None,
        emissions_kgco2e=outcome.emissions_kgco2e,
        formula=outcome.formula,
        resolution_reason=outcome.resolution_reason,
        calculated_by=calculated_by,
        supersedes_calculation_id=existing.id if existing else None,
    )
    if add_immediately:
        db.add(calc)
        if existing is not None:
            existing.status = "superseded"
    return calc


def calculate_entry(db: Session, entry: Entry, tenant_id: uuid.UUID, calculated_by: uuid.UUID | None) -> EmissionCalculation | None:
    """Single-entry entry point (e.g. the approval hook). Caller commits."""
    dp = db.get(DataPoint, entry.data_point_id)
    return build_calculation_row(db, entry, dp, tenant_id, calculated_by)


def calculate_entries_batch(
    db: Session, entries: list[Entry], tenant_id: uuid.UUID, calculated_by: uuid.UUID | None
) -> list[tuple[Entry, EmissionCalculation | None]]:
    """Batch entry point for a period/queue recalculation -- every row is
    added to the same session without an intermediate commit, so the
    caller can commit once (rule: bounded transaction, not per-entry).

    dp_cache is an explicit dict, not a bare reliance on SQLAlchemy's
    db.get() -- its identity map holds instances by weak reference, so
    without something keeping a real (strong) reference across loop
    iterations, the garbage collector can reclaim a "cached" row between
    entries and silently turn every repeat lookup back into a fresh query.
    Same reasoning for pre-fetching every existing EmissionCalculation to
    supersede in one query instead of one per entry."""
    if not entries:
        return []

    dps = {dp.id: dp for dp in db.query(DataPoint).filter(DataPoint.id.in_({e.data_point_id for e in entries})).all()}
    existing_by_entry = {
        ec.entry_id: ec
        for ec in db.query(EmissionCalculation)
        .filter(
            EmissionCalculation.entry_id.in_([e.id for e in entries]),
            EmissionCalculation.status.in_(["calculated", "unresolved"]),
        )
        .all()
    }

    results: list[tuple[Entry, EmissionCalculation | None]] = []
    new_calcs: list[EmissionCalculation] = []
    superseded_ids: list[uuid.UUID] = []
    for entry in entries:
        dp = dps.get(entry.data_point_id)
        existing = existing_by_entry.get(entry.id)
        calc = build_calculation_row(db, entry, dp, tenant_id, calculated_by, existing)
        results.append((entry, calc))
        if calc is not None:
            new_calcs.append(calc)
            if existing is not None:
                superseded_ids.append(existing.id)

    # bulk_save_objects()/a single UPDATE...IN instead of session.add() and
    # attribute mutation per row -- session.add() in a loop measured at
    # 133s for 2550 rows elsewhere in this codebase (same unit-of-work
    # flush cost applies here to EmissionCalculation inserts and the
    # existing-row supersede update).
    if new_calcs:
        db.bulk_save_objects(new_calcs)
    if superseded_ids:
        db.execute(sa_update(EmissionCalculation).where(EmissionCalculation.id.in_(superseded_ids)).values(status="superseded"))

    return results


# ---- Period rollups (shared by the dashboard overview and target baselines) -


def prior_month(d: date) -> date:
    if d.month == 1:
        return d.replace(year=d.year - 1, month=12)
    return d.replace(month=d.month - 1)


def prior_year(d: date) -> date:
    return d.replace(year=d.year - 1)


def shift_months(d: date, delta: int) -> date:
    """d, moved by delta calendar months (either direction), clamped to the
    1st -- the single place every range-mode date arithmetic in this module
    goes through, so "3 months back" always means the same thing."""
    total = d.year * 12 + (d.month - 1) + delta
    return date(total // 12, total % 12 + 1, 1)


def months_in_range(start: date, end: date) -> list[date]:
    months = []
    cursor = start
    while cursor <= end:
        months.append(cursor)
        cursor = shift_months(cursor, 1)
    return months


def range_bounds_for_mode(period: date, mode: str) -> tuple[date, date]:
    """The [start, end] of months a period_mode covers, ending at period.
    'month' is just period itself; 'quarter'/'ytd' are quarter-to-date /
    year-to-date -- the same "bucket start through the selected month"
    shape, differing only in how far back the bucket starts."""
    period = period.replace(day=1)
    if mode == "quarter":
        quarter_start_month = ((period.month - 1) // 3) * 3 + 1
        return period.replace(month=quarter_start_month), period
    if mode == "ytd":
        return period.replace(month=1), period
    return period, period


def prior_range_for_mode(start: date, end: date, mode: str) -> tuple[date, date]:
    """The immediately-preceding range of the same shape -- prior month,
    prior quarter-to-date, or (for ytd, where "immediately preceding" isn't
    meaningful) the same year-to-date range one year back, which is what
    prior_year_range_for_mode also computes."""
    delta = {"quarter": -3, "ytd": -12}.get(mode, -1)
    return shift_months(start, delta), shift_months(end, delta)


def prior_year_range_for_mode(start: date, end: date) -> tuple[date, date]:
    return shift_months(start, -12), shift_months(end, -12)


def trailing_buckets_for_mode(period: date, mode: str, count: int) -> list[tuple[date, date]]:
    """The trailing `count` [start, end] buckets of period_mode's shape,
    ending at the bucket containing period, oldest first. For 'month' this
    is just count trailing single months. For 'quarter'/'ytd', only the
    MOST RECENT bucket (the one matching the live overview's anchor) is
    "to date" -- every earlier bucket is a COMPLETE quarter/year, since a
    trend chart's historical bars should show the finished period, not an
    arbitrarily truncated one to match wherever the anchor happens to sit
    within the current quarter/year. A missing month inside a complete
    bucket still contributes nothing to the sum rather than a fabricated
    number, so requesting the full bucket is always safe."""
    if mode not in ("quarter", "ytd"):
        start, end = range_bounds_for_mode(period, mode)
        buckets: list[tuple[date, date]] = []
        for _ in range(count):
            buckets.append((start, end))
            start, end = shift_months(start, -1), shift_months(end, -1)
        return list(reversed(buckets))

    latest_start, latest_end = range_bounds_for_mode(period, mode)
    step = -3 if mode == "quarter" else -12
    full_width = 2 if mode == "quarter" else 11  # months beyond start for a COMPLETE bucket
    buckets = [(latest_start, latest_end)]
    start = shift_months(latest_start, step)
    for _ in range(count - 1):
        buckets.append((start, shift_months(start, full_width)))
        start = shift_months(start, step)
    return list(reversed(buckets))


def compute_period_totals(db: Session, tenant_id: uuid.UUID, location_id: uuid.UUID | None, period: date) -> dict:
    """Approved-calculation-snapshot totals for one reporting month. Thin
    wrapper over compute_period_totals_batch -- kept as the single-period
    API every existing caller uses, but routed through the batched query
    path so a caller that only needs one period doesn't pay a different
    (worse) query cost than a multi-period caller."""
    return compute_period_totals_batch(db, tenant_id, location_id, [period])[period]


def compute_period_totals_batch(
    db: Session, tenant_id: uuid.UUID, location_id: uuid.UUID | None, periods: list[date]
) -> dict[date, dict]:
    """Same result shape as compute_period_totals, for N periods in 4 fixed
    queries total (not 4*N) -- one EmissionCalculation IN-query, one
    ProductionVolumeMapping lookup, one Entry IN-query, one grouped
    unresolved-count query. Powers both a 6-month trend chart and a
    current/prior-month/prior-year comparison from a single round trip
    each, instead of one HTTP call (and one full query set) per period."""
    if not periods:
        return {}

    q = db.query(EmissionCalculation).filter(
        EmissionCalculation.tenant_id == tenant_id,
        EmissionCalculation.reporting_period.in_(periods),
        EmissionCalculation.status == "calculated",
    )
    if location_id is not None:
        q = q.filter(EmissionCalculation.location_id == location_id)
    rows_by_period: dict[date, list] = {p: [] for p in periods}
    for r in q.all():
        rows_by_period.setdefault(r.reporting_period, []).append(r)

    prod_mapping_q = db.query(ProductionVolumeMapping).filter(
        ProductionVolumeMapping.tenant_id == tenant_id, ProductionVolumeMapping.is_active.is_(True)
    )
    if location_id is not None:
        prod_mapping_q = prod_mapping_q.filter(
            (ProductionVolumeMapping.location_id == location_id) | (ProductionVolumeMapping.location_id.is_(None))
        )
    prod_mapping = prod_mapping_q.first()

    production_by_period: dict[date, float] = {}
    if prod_mapping is not None:
        entry_q = db.query(Entry).filter(
            Entry.data_point_id == prod_mapping.data_point_id, Entry.status == "Approved", Entry.period.in_(periods)
        )
        if location_id is not None:
            entry_q = entry_q.filter(Entry.location_id == location_id)
        entries_by_period: dict[date, list] = {}
        for e in entry_q.all():
            entries_by_period.setdefault(e.period, []).append(e)
        for p, entries in entries_by_period.items():
            total_native = sum((to_decimal(e.value) for e in entries if e.value is not None), Decimal("0"))
            production_by_period[p] = float(total_native * to_decimal(prod_mapping.conversion_multiplier))

    unresolved_q = (
        db.query(EmissionCalculation.reporting_period, func.count(EmissionCalculation.id))
        .filter(
            EmissionCalculation.tenant_id == tenant_id,
            EmissionCalculation.reporting_period.in_(periods),
            EmissionCalculation.status == "unresolved",
        )
    )
    if location_id is not None:
        unresolved_q = unresolved_q.filter(EmissionCalculation.location_id == location_id)
    unresolved_counts = dict(unresolved_q.group_by(EmissionCalculation.reporting_period).all())

    # Revenue denominator -- same pattern as production above. Kept here
    # (rather than reusing intensity_calculation.compute_revenue_batch)
    # to avoid a circular import: intensity_calculation already imports
    # from this module.
    rev_mapping_q = db.query(RevenueMapping).filter(RevenueMapping.tenant_id == tenant_id, RevenueMapping.is_active.is_(True))
    if location_id is not None:
        rev_mapping_q = rev_mapping_q.filter((RevenueMapping.location_id == location_id) | (RevenueMapping.location_id.is_(None)))
    rev_mapping = rev_mapping_q.first()

    revenue_by_period: dict[date, float] = {}
    if rev_mapping is not None:
        rev_entry_q = db.query(Entry).filter(
            Entry.data_point_id == rev_mapping.data_point_id, Entry.status == "Approved", Entry.period.in_(periods)
        )
        if location_id is not None:
            rev_entry_q = rev_entry_q.filter(Entry.location_id == location_id)
        rev_entries_by_period: dict[date, list] = {}
        for e in rev_entry_q.all():
            rev_entries_by_period.setdefault(e.period, []).append(e)
        for p, entries in rev_entries_by_period.items():
            total_native = sum((to_decimal(e.value) for e in entries if e.value is not None), Decimal("0"))
            revenue_by_period[p] = float(total_native * to_decimal(rev_mapping.conversion_multiplier))

    result: dict[date, dict] = {}
    for period in periods:
        rows = rows_by_period.get(period, [])
        has_any_data = len(rows) > 0
        scope1 = sum((r.emissions_kgco2e for r in rows if r.scope == 1), Decimal("0"))
        scope2_loc = sum(
            (r.emissions_kgco2e for r in rows if r.scope == 2 and r.calculation_method == "location_based"), Decimal("0")
        )
        scope2_mkt = sum(
            (r.emissions_kgco2e for r in rows if r.scope == 2 and r.calculation_method == "market_based"), Decimal("0")
        )
        has_scope2_mkt = any(r.scope == 2 and r.calculation_method == "market_based" for r in rows)
        scope1_2_loc = scope1 + scope2_loc

        production_value = production_by_period.get(period)
        intensity = None
        if production_value and production_value > 0 and has_any_data:
            intensity = float(scope1_2_loc / 1000) / production_value

        revenue_value = revenue_by_period.get(period)
        intensity_revenue = None
        if revenue_value and revenue_value > 0 and has_any_data:
            intensity_revenue = float(scope1_2_loc / 1000) / revenue_value

        unresolved_count = unresolved_counts.get(period, 0)
        calculated_count = len(rows)
        total_attempts = calculated_count + unresolved_count
        completeness_pct = (calculated_count / total_attempts * 100) if total_attempts > 0 else None

        result[period] = {
            "rows": rows,
            "scope1_tco2e": (float(scope1 / 1000) if has_any_data else None),
            "scope2_loc_tco2e": (float(scope2_loc / 1000) if has_any_data else None),
            "scope2_mkt_tco2e": (float(scope2_mkt / 1000) if has_scope2_mkt else None),
            "scope1_2_loc_tco2e": (float(scope1_2_loc / 1000) if has_any_data else None),
            "production_value": production_value,
            "production_unit": prod_mapping.canonical_unit if prod_mapping else None,
            "intensity": intensity,
            "revenue_value": revenue_value,
            "revenue_unit": rev_mapping.canonical_unit if rev_mapping else None,
            "intensity_revenue": intensity_revenue,
            "unresolved_count": unresolved_count,
            "calculated_count": calculated_count,
            "completeness_pct": completeness_pct,
        }
    return result


def _sum_optional(values: list[float | None]) -> float | None:
    present = [v for v in values if v is not None]
    return sum(present) if present else None


def compute_range_totals(
    db: Session,
    tenant_id: uuid.UUID,
    location_id: uuid.UUID | None,
    months: list[date],
    by_month: dict[date, dict] | None = None,
) -> dict:
    """Same result shape as one compute_period_totals_batch entry, but
    aggregated across a range of months (quarter-to-date / year-to-date).
    Absolute figures (scope1/scope2/production/revenue/unresolved/
    calculated) sum across the months present; intensity ratios are
    recomputed from those summed totals -- never averaged across months,
    since a rate's numerator and denominator can each vary month to month
    and averaging the ratios would silently misweight them. Pass an
    already-fetched by_month (e.g. one batch covering several ranges'
    months at once) to skip the internal query -- a trend chart computing
    several buckets shouldn't pay one query round trip per bucket."""
    if by_month is None:
        by_month = compute_period_totals_batch(db, tenant_id, location_id, months)

    scope1 = _sum_optional([by_month[m]["scope1_tco2e"] for m in months])
    scope2_loc = _sum_optional([by_month[m]["scope2_loc_tco2e"] for m in months])
    scope2_mkt = _sum_optional([by_month[m]["scope2_mkt_tco2e"] for m in months])
    scope1_2 = None if (scope1 is None and scope2_loc is None) else (scope1 or 0.0) + (scope2_loc or 0.0)

    production_value = _sum_optional([by_month[m]["production_value"] for m in months])
    revenue_value = _sum_optional([by_month[m]["revenue_value"] for m in months])

    intensity = None
    if scope1_2 is not None and production_value and production_value > 0:
        intensity = scope1_2 / production_value

    intensity_revenue = None
    if scope1_2 is not None and revenue_value and revenue_value > 0:
        intensity_revenue = scope1_2 / revenue_value

    unresolved_count = sum(by_month[m]["unresolved_count"] for m in months)
    calculated_count = sum(by_month[m]["calculated_count"] for m in months)
    total_attempts = calculated_count + unresolved_count
    completeness_pct = (calculated_count / total_attempts * 100) if total_attempts > 0 else None

    anchor = by_month[months[0]]
    return {
        "rows": [r for m in months for r in by_month[m]["rows"]],
        "scope1_tco2e": scope1,
        "scope2_loc_tco2e": scope2_loc,
        "scope2_mkt_tco2e": scope2_mkt,
        "scope1_2_loc_tco2e": scope1_2,
        "production_value": production_value,
        "production_unit": anchor["production_unit"],
        "intensity": intensity,
        "revenue_value": revenue_value,
        "revenue_unit": anchor["revenue_unit"],
        "intensity_revenue": intensity_revenue,
        "unresolved_count": unresolved_count,
        "calculated_count": calculated_count,
        "completeness_pct": completeness_pct,
    }
