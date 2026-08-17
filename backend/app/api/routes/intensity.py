import uuid
from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, require_roles
from app.db.session import get_db
from app.schemas.intensity import IntensityOverviewOut, IntensityTrendPoint
from app.services.carbon_calculation import (
    months_in_range,
    prior_range_for_mode,
    prior_year_range_for_mode,
    range_bounds_for_mode,
    trailing_buckets_for_mode,
)
from app.services.intensity_calculation import compute_intensity_overview_batch, compute_intensity_overview_range
from app.services.rollups import month_start
from app.services.target_calculation import active_target_comparison, active_targets_by_metric, target_value_for_bucket

router = APIRouter(prefix="/intensity", tags=["intensity"])

# intensity.py's own field names don't all match the targetable metric_key
# registry (e.g. this route's "ghg_per_production" is target-tracked under
# the key "ghg_intensity_production", the same underlying figure carbon.py's
# dashboard tile also shows) -- this maps each tile to its real metric_key.
_PRODUCTION_METRIC_KEYS = {
    "ghg": "ghg_intensity_production",
    "energy": "energy_per_production",
    "water": "water_per_production",
    "waste": "waste_per_production",
}
_REVENUE_METRIC_KEYS = {
    "ghg": "ghg_per_revenue",
    "energy": "energy_per_revenue",
    "water": "water_per_revenue",
    "waste": "waste_per_revenue",
}


