import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field


class SiteOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    is_synthetic: bool


class SourceIn(BaseModel):
    site_id: uuid.UUID
    name: str = Field(min_length=2, max_length=120)
    source_type: str
    supplier: str | None = None
    renewable: bool = False
    active: bool = True


class SourceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    supplier: str | None = None
    renewable: bool | None = None
    active: bool | None = None


class SourceOut(BaseModel):
    id: uuid.UUID
    site_id: uuid.UUID
    name: str
    source_type: str
    supplier: str | None
    renewable: bool
    active: bool
    meter_count: int = 0


class MeterIn(BaseModel):
    site_id: uuid.UUID
    source_id: uuid.UUID
    meter_code: str = Field(min_length=2, max_length=80)
    name: str = Field(min_length=2, max_length=120)
    unit: str = "kWh"
    direction: str = "import"
    active: bool = True


class MeterUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    source_id: uuid.UUID | None = None
    unit: str | None = None
    direction: str | None = None
    active: bool | None = None


class MeterOut(BaseModel):
    id: uuid.UUID
    site_id: uuid.UUID
    source_id: uuid.UUID
    source_name: str
    meter_code: str
    name: str
    unit: str
    direction: str
    active: bool


class ReadingIn(BaseModel):
    site_id: uuid.UUID
    meter_id: uuid.UUID
    period: date
    value: float = Field(ge=0)
    unit: str = "kWh"
    evidence_reference: str | None = None
    status: str = "review"


class ReadingUpdate(BaseModel):
    value: float | None = Field(default=None, ge=0)
    unit: str | None = None
    evidence_reference: str | None = None
    status: str | None = None


class ReadingOut(BaseModel):
    id: uuid.UUID
    site_id: uuid.UUID
    source_id: uuid.UUID
    source_name: str
    source_type: str
    meter_id: uuid.UUID
    meter_code: str
    meter_name: str
    period: date
    value: float
    normalized_kwh: float | None
    unit: str
    evidence_reference: str | None
    status: str
    quality_flags: list[str]
    source_row: int | None


class ImportRowIn(BaseModel):
    row_index: int
    meter_code: str
    period: str
    value: str
    unit: str = "kWh"
    evidence_reference: str | None = None


class ImportRequest(BaseModel):
    site_id: uuid.UUID
    filename: str = Field(min_length=1, max_length=255)
    commit: bool = False
    rows: list[ImportRowIn]


class ImportRowResult(BaseModel):
    row_index: int
    status: str
    meter_code: str
    meter_name: str | None = None
    period: date | None = None
    value: float | None = None
    normalized_kwh: float | None = None
    message: str | None = None


class ImportResponse(BaseModel):
    rows: list[ImportRowResult]
    valid_count: int
    error_count: int
    imported_count: int


class ReconciliationOut(BaseModel):
    source_id: uuid.UUID
    source_name: str
    source_type: str
    meter_total_kwh: float
    reference_type: str | None
    reference_value_kwh: float | None
    variance_kwh: float | None
    variance_pct: float | None
    status: str
    message: str
    evidence_reference: str | None


class TraceInputOut(BaseModel):
    reading_id: uuid.UUID
    meter_code: str
    source_name: str
    value_kwh: float
    evidence_reference: str | None
    source_row: int | None


class TraceOut(BaseModel):
    metric_name: str
    result_value: float
    unit: str
    activity_value_kwh: float
    factor_value: float
    factor_unit: str
    factor_source: str
    formula: str
    inputs: list[TraceInputOut]


class AssuranceSummaryOut(BaseModel):
    completeness_pct: float
    evidence_coverage_pct: float
    readings_received: int
    readings_expected: int
    sources_reconciled: int
    sources_total: int
    open_exceptions: int
    reporting_status: str


class WorkspaceOut(BaseModel):
    period: date
    sites: list[SiteOut]
    active_site: SiteOut
    summary: AssuranceSummaryOut
    sources: list[SourceOut]
    meters: list[MeterOut]
    readings: list[ReadingOut]
    reconciliations: list[ReconciliationOut]
    trace: TraceOut
    latest_import_at: datetime | None = None
