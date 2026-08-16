import uuid
from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, require_roles
from app.db.session import get_db
from app.schemas.intensity import IntensityOverviewOut, IntensityTrendPoint
from app.services.carbon_calculation import prior_month, prior_year
from app.services.intensity_calculation import compute_intensity_overview_batch
from app.services.rollups import month_start

router = APIRouter(prefix="/intensity", tags=["intensity"])


def _trailing_months(period: date, count: int) -> list[date]:
    months = []
    cursor = period
    for _ in range(count):
        months.append(cursor)
        year = cursor.year - (1 if cursor.month == 1 else 0)
        month = 12 if cursor.month == 1 else cursor.month - 1
        cursor = cursor.replace(year=year, month=month)
    return list(reversed(months))


@router.get("/overview", response_model=IntensityOverviewOut)
def intensity_overview(
    period: date,
    location_id: uuid.UUID | None = None,
    current: CurrentUser = Depends(require_roles("Admin", "Manager", "Approver")),
    db: Session = Depends(get_db),
):
    period = month_start(period)
    periods = [period, prior_month(period), prior_year(period)]
    by_period = compute_intensity_overview_batch(db, current.tenant_id, location_id, periods)
    current_ov = by_period[periods[0]]
    prior_ov = by_period[periods[1]]
    prior_year_ov = by_period[periods[2]]

    return IntensityOverviewOut(
        period=current_ov.period,
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
    )


@router.get("/trend", response_model=list[IntensityTrendPoint])
def intensity_trend(
    period: date,
    months: int = 6,
    location_id: uuid.UUID | None = None,
    current: CurrentUser = Depends(require_roles("Admin", "Manager", "Approver")),
    db: Session = Depends(get_db),
):
    """Trailing N months of intensity ratios in one batched query set --
    powers the trend charts on the Production/Revenue tabs without one
    full /intensity/overview round trip per bar."""
    period = month_start(period)
    trailing = _trailing_months(period, min(max(months, 1), 24))
    by_period = compute_intensity_overview_batch(db, current.tenant_id, location_id, trailing)
    return [
        IntensityTrendPoint(
            period=p,
            ghg_per_production=by_period[p].ghg_per_production,
            ghg_per_revenue=by_period[p].ghg_per_revenue,
        )
        for p in trailing
    ]