@router.get("/overview", response_model=IntensityOverviewOut)
def intensity_overview(
    period: date,
    location_id: uuid.UUID | None = None,
    period_mode: str = "month",
    current: CurrentUser = Depends(require_roles("Admin", "Manager", "Approver")),
    db: Session = Depends(get_db),
):
    """period_mode: 'month' (default), 'quarter' (quarter-to-date), or
    'ytd' (year-to-date) -- mirrors /carbon/overview's range aggregation
    (sum absolutes, recompute ratios from the sums)."""
    period = month_start(period)
    range_start, range_end = range_bounds_for_mode(period, period_mode)
    current_months = months_in_range(range_start, range_end)
    prior_start, prior_end = prior_range_for_mode(range_start, range_end, period_mode)
    prior_months = months_in_range(prior_start, prior_end)
    prior_year_start, prior_year_end = prior_year_range_for_mode(range_start, range_end)
    prior_year_months = months_in_range(prior_year_start, prior_year_end)

    current_ov = compute_intensity_overview_range(db, current.tenant_id, location_id, current_months)
    prior_ov = compute_intensity_overview_range(db, current.tenant_id, location_id, prior_months)
    prior_year_ov = compute_intensity_overview_range(db, current.tenant_id, location_id, prior_year_months)

    ghg_per_production_target = active_target_comparison(
        db, current.tenant_id, location_id, _PRODUCTION_METRIC_KEYS["ghg"], current_months, current_ov.ghg_per_production
    )
    energy_per_production_target = active_target_comparison(
        db, current.tenant_id, location_id, _PRODUCTION_METRIC_KEYS["energy"], current_months, current_ov.energy_per_production
    )
    water_per_production_target = active_target_comparison(
        db, current.tenant_id, location_id, _PRODUCTION_METRIC_KEYS["water"], current_months, current_ov.water_per_production
    )
    waste_per_production_target = active_target_comparison(
        db, current.tenant_id, location_id, _PRODUCTION_METRIC_KEYS["waste"], current_months, current_ov.waste_per_production
    )
    ghg_per_revenue_target = active_target_comparison(
        db, current.tenant_id, location_id, _REVENUE_METRIC_KEYS["ghg"], current_months, current_ov.ghg_per_revenue
    )
    energy_per_revenue_target = active_target_comparison(
        db, current.tenant_id, location_id, _REVENUE_METRIC_KEYS["energy"], current_months, current_ov.energy_per_revenue
    )
    water_per_revenue_target = active_target_comparison(
        db, current.tenant_id, location_id, _REVENUE_METRIC_KEYS["water"], current_months, current_ov.water_per_revenue
    )
    waste_per_revenue_target = active_target_comparison(
        db, current.tenant_id, location_id, _REVENUE_METRIC_KEYS["waste"], current_months, current_ov.waste_per_revenue
    )

    return IntensityOverviewOut(
        period=current_ov.period,
        period_mode=period_mode,
        period_start=range_start,
        period_end=range_end,
        energy_gj=current_ov.energy_gj,
        ghg_tco2e=current_ov.ghg_tco2e,
        water_kl=current_ov.water_kl,
        waste_mt=current_ov.waste_mt,
        production_mnah=current_ov.production_mnah,
        revenue_inr_cr=current_ov.revenue_inr_cr,
        energy_per_production=current_ov.energy_per_production,
        ghg_per_production=current_ov.ghg_per_production,
        water_per_production=current_ov.water_per_production,
        waste_per_production=current_ov.waste_per_production,
        energy_per_revenue=current_ov.energy_per_revenue,
        ghg_per_revenue=current_ov.ghg_per_revenue,
        water_per_revenue=current_ov.water_per_revenue,
        waste_per_revenue=current_ov.waste_per_revenue,
        prior_energy_per_production=prior_ov.energy_per_production,
        prior_ghg_per_production=prior_ov.ghg_per_production,
        prior_water_per_production=prior_ov.water_per_production,
        prior_waste_per_production=prior_ov.waste_per_production,
        prior_energy_per_revenue=prior_ov.energy_per_revenue,
        prior_ghg_per_revenue=prior_ov.ghg_per_revenue,
        prior_water_per_revenue=prior_ov.water_per_revenue,
        prior_waste_per_revenue=prior_ov.waste_per_revenue,
        prior_energy_gj=prior_ov.energy_gj,
        prior_ghg_tco2e=prior_ov.ghg_tco2e,
        prior_water_kl=prior_ov.water_kl,
        prior_waste_mt=prior_ov.waste_mt,
        prior_production_mnah=prior_ov.production_mnah,
        prior_revenue_inr_cr=prior_ov.revenue_inr_cr,
        prior_year_energy_per_production=prior_year_ov.energy_per_production,
        prior_year_ghg_per_production=prior_year_ov.ghg_per_production,
        prior_year_water_per_production=prior_year_ov.water_per_production,
        prior_year_waste_per_production=prior_year_ov.waste_per_production,
        prior_year_energy_per_revenue=prior_year_ov.energy_per_revenue,
        prior_year_ghg_per_revenue=prior_year_ov.ghg_per_revenue,
        prior_year_water_per_revenue=prior_year_ov.water_per_revenue,
        prior_year_waste_per_revenue=prior_year_ov.waste_per_revenue,
        prior_year_energy_gj=prior_year_ov.energy_gj,
        prior_year_ghg_tco2e=prior_year_ov.ghg_tco2e,
        prior_year_water_kl=prior_year_ov.water_kl,
        prior_year_waste_mt=prior_year_ov.waste_mt,
        prior_year_production_mnah=prior_year_ov.production_mnah,
        prior_year_revenue_inr_cr=prior_year_ov.revenue_inr_cr,
        ghg_per_production_target=ghg_per_production_target,
        energy_per_production_target=energy_per_production_target,
        water_per_production_target=water_per_production_target,
        waste_per_production_target=waste_per_production_target,
        ghg_per_revenue_target=ghg_per_revenue_target,
        energy_per_revenue_target=energy_per_revenue_target,
        water_per_revenue_target=water_per_revenue_target,
        waste_per_revenue_target=waste_per_revenue_target,
    )


