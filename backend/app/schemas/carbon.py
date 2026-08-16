import uuid
from datetime import date, datetime

from pydantic import BaseModel


class CarbonPreviewRequest(BaseModel):
    data_point_id: uuid.UUID
    location_id: uuid.UUID
    period: date
    value: float
    unit: str | None = None  # defaults to the data point's own unit if omitted


class CarbonPreviewResponse(BaseModel):
    data_point_name: str
    scope: int | None
    status: str  # calculated | unresolved | not_a_ghg_source
    activity_value: float
    activity_unit: str
    normalized_activity_value: float | None
    normalized_activity_unit: str | None
    factor_version: str | None
    factor_value: float | None
    factor_unit: str | None
    factor_source: str | None
    calculation_method: str | None
    formula: str | None
    emissions_kgco2e: float | None
    emissions_tco2e: float | None
    resolution_reason: str | None
    warning: str | None = None


class EmissionCalculationOut(BaseModel):
    id: uuid.UUID
    entry_id: uuid.UUID
    data_point_id: uuid.UUID
    data_point_name: str
    location_id: uuid.UUID
    location_name: str
    reporting_period: date
    scope: int
    calculation_method: str | None
    status: str
    activity_value: float
    activity_unit: str
    normalized_activity_value: float | None
    normalized_activity_unit: str | None
    factor_version: str | None
    factor_value: float | None
    factor_unit: str | None
    factor_source: str | None
    factor_effective_year: int | None
    emissions_kgco2e: float | None
    emissions_tco2e: float | None
    formula: str | None
    resolution_reason: str | None
    calculated_at: datetime
    calculated_by_email: str | None
    supersedes_calculation_id: uuid.UUID | None


class RecalculateResponse(BaseModel):
    calculated_count: int
    unresolved_count: int
    skipped_not_ghg_count: int
    results: list[EmissionCalculationOut]


class CarbonOverviewSource(BaseModel):
    data_point_name: str
    scope: int
    calculation_method: str | None
    emissions_tco2e: float
    entry_count: int


class CarbonOverview(BaseModel):
    period: date | None
    scope1_tco2e: float | None
    scope2_location_based_tco2e: float | None
    scope2_market_based_tco2e: float | None
    scope1_2_location_based_tco2e: float | None
    production_value: float | None
    production_unit: str | None
    intensity_tco2e_per_mnah: float | None
    unresolved_count: int
    sources: list[CarbonOverviewSource]
