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


class BreakdownDimensionOut(BaseModel):
    key: str
    label: str


class BreakdownSlice(BaseModel):
    label: str
    value: float


class BreakdownDataOut(BaseModel):
    dimension: str
    label: str
    unit: str
    period_mode: str
    slices: list[BreakdownSlice]


class ChartConfig(BaseModel):
    # "What question do you want to answer?" -- picks which fields below
    # apply and how the chart renders (line/bar over time for trend, pie
    # for breakdown, bar-of-current-values for comparison).
    question_type: str = "trend"  # trend | breakdown | comparison

    # trend
    metric: str | None = None
    chart_kind: str = "bar"  # bar | line
    period_mode: str = "month"  # month | quarter | ytd
    months: int = 6

    # breakdown
    dimension: str | None = None

    # comparison
    comparison_mode: str = "metrics"  # metrics | peers
    metrics: list[str] | None = None  # comparison_mode == "metrics": 2-6 of our own metrics, current period
    compare_peer_ids: list[uuid.UUID] | None = None  # comparison_mode == "peers": one metric, us + these peer companies

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
