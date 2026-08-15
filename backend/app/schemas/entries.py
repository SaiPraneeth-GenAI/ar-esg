import uuid
from datetime import date, datetime

from pydantic import BaseModel


class DataPointOut(BaseModel):
    id: uuid.UUID
    name: str
    unit: str | None
    input_type: str | None
    default_mode: str
    is_provisional: bool


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


class SubmitRequest(BaseModel):
    category: str
    period: date
    location_id: uuid.UUID


class RejectRequest(BaseModel):
    reject_note: str


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
