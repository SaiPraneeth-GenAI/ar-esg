"""Target baseline computation and actual-vs-target status (Prompt 4's
target-setting workflow). A target's metric is one of the Chart Builder's
CHARTABLE_METRICS keys -- the exact same list the dashboards show -- so
picking a target is just picking a metric, never assembling a scope/
method/type boundary by hand. Boundary/metric extraction and status
classification are pure functions; baseline/performance computation reads
approved calculation snapshots through compute_range_totals /
compute_intensity_overview_range -- the same functions the dashboard and
trend charts use, so a target's numbers can never drift from what's shown
elsewhere for the same period.
"""

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.metrics_registry import CHARTABLE_METRICS
from app.db.models import EmissionTarget, ProductionVolumeMapping
from app.schemas.carbon import TargetComparison
from app.services.carbon_calculation import compute_period_totals_batch, compute_range_totals
from app.services.intensity_calculation import (
    compute_intensity_overview_batch,
    compute_intensity_overview_range,
    get_active_revenue_mapping,
)
from app.services.safety_calculation import aggregate_metric_range, metric_values_batch

BASELINE_READY_COMPLETENESS_PCT = 95.0

TARGETABLE_METRIC_KEYS = [
    "energy_absolute", "water_absolute", "waste_absolute", "production_absolute",
    "scope1_tco2e", "scope2_tco2e", "scope1_2_tco2e",
    "ghg_intensity_production", "energy_per_production", "water_per_production", "waste_per_production",
    "ghg_per_revenue", "energy_per_revenue", "water_per_revenue", "waste_per_revenue",
    "safety_fatality", "safety_ltifr", "safety_training", "safety_unsafe", "safety_near_miss",
]

# metric_key -> field name on a compute_range_totals()/compute_period_totals() dict
_GHG_ABSOLUTE_FIELD = {"scope1_tco2e": "scope1_tco2e", "scope2_tco2e": "scope2_loc_tco2e", "scope1_2_tco2e": "scope1_2_loc_tco2e"}
_GHG_RATE_FIELD = {"ghg_intensity_production": "intensity", "ghg_per_revenue": "intensity_revenue"}
# metric_key -> attribute name on an IntensityOverview
_OTHER_RATE_FIELD = {
    "energy_per_production": "energy_per_production",
    "water_per_production": "water_per_production",
    "waste_per_production": "waste_per_production",
    "energy_per_revenue": "energy_per_revenue",
    "water_per_revenue": "water_per_revenue",
    "waste_per_revenue": "waste_per_revenue",
}
_OTHER_ABSOLUTE_FIELD = {
    "energy_absolute": "energy_gj",
    "water_absolute": "water_kl",
    "waste_absolute": "waste_mt",
    "production_absolute": "production_mnah",
}
_SAFETY_FIELD = {
    "safety_fatality": "Fatality",
    "safety_ltifr": "LTIFR",
    "safety_training": "Defensive Driving Training",
    "safety_unsafe": "Unsafe Conditions",
    "safety_near_miss": "Near Miss",
}
HIGHER_IS_BETTER_KEYS = {"production_absolute", "safety_training"}

# A rate (tCO2e/MnAh, GJ/Cr, ...) is compared against the same annual
# figure every month; a budget (a plain tCO2e total) is spread evenly
# across months by default. Dividing a rate by the month count would be
# meaningless -- see target_value_for_month.
RATE_METRIC_KEYS = set(_GHG_RATE_FIELD) | set(_OTHER_RATE_FIELD) | {"safety_ltifr", "safety_training"}


def metric_direction(metric_key: str) -> str:
    return "higher" if metric_key in HIGHER_IS_BETTER_KEYS else "lower"


def metric_aggregation(metric_key: str) -> str:
    return "rate" if metric_key in RATE_METRIC_KEYS else "budget"


def target_from_percentage(baseline: float, percentage: float, metric_key: str) -> float:
    factor = 1 + percentage / 100 if metric_key in HIGHER_IS_BETTER_KEYS else 1 - percentage / 100
    value = baseline * factor
    return min(value, 100.0) if metric_key == "safety_training" else value


