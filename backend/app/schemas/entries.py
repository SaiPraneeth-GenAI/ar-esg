import uuid
from datetime import date, datetime

from pydantic import BaseModel


class DataPointOut(BaseModel):
    id: uuid.UUID
    name: str
    unit: str | None
    input_type: str | None
    is_provisional: bool
    tooltip: str | None = None
    example: str | None = None


class CategoryOut(BaseModel):
    id: uuid.UUID
    name: str
    display_order: int | None
    is_provisional: bool
    data_points: list[DataPointOut]


class EntryUpsertRequest(BaseModel):
    data_point_id: uuid.UUID
    location_id: uuid.UUID
    period: date
    value: float | None = None
    note: str | None = None
    meter_id: str | None = None


class EntryOut(BaseModel):
    id: uuid.UUID
    data_point_id: uuid.UUID
    data_point_name: str
    category_name: str
    location_id: uuid.UUID
    location_name: str
    period: date
    value: float | None
    status: str
    note: str | None
    submitted_by: uuid.UUID | None
    submitted_by_email: str | None
    latest_rejection_note: str | None = None


class SubmitRequest(BaseModel):
    category: str
    period: date
    location_id: uuid.UUID


class RejectRequest(BaseModel):
    reject_note: str


class BulkApproveRequest(BaseModel):
    entry_ids: list[uuid.UUID]


class BulkRejectRequest(BaseModel):
    entry_ids: list[uuid.UUID]
    reject_note: str


class BulkDecisionSkip(BaseModel):
    entry_id: uuid.UUID
    reason: str


class BulkDecisionResponse(BaseModel):
    processed_count: int
    skipped: list[BulkDecisionSkip]


class AuditLogOut(BaseModel):
    id: uuid.UUID
    actor: str | None
    action: str
    old_value: str | None
    new_value: str | None
    timestamp: datetime


class AttachmentOut(BaseModel):
    id: uuid.UUID
    file_url: str
    file_type: str | None
    uploaded_by: uuid.UUID | None
    uploaded_at: datetime


class LastValueOut(BaseModel):
    value: float | None
    period: date | None


class LastValueEntry(BaseModel):
    data_point_id: uuid.UUID
    value: float | None
    period: date | None


class BulkImportRowIn(BaseModel):
    row_index: int
    data_point_name: str
    period_iso: str = ""
    # Separate Year/Month columns -- the alternative to period_iso for a
    # file laid out as a time series (one row per data point per month),
    # matching how the template now presents the period. Used only when
    # period_iso is blank.
    year: int | None = None
    month: int | None = None
    value_raw: str
    unit_raw: str | None = None
    note: str | None = None
    # Only meaningful when BulkImportRequest.category is None (the "all
    # categories" upload) -- some field names exist in more than one
    # category (e.g. "Total Treated Effluent Generated" under both
    # ETP-Water and STP-Water), so name alone can be ambiguous.
    category: str | None = None


class BulkImportRequest(BaseModel):
    # None means "all categories" -- rows are matched by (row.category,
    # data_point_name) instead of being pre-scoped to one category.
    category: str | None = None
    location_id: uuid.UUID
    # Used for any row that doesn't specify its own period -- i.e. a file
    # with no Period column at all, which is the common single-month case.
    default_period: str | None = None
    commit: bool = False
    rows: list[BulkImportRowIn]


class BulkImportRowResult(BaseModel):
    row_index: int
    status: str  # "valid" | "error" | "created"
    data_point_name: str
    period: date | None
    value: float | None
    message: str | None = None
    entry_id: uuid.UUID | None = None
    # Set when the uploaded unit differed from what the data point expects
    # but was successfully converted (e.g. "Converted 1.5 KL → 1500 litres").
    unit_note: str | None = None
    # Set on a unit error -- the exact unit string this data point expects,
    # so the UI (and the annotated file re-download) can suggest it
    # directly instead of just saying "wrong unit".
    suggested_unit: str | None = None
    # Only set in "all categories" mode -- which category this row's
    # data point actually belongs to, so the UI can show it even when the
    # uploaded row didn't specify one.
    category: str | None = None


class BulkImportResponse(BaseModel):
    rows: list[BulkImportRowResult]
    valid_count: int
    error_count: int
    created_count: int
