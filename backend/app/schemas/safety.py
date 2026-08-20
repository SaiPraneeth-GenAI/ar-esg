from datetime import date

from pydantic import BaseModel

from app.schemas.carbon import TargetComparison


class SafetyMetricOut(BaseModel):
    name: str
    value: float | None
    unit: str
    prior_value: float | None
    prior_year_value: float | None = None
    target: TargetComparison | None = None


class SafetyOverviewOut(BaseModel):
    period: date
    period_mode: str = "month"
    period_start: date | None = None
    period_end: date | None = None
    metrics: list[SafetyMetricOut]


class SafetyTrendPoint(BaseModel):
    period: date
    bucket_start: date | None = None
    bucket_end: date | None = None
    values: dict[str, float | None]  # metric name -> value for that bucket
    prior_year_values: dict[str, float | None] = {}  # same bucket, one year back