def metric_unit(metric_key: str) -> str:
    return CHARTABLE_METRICS[metric_key]["unit"]


def metric_label(metric_key: str) -> str:
    return CHARTABLE_METRICS[metric_key]["label"]


def months_between(start: date, end: date) -> list[date]:
    """Every first-of-month date from start to end inclusive. Both must
    already be month-start dates."""
    months = []
    cursor = start
    while cursor <= end:
        months.append(cursor)
        year = cursor.year + (1 if cursor.month == 12 else 0)
        month = 1 if cursor.month == 12 else cursor.month + 1
        cursor = cursor.replace(year=year, month=month)
    return months


def denominator_mapping_id(db: Session, tenant_id: uuid.UUID, location_id: uuid.UUID | None, metric_key: str) -> uuid.UUID | None:
    """The production or revenue mapping this metric's denominator depends
    on, if any -- folded into boundary_config_hash so a later change to
    that mapping is detectable."""
    if metric_key.endswith("_per_production") or metric_key == "ghg_intensity_production":
        mapping = get_active_production_mapping(db, tenant_id, location_id)
        return mapping.id if mapping else None
    if metric_key.endswith("_per_revenue"):
        mapping = get_active_revenue_mapping(db, tenant_id, location_id)
        return mapping.id if mapping else None
    return None


def boundary_config_hash(tenant_id: uuid.UUID, location_id: uuid.UUID | None, metric_key: str, denominator_mapping_id: uuid.UUID | None) -> str:
    """Detects when a target's boundary or denominator has moved under it.
    Not a secret -- just a stable fingerprint, so sha256 with no salt is
    fine."""
    raw = "|".join([str(tenant_id), str(location_id or ""), metric_key, str(denominator_mapping_id or "")])
    return hashlib.sha256(raw.encode()).hexdigest()


def extract_metric_value(
    db: Session, tenant_id: uuid.UUID, location_id: uuid.UUID | None, metric_key: str, months: list[date]
) -> tuple[float | None, float | None]:
    """The metric's value aggregated across `months` (a single month, or a
    whole baseline/target window), plus a completeness percentage where
    that concept applies. Delegates entirely to the same range-aggregation
    functions the dashboard's trend charts use -- an intensity's numerator
    and denominator are each summed across the window and only then
    divided, never averaged month-by-month (which would misweight months
    with different production/revenue volume)."""
    if metric_key in _GHG_ABSOLUTE_FIELD or metric_key in _GHG_RATE_FIELD:
        totals = compute_range_totals(db, tenant_id, location_id, months)
        field = _GHG_ABSOLUTE_FIELD.get(metric_key) or _GHG_RATE_FIELD.get(metric_key)
        return totals[field], totals["completeness_pct"]
    if metric_key in _SAFETY_FIELD:
        values = metric_values_batch(db, tenant_id, location_id, months)
        value, _ = aggregate_metric_range(_SAFETY_FIELD[metric_key], values[_SAFETY_FIELD[metric_key]], months)
        return value, (100.0 if value is not None else None)
    overview = compute_intensity_overview_range(db, tenant_id, location_id, months)
    value = getattr(overview, (_OTHER_RATE_FIELD | _OTHER_ABSOLUTE_FIELD)[metric_key])
    return value, (100.0 if value is not None else None)


