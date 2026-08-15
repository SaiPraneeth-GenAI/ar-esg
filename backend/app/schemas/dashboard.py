from datetime import date

from pydantic import BaseModel


class DashboardCard(BaseModel):
    category: str
    metric_type: str
    label: str
    value: float
    unit: str
    status: str
    comparison_label: str
    period: date


class DashboardSummary(BaseModel):
    period: date | None
    cards: list[DashboardCard]


class DrilldownEntry(BaseModel):
    location_name: str
    data_point_name: str
    value: float
    unit: str
    period: date
    method_of_entry: str


class DrilldownResponse(BaseModel):
    category: str
    metric_type: str
    period: date
    entries: list[DrilldownEntry]
    production_entries: list[DrilldownEntry]
