import uuid
from datetime import date, datetime

from pydantic import BaseModel, model_validator


class MonthlyPhaseEntry(BaseModel):
    period: date
    value: float


class BaselinePreviewRequest(BaseModel):
    location_id: uuid.UUID | None = None
    scope: str  # '1' | '2' | '1_2_combined'
    calculation_method: str | None = None
    metric_type: str  # absolute_tco2e | intensity_tco2e_per_mnah
    baseline_period_start: date
    baseline_period_end: date


class BaselineMonthOut(BaseModel):
    period: date
    value: float | None
    completeness_pct: float | None


class BaselinePreviewResponse(BaseModel):
    ready: bool
    provisional: bool
    baseline_value: float | None
    completeness_pct: float | None
    message: str
    months: list[BaselineMonthOut]


class TargetCreate(BaseModel):
    location_id: uuid.UUID | None = None
    scope: str
    calculation_method: str | None = None
    metric_type: str
    baseline_period_start: date
    baseline_period_end: date
    target_period_start: date
    target_period_end: date
    reduction_percentage: float | None = None
    target_value: float | None = None
    monthly_phasing: list[MonthlyPhaseEntry] = []
    owner_id: uuid.UUID | None = None
    rationale: str | None = None

    @model_validator(mode="after")
    def _check_dates(self):
        if self.baseline_period_end < self.baseline_period_start:
            raise ValueError("baseline_period_end must not be before baseline_period_start")
        if self.target_period_end < self.target_period_start:
            raise ValueError("target_period_end must not be before target_period_start")
        return self


class TargetUpdate(BaseModel):
    """Draft-only edits -- any field may be updated up until activation."""

    location_id: uuid.UUID | None = None
    scope: str | None = None
    calculation_method: str | None = None
    metric_type: str | None = None
    baseline_period_start: date | None = None
    baseline_period_end: date | None = None
    target_period_start: date | None = None
    target_period_end: date | None = None
    reduction_percentage: float | None = None
    target_value: float | None = None
    monthly_phasing: list[MonthlyPhaseEntry] | None = None
    owner_id: uuid.UUID | None = None
    rationale: str | None = None


class TargetActivateRequest(BaseModel):
    rationale: str


class TargetOut(BaseModel):
    id: uuid.UUID
    location_id: uuid.UUID | None
    location_name: str | None
    scope: str
    calculation_method: str | None
    metric_type: str
    baseline_period_start: date
    baseline_period_end: date
    baseline_value: float | None
    baseline_completeness_pct: float | None
    baseline_locked_at: datetime | None
    reduction_percentage: float | None
    target_period_start: date
    target_period_end: date
    target_value: float | None
    monthly_phasing: list[MonthlyPhaseEntry]
    status: str
    owner_id: uuid.UUID | None
    owner_email: str | None
    rationale: str | None
    approved_by: uuid.UUID | None
    approved_by_email: str | None
    approved_at: datetime | None
    boundary_config_hash: str | None
    created_at: datetime
    updated_at: datetime
    current_status_label: str | None = None


class TargetMonthPerformance(BaseModel):
    period: date
    actual: float | None
    target: float | None
    variance_pct: float | None
    status: str
    completeness_pct: float | None


class TargetPerformanceResponse(BaseModel):
    target_id: uuid.UUID
    metric_type: str
    months: list[TargetMonthPerformance]
