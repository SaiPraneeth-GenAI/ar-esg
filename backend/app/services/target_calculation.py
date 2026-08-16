"""Target baseline computation and actual-vs-target status (Prompt 4's
target-setting workflow). Boundary/metric extraction and status
classification are pure functions; baseline/performance computation reads
approved calculation snapshots through compute_period_totals -- the same
function the dashboard overview uses, so a target's numbers can never
drift from what the dashboard shows for the same period.
"""

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.db.models import ProductionVolumeMapping
from app.services.carbon_calculation import compute_period_totals

BASELINE_READY_COMPLETENESS_PCT = 95.0
STATUS_WATCH_MARGIN_PCT = 5.0


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


def boundary_config_hash(
    tenant_id: uuid.UUID,
    location_id: uuid.UUID | None,
    scope: str,
    calculation_method: str | None,
    metric_type: str,
    production_mapping_id: uuid.UUID | None,
) -> str:
    """Detects when a target's boundary or denominator has moved under it.
    Not a secret -- just a stable fingerprint, so sha256 with no salt is
    fine."""
    raw = "|".join(
        [
            str(tenant_id),
            str(location_id or ""),
            scope,
            calculation_method or "",
            metric_type,
            str(production_mapping_id or ""),
        ]
    )
    return hashlib.sha256(raw.encode()).hexdigest()


def validate_metric_scope(scope: str, metric_type: str) -> str | None:
    """Intensity is only defined for the combined Scope 1+2 location-based
    boundary -- the only denominator (production volume) the platform
    tracks. Returns an error message, or None if valid."""
    if metric_type == "intensity_tco2e_per_mnah" and scope != "1_2_combined":
        return "Intensity targets are only supported for the Scope 1+2 (location-based) boundary."
    return None


def extract_metric_value(totals: dict, scope: str, calculation_method: str | None) -> tuple[float | None, str | None]:
    """Reads the one number a target boundary/metric combination refers to
    out of a compute_period_totals() result. Returns (value, error) --
    error is set when the boundary/metric combination has no defined
    meaning (e.g. intensity for scope 1 alone)."""
    if scope == "1_2_combined":
        return totals["scope1_2_loc_tco2e"], None
    if scope == "1":
        return totals["scope1_tco2e"], None
    if scope == "2":
        if calculation_method == "market_based":
            return totals["scope2_mkt_tco2e"], None
        return totals["scope2_loc_tco2e"], None
    return None, f"Unknown scope boundary '{scope}'."


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
    db: Session,
    tenant_id: uuid.UUID,
    location_id: uuid.UUID | None,
    scope: str,
    calculation_method: str | None,
    metric_type: str,
    period_start: date,
    period_end: date,
) -> BaselineResult:
    """Aggregates approved calculation snapshots across every month in the
    baseline window. A baseline is 'ready' only when every month reaches
    the completeness threshold; short of that it's shown as provisional
    and directs the user to the missing entries/factors rather than
    presenting a misleading number (rule #5 in Prompt 4)."""
    months = months_between(period_start, period_end)
    month_results: list[MonthBaseline] = []
    total_emissions_kg = Decimal("0")
    total_production = Decimal("0")
    any_month_incomplete = False
    any_data_at_all = False

    for m in months:
        totals = compute_period_totals(db, tenant_id, location_id, m)
        value, error = extract_metric_value(totals, scope, calculation_method)
        completeness = totals["completeness_pct"]
        calc_ids = [r.id for r in totals["rows"]]

        if totals["calculated_count"] > 0 or totals["unresolved_count"] > 0:
            any_data_at_all = True
        if completeness is None or completeness < BASELINE_READY_COMPLETENESS_PCT:
            any_month_incomplete = True

        month_results.append(MonthBaseline(period=m, value=value, completeness_pct=completeness, calculation_ids=calc_ids))

        if metric_type == "absolute_tco2e" and value is not None:
            total_emissions_kg += Decimal(str(value)) * 1000
        elif metric_type == "intensity_tco2e_per_mnah":
            scope1_2 = totals["scope1_2_loc_tco2e"]
            if scope1_2 is not None:
                total_emissions_kg += Decimal(str(scope1_2)) * 1000
            if totals["production_value"]:
                total_production += Decimal(str(totals["production_value"]))

    if not any_data_at_all:
        return BaselineResult(
            ready=False,
            provisional=False,
            baseline_value=None,
            completeness_pct=None,
            months=month_results,
            message="Baseline not ready -- no approved activity data found in this period yet.",
        )

    if metric_type == "absolute_tco2e":
        baseline_value = float(total_emissions_kg / 1000)
    else:
        if total_production <= 0:
            return BaselineResult(
                ready=False,
                provisional=False,
                baseline_value=None,
                completeness_pct=None,
                months=month_results,
                message="Baseline not ready -- no approved production volume found in this period, so intensity can't be computed.",
            )
        baseline_value = float(total_emissions_kg / 1000) / float(total_production)

    overall_completeness = sum(m.completeness_pct or 0 for m in month_results) / len(month_results)

    if any_month_incomplete:
        return BaselineResult(
            ready=True,
            provisional=True,
            baseline_value=baseline_value,
            completeness_pct=overall_completeness,
            months=month_results,
            message=(
                f"Baseline is provisional -- at least one month is below {BASELINE_READY_COMPLETENESS_PCT:.0f}% data "
                "completeness. You can still activate it, but resolve the missing entries/factors first if possible."
            ),
        )

    return BaselineResult(
        ready=True,
        provisional=False,
        baseline_value=baseline_value,
        completeness_pct=overall_completeness,
        months=month_results,
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


def target_value_for_month(monthly_phasing: list[dict], period: date, target_value: float | None, num_months: int) -> float | None:
    """The month's target figure -- its explicit phased value if phasing
    was set, otherwise the annual target spread evenly."""
    if monthly_phasing:
        for entry in monthly_phasing:
            if entry.get("period") == period.isoformat():
                return float(entry["value"])
        return None
    if target_value is None or num_months == 0:
        return None
    return target_value / num_months


def classify_status(actual: float | None, target: float | None) -> str:
    """On track / Watch / Off track / Not enough data -- a target is a
    reduction, so at-or-below target is good. Mirrors the dashboard's
    0%/10% comparison thresholds in spirit, with a tighter 5% watch band
    since this is being measured against a committed number, not just a
    prior-period comparison."""
    if actual is None or target is None:
        return "Not enough data"
    if actual <= target:
        return "On track"
    if actual <= target * (1 + STATUS_WATCH_MARGIN_PCT / 100):
        return "Watch"
    return "Off track"
