import uuid
from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, require_roles
from app.db.session import get_db
from app.schemas.intensity import IntensityOverviewOut
from app.services.carbon_calculation import prior_month
from app.services.intensity_calculation import compute_intensity_overview
from app.services.rollups import month_start

router = APIRouter(prefix="/intensity", tags=["intensity"])


@router.get("/overview", response_model=IntensityOverviewOut)
def intensity_overview(
    period: date,
    location_id: uuid.UUID | None = None,
    current: CurrentUser = Depends(require_roles("Admin", "Manager", "Approver")),
    db: Session = Depends(get_db),
):
    period = month_start(period)
    current_ov = compute_intensity_overview(db, current.tenant_id, location_id, period)
    prior_ov = compute_intensity_overview(db, current.tenant_id, location_id, prior_month(period))

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
    )
