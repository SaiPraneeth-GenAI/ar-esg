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

from sqlalchemy.orm import Session

from app.core.carbon_mapping import CarbonSourceMapping, get_carbon_mapping
from app.db.models import DataPoint, EmissionCalculation, EmissionFactor, Entry, IpccReference

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


def normalize_fuel_activity(
    activity_value: Decimal, activity_unit: str, factor_unit: str, density_kg_per_unit: Decimal | None
) -> tuple[Decimal, str] | UnresolvedResult:
    """Fuel factors are expressed per litre or per kg. Converts only when a
    documented density is on file (rule #8) -- never assumes kg == litre."""
    factor_unit_l = factor_unit.lower()
    if "litre" in factor_unit_l or "/l" in factor_unit_l:
        factor_basis = "litre"
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
    db: Session, entry: Entry, dp: DataPoint, tenant_id: uuid.UUID, calculated_by: uuid.UUID | None
) -> EmissionCalculation | None:
    """Builds (via db.add, not committed) the EmissionCalculation row for
    one entry, superseding whatever was previously current for it. Returns
    None -- writes nothing -- when the data point isn't a mapped GHG
    source at all (Water/Waste/etc stay out of the queue entirely, not
    flagged as perpetually "unresolved")."""
    mapping = get_carbon_mapping(dp.name)
    if mapping is None:
        return None

    if entry.status != "Approved":
        outcome = CalculationOutcome(status="unresolved", scope=mapping.scope, resolution_reason=UNRESOLVED_REASONS["not_approved"])
    elif entry.value is None:
        outcome = CalculationOutcome(status="unresolved", scope=mapping.scope, resolution_reason=UNRESOLVED_REASONS["missing_value"])
    else:
        outcome = run_calculation(db, tenant_id, mapping, to_decimal(entry.value), dp.unit or "", entry.period)

    existing = (
        db.query(EmissionCalculation)
        .filter(EmissionCalculation.entry_id == entry.id, EmissionCalculation.status.in_(["calculated", "unresolved"]))
        .first()
    )

    resolved = outcome.resolved
    calc = EmissionCalculation(
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
    caller can commit once (rule: bounded transaction, not per-entry)."""
    results: list[tuple[Entry, EmissionCalculation | None]] = []
    dp_cache: dict[uuid.UUID, DataPoint] = {}
    for entry in entries:
        dp = dp_cache.get(entry.data_point_id)
        if dp is None:
            dp = db.get(DataPoint, entry.data_point_id)
            dp_cache[entry.data_point_id] = dp
        results.append((entry, build_calculation_row(db, entry, dp, tenant_id, calculated_by)))
    return results