@router.get("/trend", response_model=list[IntensityTrendPoint])
def intensity_trend(
    period: date,
    months: int = 6,
    location_id: uuid.UUID | None = None,
    period_mode: str = "month",
    current: CurrentUser = Depends(require_roles("Admin", "Manager", "Approver")),
    db: Session = Depends(get_db),
):
    """Trailing N buckets of intensity ratios, each paired with the same
    bucket one year earlier, in one batched query set -- powers the trend
    charts on the Production/Revenue tabs without one round trip per
    bucket. period_mode picks the bucket granularity: 'month' (default),
    'quarter', or 'ytd' (year buckets)."""
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

    by_month = compute_intensity_overview_batch(db, current.tenant_id, location_id, sorted(all_months))
    all_metric_keys = list(_PRODUCTION_METRIC_KEYS.values()) + list(_REVENUE_METRIC_KEYS.values())
    targets_by_metric = active_targets_by_metric(db, current.tenant_id, location_id, all_metric_keys)

    points = []
    for (start, end), (py_start, py_end) in zip(buckets, prior_year_buckets):
        bucket_months = months_in_range(start, end)
        ov = compute_intensity_overview_range(db, current.tenant_id, location_id, bucket_months, by_month=by_month)
        py_ov = compute_intensity_overview_range(
            db, current.tenant_id, location_id, months_in_range(py_start, py_end), by_month=by_month
        )
        points.append(
            IntensityTrendPoint(
                period=end,
                bucket_start=start,
                bucket_end=end,
                ghg_per_production=ov.ghg_per_production,
                energy_per_production=ov.energy_per_production,
                water_per_production=ov.water_per_production,
                waste_per_production=ov.waste_per_production,
                ghg_per_revenue=ov.ghg_per_revenue,
                energy_per_revenue=ov.energy_per_revenue,
                water_per_revenue=ov.water_per_revenue,
                waste_per_revenue=ov.waste_per_revenue,
                prior_year_ghg_per_production=py_ov.ghg_per_production,
                prior_year_energy_per_production=py_ov.energy_per_production,
                prior_year_water_per_production=py_ov.water_per_production,
                prior_year_waste_per_production=py_ov.waste_per_production,
                prior_year_ghg_per_revenue=py_ov.ghg_per_revenue,
                prior_year_energy_per_revenue=py_ov.energy_per_revenue,
                prior_year_water_per_revenue=py_ov.water_per_revenue,
                prior_year_waste_per_revenue=py_ov.waste_per_revenue,
                target_ghg_per_production=target_value_for_bucket(
                    targets_by_metric.get(_PRODUCTION_METRIC_KEYS["ghg"]), _PRODUCTION_METRIC_KEYS["ghg"], bucket_months
                ),
                target_energy_per_production=target_value_for_bucket(
                    targets_by_metric.get(_PRODUCTION_METRIC_KEYS["energy"]), _PRODUCTION_METRIC_KEYS["energy"], bucket_months
                ),
                target_water_per_production=target_value_for_bucket(
                    targets_by_metric.get(_PRODUCTION_METRIC_KEYS["water"]), _PRODUCTION_METRIC_KEYS["water"], bucket_months
                ),
                target_waste_per_production=target_value_for_bucket(
                    targets_by_metric.get(_PRODUCTION_METRIC_KEYS["waste"]), _PRODUCTION_METRIC_KEYS["waste"], bucket_months
                ),
                target_ghg_per_revenue=target_value_for_bucket(
                    targets_by_metric.get(_REVENUE_METRIC_KEYS["ghg"]), _REVENUE_METRIC_KEYS["ghg"], bucket_months
                ),
                target_energy_per_revenue=target_value_for_bucket(
                    targets_by_metric.get(_REVENUE_METRIC_KEYS["energy"]), _REVENUE_METRIC_KEYS["energy"], bucket_months
                ),
                target_water_per_revenue=target_value_for_bucket(
                    targets_by_metric.get(_REVENUE_METRIC_KEYS["water"]), _REVENUE_METRIC_KEYS["water"], bucket_months
                ),
                target_waste_per_revenue=target_value_for_bucket(
                    targets_by_metric.get(_REVENUE_METRIC_KEYS["waste"]), _REVENUE_METRIC_KEYS["waste"], bucket_months
                ),
            )
        )
    return points
