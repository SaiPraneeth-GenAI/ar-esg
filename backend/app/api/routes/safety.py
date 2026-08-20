import uuid
from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, require_roles
from app.db.session import get_db
from app.schemas.safety import SafetyMetricOut, SafetyOverviewOut, SafetyTrendPoint
from app.services.carbon_calculation import (
    months_in_range,
    prior_range_for_mode,
    prior_year_range_for_mode,
    range_bounds_for_mode,
    trailing_buckets_for_mode,
)
from app.services.rollups import month_start
from app.services.safety_calculation import METRIC_NAMES, aggregate_metric_range, metric_values_batch
from app.services.target_calculation import active_target_comparison

router = APIRouter(prefix="/safety", tags=["safety"])

SAFETY_TARGET_KEYS = {
    "safety_fatality": "Fatality",
    "safety_ltifr": "LTIFR",
    "safety_training": "Defensive Driving Training",
    "safety_unsafe": "Unsafe Conditions",
    "safety_near_miss": "Near Miss",
}

@router.get("/overview", response_model=SafetyOverviewOut)
def safety_overview(
    period: date,
    location_id: uuid.UUID | None = None,
    period_mode: str = "month",
    current: CurrentUser = Depends(require_roles("Admin", "Manager", "Approver")),
    db: Session = Depends(get_db),
):
    """period_mode: 'month' (default), 'quarter' (quarter-to-date), or
    'ytd' (year-to-date). Counted metrics sum across the range; LTIFR (a
    rate) averages across the months present -- see METRIC_RANGE_AGGREGATION."""
    period = month_start(period)
    range_start, range_end = range_bounds_for_mode(period, period_mode)
    current_months = months_in_range(range_start, range_end)
    prior_start, prior_end = prior_range_for_mode(range_start, range_end, period_mode)
    prior_months = months_in_range(prior_start, prior_end)
    prior_year_start, prior_year_end = prior_year_range_for_mode(range_start, range_end)
    prior_year_months = months_in_range(prior_year_start, prior_year_end)

    all_months = sorted(set(current_months) | set(prior_months) | set(prior_year_months))
    values = metric_values_batch(db, current.tenant_id, location_id, all_months)

    metrics = []
    for name in METRIC_NAMES:
        value, unit = aggregate_metric_range(name, values[name], current_months)
        prior_value, _ = aggregate_metric_range(name, values[name], prior_months)
        prior_year_value, _ = aggregate_metric_range(name, values[name], prior_year_months)
        metric_key = next(key for key, metric_name in SAFETY_TARGET_KEYS.items() if metric_name == name)
        metrics.append(
            SafetyMetricOut(
                name=name, value=value, unit=unit, prior_value=prior_value, prior_year_value=prior_year_value,
                target=active_target_comparison(db, current.tenant_id, location_id, metric_key, current_months, value),
            )
        )

    return SafetyOverviewOut(period=period, period_mode=period_mode, period_start=range_start, period_end=range_end, metrics=metrics)


@router.get("/trend", response_model=list[SafetyTrendPoint])
def safety_trend(
    period: date,
    months: int = 6,
    location_id: uuid.UUID | None = None,
    period_mode: str = "month",
    current: CurrentUser = Depends(require_roles("Admin", "Manager", "Approver")),
    db: Session = Depends(get_db),
):
    """Trailing N buckets, each paired with the same bucket one year
    earlier. period_mode picks the bucket granularity: 'month' (default),
    'quarter', or 'ytd' (year buckets). Counted metrics sum across a
    bucket's months, LTIFR/Defensive Driving Training average -- see
    METRIC_RANGE_AGGREGATION."""
    period = month_start(period)
    count = min(max(months, 1), 24) if period_mode == "month" else min(max(months, 1), 8)
    buckets = trailing_buckets_for_mode(period, period_mode, count)

    all_months: set[date] = set()
    prior_year_buckets: list[tuple[date, date]] = []
    for start, end in buckets:
        all_months.update(months_in_range(start, end))
        py_start, py_end = prior_year_range_for_mode(start, end)
        prior_year_buckets.append((py_start, py_end))
        all_months.update(months_in_range(py_start, py_end))

    values = metric_values_batch(db, current.tenant_id, location_id, sorted(all_months))

    points = []
    for (start, end), (py_start, py_end) in zip(buckets, prior_year_buckets):
        bucket_months = months_in_range(start, end)
        py_months = months_in_range(py_start, py_end)
        points.append(
            SafetyTrendPoint(
                period=end,
                bucket_start=start,
                bucket_end=end,
                values={name: aggregate_metric_range(name, values[name], bucket_months)[0] for name in METRIC_NAMES},
                prior_year_values={name: aggregate_metric_range(name, values[name], py_months)[0] for name in METRIC_NAMES},
            )
        )
    return points