def extract_metric_value_batch(
    db: Session, tenant_id: uuid.UUID, location_id: uuid.UUID | None, metric_key: str, months: list[date]
) -> dict[date, tuple[float | None, float | None]]:
    """The same (value, completeness_pct) pair extract_metric_value returns,
    for every month in `months` at once -- one batched query set covering
    every month, not one round of queries per month. Used by
    /targets/{id}/performance, which needs each month of a target's period
    individually rather than one aggregated range."""
    if metric_key in _GHG_ABSOLUTE_FIELD or metric_key in _GHG_RATE_FIELD:
        by_month = compute_period_totals_batch(db, tenant_id, location_id, months)
        field = _GHG_ABSOLUTE_FIELD.get(metric_key) or _GHG_RATE_FIELD.get(metric_key)
        return {m: (by_month[m][field], by_month[m]["completeness_pct"]) for m in months}
    if metric_key in _SAFETY_FIELD:
        values = metric_values_batch(db, tenant_id, location_id, months)
        name = _SAFETY_FIELD[metric_key]
        return {m: (values[name][m][0], 100.0 if values[name][m][0] is not None else None) for m in months}
    overview_by_month = compute_intensity_overview_batch(db, tenant_id, location_id, months)
    attr = (_OTHER_RATE_FIELD | _OTHER_ABSOLUTE_FIELD)[metric_key]
    return {
        m: (getattr(overview_by_month[m], attr), 100.0 if getattr(overview_by_month[m], attr) is not None else None)
        for m in months
    }


def get_active_production_mapping(db: Session, tenant_id: uuid.UUID, location_id: uuid.UUID | None) -> ProductionVolumeMapping | None:
    q = db.query(ProductionVolumeMapping).filter(
        ProductionVolumeMapping.tenant_id == tenant_id, ProductionVolumeMapping.is_active.is_(True)
    )
    if location_id is not None:
        q = q.filter((ProductionVolumeMapping.location_id == location_id) | (ProductionVolumeMapping.location_id.is_(None)))
    return q.first()


@dataclass
class MonthBaseline:
    period: date
    value: float | None
    completeness_pct: float | None
    calculation_ids: list[uuid.UUID] = field(default_factory=list)


@dataclass
class BaselineResult:
    ready: bool
    provisional: bool
    baseline_value: float | None
    completeness_pct: float | None
    months: list[MonthBaseline]
    message: str


def compute_baseline(
    db: Session, tenant_id: uuid.UUID, location_id: uuid.UUID | None, metric_key: str, period_start: date, period_end: date
) -> BaselineResult:
    """Aggregates approved calculation snapshots across every month in the
    baseline window. A baseline is 'ready' only when every month reaches
    the completeness threshold (for metrics that track completeness);
    short of that it's shown as provisional and directs the user to the
    missing entries/factors rather than presenting a misleading number
    (rule #5 in Prompt 4)."""
    months = months_between(period_start, period_end)
    is_ghg = metric_key in _GHG_ABSOLUTE_FIELD or metric_key in _GHG_RATE_FIELD

    if is_ghg:
        by_month = compute_period_totals_batch(db, tenant_id, location_id, months)
        field = _GHG_ABSOLUTE_FIELD.get(metric_key) or _GHG_RATE_FIELD.get(metric_key)
        month_results = [
            MonthBaseline(
                period=m, value=by_month[m][field], completeness_pct=by_month[m]["completeness_pct"],
                calculation_ids=[r.id for r in by_month[m]["rows"]],
            )
            for m in months
        ]
        range_totals = compute_range_totals(db, tenant_id, location_id, months, by_month=by_month)
        baseline_value = range_totals[field]
        overall_completeness = range_totals["completeness_pct"]
        any_data = any(by_month[m]["calculated_count"] > 0 or by_month[m]["unresolved_count"] > 0 for m in months)
        any_incomplete = any((by_month[m]["completeness_pct"] or 0) < BASELINE_READY_COMPLETENESS_PCT for m in months)
    elif metric_key in _SAFETY_FIELD:
        values = metric_values_batch(db, tenant_id, location_id, months)
        name = _SAFETY_FIELD[metric_key]
        month_results = [
            MonthBaseline(period=m, value=values[name][m][0], completeness_pct=(100.0 if values[name][m][0] is not None else None))
            for m in months
        ]
        baseline_value, _ = aggregate_metric_range(name, values[name], months)
        overall_completeness = 100.0 if baseline_value is not None else None
        any_data = any(values[name][m][0] is not None for m in months)
        any_incomplete = False
    else:
        overview_by_month = compute_intensity_overview_batch(db, tenant_id, location_id, months)
        attr = (_OTHER_RATE_FIELD | _OTHER_ABSOLUTE_FIELD)[metric_key]
        month_results = [
            MonthBaseline(
                period=m, value=getattr(overview_by_month[m], attr),
                completeness_pct=(100.0 if getattr(overview_by_month[m], attr) is not None else None),
            )
            for m in months
        ]
        range_overview = compute_intensity_overview_range(db, tenant_id, location_id, months, by_month=overview_by_month)
        baseline_value = getattr(range_overview, attr)
        overall_completeness = 100.0 if baseline_value is not None else None
        any_data = any(getattr(overview_by_month[m], attr) is not None for m in months)
        any_incomplete = False  # no partial-month completeness concept for these metrics yet

    if not any_data:
        return BaselineResult(
            ready=False, provisional=False, baseline_value=None, completeness_pct=None, months=month_results,
            message="Baseline not ready -- no approved data found in this period yet.",
        )
    if baseline_value is None:
        return BaselineResult(
            ready=False, provisional=False, baseline_value=None, completeness_pct=overall_completeness, months=month_results,
            message="Baseline not ready -- some of the data needed to compute this metric is missing (e.g. production volume or revenue).",
        )
    if any_incomplete:
        return BaselineResult(
            ready=True, provisional=True, baseline_value=baseline_value, completeness_pct=overall_completeness, months=month_results,
            message=(
                f"Baseline is provisional -- at least one month is below {BASELINE_READY_COMPLETENESS_PCT:.0f}% data "
                "completeness. You can still activate it, but resolve the missing entries/factors first if possible."
            ),
        )
    return BaselineResult(
        ready=True, provisional=False, baseline_value=baseline_value, completeness_pct=overall_completeness, months=month_results,
        message="Baseline is ready.",
    )


