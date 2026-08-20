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


class CarbonTrendPoint(BaseModel):
    period: date
    bucket_start: date | None = None
    bucket_end: date | None = None
    scope1_tco2e: float | None
    scope2_location_based_tco2e: float | None
    scope1_2_location_based_tco2e: float | None
    # Always None -- no Scope 3 calculation exists in this platform yet.
    # Exposed as an explicit, honestly-empty field (not omitted) so the
    # dashboard can offer it as a real, clearly-labeled "not tracked yet"
    # option instead of silently pretending it doesn't exist.
    scope3_tco2e: float | None
    intensity_tco2e_per_mnah: float | None
    # The same bucket, one year back -- lets the chart draw a same-bucket
    # year-over-year comparison without a second round trip.
    prior_year_scope1_tco2e: float | None = None
    prior_year_scope2_location_based_tco2e: float | None = None
    prior_year_scope1_2_location_based_tco2e: float | None = None
    prior_year_intensity_tco2e_per_mnah: float | None = None
    # This bucket's active target, if one is set and its period covers this
    # bucket -- None (not zero) when no target applies here, so the chart
    # can draw a reference line only where a real commitment exists.
    target_scope1_tco2e: float | None = None
    target_scope2_location_based_tco2e: float | None = None
    target_scope1_2_location_based_tco2e: float | None = None
    target_intensity_tco2e_per_mnah: float | None = None


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


class TargetComparison(BaseModel):
    target_id: uuid.UUID
    # None only when status is "Not started yet"/"Target period ended" and
    # the target itself has no annual figure recorded (shouldn't normally
    # happen for an active target, but the type reflects what's possible).
    target_value: float | None
    status: str  # Within safe limits | Exceeded | Not enough data | Not started yet | Target period ended


class TargetStatusOut(BaseModel):
    target_id: uuid.UUID
    metric_key: str
    label: str
    unit: str
    actual: float | None
    target_value: float
    status: str


class CarbonOverview(BaseModel):
    period: date | None
    period_mode: str = "month"
    period_start: date | None = None
    period_end: date | None = None
    scope1_tco2e: float | None
    scope2_location_based_tco2e: float | None
    scope2_market_based_tco2e: float | None
    scope1_2_location_based_tco2e: float | None
    prior_scope1_2_location_based_tco2e: float | None
    prior_intensity_tco2e_per_mnah: float | None
    prior_year_scope1_2_location_based_tco2e: float | None = None
    prior_year_intensity_tco2e_per_mnah: float | None = None
    prior_scope1_tco2e: float | None = None
    prior_year_scope1_tco2e: float | None = None
    prior_scope2_location_based_tco2e: float | None = None
    prior_year_scope2_location_based_tco2e: float | None = None
    production_value: float | None
    production_unit: str | None
    intensity_tco2e_per_mnah: float | None
    unresolved_count: int
    calculated_count: int
    completeness_pct: float | None
    sources: list[CarbonOverviewSource]
    insight: str | None
    scope1_2_target: TargetComparison | None = None
    intensity_target: TargetComparison | None = None
    scope1_target: TargetComparison | None = None
    scope2_target: TargetComparison | None = None
    all_targets: list[TargetStatusOut] = []


class AiInsightOut(BaseModel):
    insight: str | None
