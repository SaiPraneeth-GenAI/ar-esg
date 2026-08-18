import uuid
from datetime import date, datetime

from pydantic import BaseModel, model_validator


class MonthlyPhaseEntry(BaseModel):
    period: date
    value: float


class TargetableMetricOut(BaseModel):
    key: str
    label: str
    unit: str
    group: str  # "GHG" | "Intensity by production" | "Intensity by revenue"


class BaselinePreviewRequest(BaseModel):
    location_id: uuid.UUID | None = None
    metric_key: str
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
    metric_key: str
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
    metric_key: str | None = None
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
    rationale: str | None = None


class TargetBulkRowIn(BaseModel):
    row_index: int
    metric_key: str
    location_name: str | None = None  # blank/omitted = org-wide
    baseline_period_start: date
    baseline_period_end: date
    target_period_start: date
    target_period_end: date
    reduction_percentage: float | None = None
    target_value: float | None = None
    rationale: str | None = None


class TargetBulkImportRequest(BaseModel):
    commit: bool = False
    rows: list[TargetBulkRowIn]


class TargetBulkRowResult(BaseModel):
    row_index: int
    status: str  # "valid" | "error" | "created" | "activated"
    metric_key: str
    message: str | None = None
    target_id: uuid.UUID | None = None


class TargetBulkImportResponse(BaseModel):
    rows: list[TargetBulkRowResult]
    activated_count: int
    error_count: int


class TargetOut(BaseModel):
    id: uuid.UUID
    location_id: uuid.UUID | None
    location_name: str | None
    metric_key: str
    metric_label: str
    metric_unit: str
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
    metric_key: str
    months: list[TargetMonthPerformance]
