import uuid
from datetime import date, datetime

from pydantic import BaseModel


class PeerCompanyCreate(BaseModel):
    name: str
    industry: str | None = None
    country: str | None = None


class PeerCompanyOut(BaseModel):
    id: uuid.UUID
    name: str
    industry: str | None
    country: str | None
    created_at: datetime
    period_count: int = 0


class PeerDataCreate(BaseModel):
    period: date
    metrics: dict[str, float]
    data_source: str | None = None
    source_link: str | None = None
    data_confidence: str | None = None  # verified | self_reported | estimated
    notes: str | None = None


class PeerDataOut(BaseModel):
    id: uuid.UUID
    peer_company_id: uuid.UUID
    period: date
    metrics: dict[str, float]
    data_source: str | None
    source_link: str | None
    data_confidence: str | None
    notes: str | None
    uploaded_by_email: str | None
    uploaded_at: datetime
    updated_at: datetime


class PeerExtractRow(BaseModel):
    key: str
    label: str
    unit: str
    group: str
    amara_raja_value: float | None
    peer_value: float | None  # AI-extracted from the uploaded PDF -- null if not found


class PeerExtractOut(BaseModel):
    peer_company_id: uuid.UUID
    peer_company_name: str
    year: int
    source_filename: str
    rows: list[PeerExtractRow]


class PeerCompareYearMetric(BaseModel):
    key: str
    label: str
    unit: str
    amara_raja_value: float | None
    peer_value: float | None


class PeerCompareYearGroup(BaseModel):
    group: str
    metrics: list[PeerCompareYearMetric]


class PeerCompareYearOut(BaseModel):
    year: int
    peer_company_name: str
    groups: list[PeerCompareYearGroup]
