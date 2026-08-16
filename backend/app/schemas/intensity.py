from datetime import date

from pydantic import BaseModel


class IntensityOverviewOut(BaseModel):
    period: date
    energy_gj: float | None
    ghg_tco2e: float | None
    water_kl: float | None
    waste_mt: float | None
    production_mnah: float | None
    revenue_inr_cr: float | None
    energy_per_production: float | None
    ghg_per_production: float | None
    water_per_production: float | None
    waste_per_production: float | None
    energy_per_revenue: float | None
    ghg_per_revenue: float | None
    water_per_revenue: float | None
    waste_per_revenue: float | None
    prior_energy_per_production: float | None = None
    prior_ghg_per_production: float | None = None
    prior_water_per_production: float | None = None
    prior_waste_per_production: float | None = None
    prior_energy_per_revenue: float | None = None
    prior_ghg_per_revenue: float | None = None
    prior_water_per_revenue: float | None = None
    prior_waste_per_revenue: float | None = None
    prior_energy_gj: float | None = None
    prior_ghg_tco2e: float | None = None
    prior_water_kl: float | None = None
    prior_waste_mt: float | None = None
    prior_production_mnah: float | None = None
    prior_revenue_inr_cr: float | None = None
