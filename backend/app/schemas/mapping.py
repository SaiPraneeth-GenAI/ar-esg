import uuid
from datetime import date, datetime

from pydantic import BaseModel


class SheetInput(BaseModel):
    name: str
    filename: str
    headers: list[str]


class ColumnSuggestion(BaseModel):
    header: str
    target: str | None  # "period" | "note" | data_point_id (as string) | None (unmatched)
    target_type: str  # "metadata" | "data_point" | "unmatched"
    data_point_name: str | None = None
    score: float
    rule: str  # "exact_alias" | "fuzzy" | "memory" | "ai" | "no_match" | "template"


class SheetDetectionResult(BaseModel):
    sheet_name: str
    header_fingerprint: str
    category_id: uuid.UUID | None
    category_name: str | None
    category_score: float
    category_rule: str
    columns: list[ColumnSuggestion]
    inferred_period: date | None
    from_template: bool
    template_id: uuid.UUID | None = None


class DetectRequest(BaseModel):
    sheets: list[SheetInput]


class DetectResponse(BaseModel):
    sheets: list[SheetDetectionResult]


class SaveTemplateRequest(BaseModel):
    category_id: uuid.UUID
    header_fingerprint: str
    column_mapping: dict[str, str]


class MappingTemplateOut(BaseModel):
    id: uuid.UUID
    category_id: uuid.UUID
    category_name: str
    header_fingerprint: str
    column_mapping: dict[str, str]
    created_at: datetime
    updated_at: datetime