def validate_monthly_phasing(monthly_phasing: list[dict], target_value: float, target_period_start: date, target_period_end: date) -> str | None:
    """Returns an error message, or None if the phasing is valid. An empty
    phasing list is valid -- it means the target isn't phased, just an
    annual figure."""
    if not monthly_phasing:
        return None

    expected_months = {m.isoformat() for m in months_between(target_period_start, target_period_end)}
    seen_months = set()
    total = Decimal("0")
    for entry in monthly_phasing:
        period = entry.get("period")
        value = entry.get("value")
        if period not in expected_months:
            return f"Phased month {period} falls outside the target period."
        if period in seen_months:
            return f"Phased month {period} is listed more than once."
        seen_months.add(period)
        total += Decimal(str(value))

    if seen_months != expected_months:
        missing = sorted(expected_months - seen_months)
        return f"Monthly phasing is missing: {', '.join(missing)}."

    target_decimal = Decimal(str(target_value))
    if abs(total - target_decimal) > Decimal("0.01"):
        return f"Monthly phasing sums to {total}, which does not match the annual target of {target_decimal}."

    return None


def target_value_for_month(
    monthly_phasing: list[dict], period: date, target_value: float | None, num_months: int, metric_key: str = "scope1_2_tco2e"
) -> float | None:
    """The month's target figure -- its explicit phased value if phasing
    was set, otherwise derived from the annual target. A budget metric
    (a plain tCO2e total) is spread evenly across months by default. A
    rate metric (tCO2e/MnAh, GJ/Cr, ...) is compared against the same
    annual figure every month -- dividing it by the month count would
    compare each month's actual rate against a twelfth of the rate, which
    is meaningless."""
    if monthly_phasing:
        for entry in monthly_phasing:
            if entry.get("period") == period.isoformat():
                return float(entry["value"])
        return None
    if target_value is None:
        return None
    if metric_key in RATE_METRIC_KEYS:
        return target_value
    if num_months == 0:
        return None
    return target_value / num_months


@dataclass
class TargetStatus:
    target_id: uuid.UUID
    metric_key: str
    label: str
    unit: str
    actual: float | None
    target_value: float
    status: str


