from datetime import date

from pydantic import BaseModel


class SafetyMetricOut(BaseModel):
    name: str
    value: float | None
    unit: str
    prior_value: float | None


class SafetyOverviewOut(BaseModel):
    period: date
    metrics: list[SafetyMetricOut]
