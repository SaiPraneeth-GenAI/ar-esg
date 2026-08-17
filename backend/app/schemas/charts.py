import uuid
from datetime import date, datetime

from pydantic import BaseModel


class ChartMetricOut(BaseModel):
    key: str
    label: str
    unit: str
    group: str  # "GHG" | "Intensity by production" | "Intensity by revenue" | "Safety"


class ChartMetricPoint(BaseModel):
    period: date
    bucket_start: date | None
    bucket_end: date | None
    value: float | None
    prior_year_value: float | None


class ChartMetricDataOut(BaseModel):
    metric: str
    label: str
    unit: str
    period_mode: str
    points: list[ChartMetricPoint]


class ChartConfig(BaseModel):
    metric: str
    chart_kind: str = "bar"  # bar | line
    period_mode: str = "month"  # month | quarter | ytd
    months: int = 6
    location_id: uuid.UUID | None = None


class SavedChartCreate(BaseModel):
    name: str
    description: str | None = None
    config: ChartConfig


class SavedChartUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    config: ChartConfig | None = None


class SavedChartOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    config: ChartConfig
    owner_id: uuid.UUID
    owner_email: str | None
    created_at: datetime
    updated_at: datetime