def all_target_comparisons(db: Session, tenant_id: uuid.UUID, location_id: uuid.UUID | None, months: list[date]) -> list["TargetStatus"]:
    """Every active target for this location that's currently in its period
    -- not just the handful of metrics a given dashboard card hardcodes.
    One query for all active targets, then only the metrics that actually
    have one pay for extract_metric_value. Mirrors the single-metric logic
    in carbon.py's _active_target_comparison exactly, generalized across
    every targetable metric at once."""
    anchor_period = months[-1]
    targets = (
        db.query(EmissionTarget)
        .filter(
            EmissionTarget.tenant_id == tenant_id,
            EmissionTarget.location_id == location_id,
            EmissionTarget.status == "active",
            EmissionTarget.target_period_start <= anchor_period,
            EmissionTarget.target_period_end >= anchor_period,
        )
        .all()
    )
    if not targets:
        return []

    # Batched once for every target this call needs, instead of each
    # target re-running its own compute_range_totals/
    # compute_intensity_overview_range (which would otherwise re-scan the
    # same approved calculations/production/safety data once per target --
    # see extract_metric_value). Even a fully targeted dashboard therefore
    # performs one batched read per source rather than one per measure.
    needs_ghg = any(t.metric_key in _GHG_ABSOLUTE_FIELD or t.metric_key in _GHG_RATE_FIELD for t in targets)
    needs_other = any(t.metric_key in _OTHER_RATE_FIELD or t.metric_key in _OTHER_ABSOLUTE_FIELD for t in targets)
    needs_safety = any(t.metric_key in _SAFETY_FIELD for t in targets)
    ghg_by_month = compute_period_totals_batch(db, tenant_id, location_id, months) if needs_ghg else None
    other_by_month = compute_intensity_overview_batch(db, tenant_id, location_id, months) if needs_other else None
    safety_by_month = metric_values_batch(db, tenant_id, location_id, months) if needs_safety else None

    results: list[TargetStatus] = []
    for target in targets:
        if target.target_value is None or target.metric_key not in CHARTABLE_METRICS:
            continue
        num_months = len(months_between(target.target_period_start, target.target_period_end))
        if target.metric_key in RATE_METRIC_KEYS:
            range_target = target_value_for_month(
                target.monthly_phasing, anchor_period, float(target.target_value), num_months, target.metric_key
            )
        else:
            relevant = [m for m in months if target.target_period_start <= m <= target.target_period_end]
            monthly_targets = [
                target_value_for_month(target.monthly_phasing, m, float(target.target_value), num_months, target.metric_key)
                for m in relevant
            ]
            monthly_targets = [t for t in monthly_targets if t is not None]
            range_target = sum(monthly_targets) if monthly_targets else None
        if range_target is None:
            continue
        window = [m for m in months if target.target_period_start <= m <= target.target_period_end] or months
        if target.metric_key in _GHG_ABSOLUTE_FIELD or target.metric_key in _GHG_RATE_FIELD:
            totals = compute_range_totals(db, tenant_id, location_id, window, by_month=ghg_by_month)
            field = _GHG_ABSOLUTE_FIELD.get(target.metric_key) or _GHG_RATE_FIELD.get(target.metric_key)
            actual = totals[field]
        elif target.metric_key in _SAFETY_FIELD:
            name = _SAFETY_FIELD[target.metric_key]
            actual, _ = aggregate_metric_range(name, safety_by_month[name], window)
        else:
            overview = compute_intensity_overview_range(db, tenant_id, location_id, window, by_month=other_by_month)
            actual = getattr(overview, (_OTHER_RATE_FIELD | _OTHER_ABSOLUTE_FIELD)[target.metric_key])
        results.append(
            TargetStatus(
                target_id=target.id,
                metric_key=target.metric_key,
                label=metric_label(target.metric_key),
                unit=metric_unit(target.metric_key),
                actual=actual,
                target_value=range_target,
                status=classify_metric_status(actual, range_target, target.metric_key),
            )
        )
    return results


