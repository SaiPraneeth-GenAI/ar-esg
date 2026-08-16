from datetime import date

from pydantic import BaseModel


class SafetyMetricOut(BaseModel):
    name: str
    value: float | None
    unit: str
    prior_value: float | None
    prior_year_value: float | None = None


class SafetyOverviewOut(BaseModel):
    period: date
    period_mode: str = "month"
    period_start: date | None = None
    period_end: date | None = None
    metrics: list[SafetyMetricOut]


class SafetyTrendPoint(BaseModel):
    period: date
    values: dict[str, float | None]  # metric name -> value for that month