def target_value_for_bucket(target: EmissionTarget | None, metric_key: str, months: list[date]) -> float | None:
    """The metric's target figure for exactly this bucket -- None (not
    substituted with anything) when the target doesn't apply here, either
    because there is no active target for this metric/location or because
    this bucket falls outside the target's own period (e.g. a 2027 target
    contributes nothing to a 2026 bucket). `months` is the same range the
    actual figure was aggregated over: a budget metric's total is summed
    across exactly those months so it's comparable to a multi-month
    actual; a rate metric's value stays constant regardless of range
    length. Shared by every dashboard tab's target badge and trend-line
    logic so they can never disagree with each other."""
    if target is None or target.target_value is None:
        return None
    anchor_period = months[-1]
    if not (target.target_period_start <= anchor_period <= target.target_period_end):
        return None
    num_months = len(months_between(target.target_period_start, target.target_period_end))
    if metric_key in RATE_METRIC_KEYS:
        return target_value_for_month(target.monthly_phasing, anchor_period, float(target.target_value), num_months, metric_key)
    relevant = [m for m in months if target.target_period_start <= m <= target.target_period_end]
    monthly_targets = [
        target_value_for_month(target.monthly_phasing, m, float(target.target_value), num_months, metric_key)
        for m in relevant
    ]
    monthly_targets = [t for t in monthly_targets if t is not None]
    return sum(monthly_targets) if monthly_targets else None


def active_targets_by_metric(db: Session, tenant_id: uuid.UUID, location_id: uuid.UUID | None, metric_keys: list[str]) -> dict[str, EmissionTarget]:
    """One query for every active target a trend chart could need a
    reference line for -- targets are few (at most one per metric per
    location), so this is never worth batching per-bucket."""
    targets = (
        db.query(EmissionTarget)
        .filter(
            EmissionTarget.tenant_id == tenant_id,
            EmissionTarget.location_id == location_id,
            EmissionTarget.metric_key.in_(metric_keys),
            EmissionTarget.status == "active",
        )
        .all()
    )
    return {t.metric_key: t for t in targets}


def active_target_comparison(
    db: Session, tenant_id: uuid.UUID, location_id: uuid.UUID | None, metric_key: str, months: list[date], actual: float | None
) -> TargetComparison | None:
    """Only ever reads an active target for the exact same boundary the
    caller already shows -- never substitutes a different location/metric
    target, and never fabricates a comparison when none has been
    declared (rule: targets are never auto-created). Returns None only
    when there's truly no active target for this metric/location -- a
    target that exists but whose period doesn't cover this month (not
    started yet, or already ended) still returns a comparison, carrying
    that status instead of a fabricated actual-vs-target number, so a
    card can say "Not started yet" instead of a misleading "No target
    set" (a real target was declared -- it's just not in force yet)."""
    target = (
        db.query(EmissionTarget)
        .filter(
            EmissionTarget.tenant_id == tenant_id,
            EmissionTarget.location_id == location_id,
            EmissionTarget.metric_key == metric_key,
            EmissionTarget.status == "active",
        )
        .first()
    )
    if target is None:
        return None
    anchor_period = months[-1]
    if anchor_period < target.target_period_start:
        return TargetComparison(
            target_id=target.id,
            target_value=float(target.target_value) if target.target_value is not None else None,
            status="Not started yet",
        )
    if anchor_period > target.target_period_end:
        return TargetComparison(
            target_id=target.id,
            target_value=float(target.target_value) if target.target_value is not None else None,
            status="Target period ended",
        )
    range_target = target_value_for_bucket(target, metric_key, months)
    if range_target is None:
        return None
    return TargetComparison(target_id=target.id, target_value=range_target, status=classify_metric_status(actual, range_target, metric_key))


def classify_metric_status(actual: float | None, target: float | None, metric_key: str) -> str:
    if actual is None or target is None:
        return "Not enough data"
    within = actual >= target if metric_key in HIGHER_IS_BETTER_KEYS else actual <= target
    return "Within safe limits" if within else "Exceeded"


def classify_status(actual: float | None, target: float | None) -> str:
    """Backward-compatible lower-is-better classification helper."""
    return classify_metric_status(actual, target, "scope1_2_tco2e")
