import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.db.models import Category, DataPoint, Entry
from app.services.carbon_calculation import to_decimal

CATEGORY_NAME = "Safety"
METRIC_NAMES = ["Fatality", "LTIFR", "Defensive Driving Training", "Unsafe Conditions", "Near Miss"]
METRIC_RANGE_AGGREGATION = {"LTIFR": "average", "Defensive Driving Training": "average"}


def metric_values_batch(
    db: Session, tenant_id: uuid.UUID, location_id: uuid.UUID | None, periods: list[date]
) -> dict[str, dict[date, tuple[float | None, str]]]:
    data_points = (
        db.query(DataPoint)
        .join(Category, Category.id == DataPoint.category_id)
        .filter(Category.tenant_id == tenant_id, Category.name == CATEGORY_NAME, DataPoint.name.in_(METRIC_NAMES))
        .all()
    )
    dp_by_name = {dp.name: dp for dp in data_points}
    entry_q = db.query(Entry).filter(
        Entry.data_point_id.in_([dp.id for dp in data_points]), Entry.status == "Approved", Entry.period.in_(periods)
    )
    if location_id is not None:
        entry_q = entry_q.filter(Entry.location_id == location_id)
    entries_by_dp_period: dict[tuple, list] = {}
    for entry in entry_q.all():
        entries_by_dp_period.setdefault((entry.data_point_id, entry.period), []).append(entry)

    result: dict[str, dict[date, tuple[float | None, str]]] = {}
    for name in METRIC_NAMES:
        dp = dp_by_name.get(name)
        per_period: dict[date, tuple[float | None, str]] = {}
        for period in periods:
            entries = entries_by_dp_period.get((dp.id, period)) if dp else None
            if not entries:
                per_period[period] = (None, dp.unit or "" if dp else "")
                continue
            total = sum((to_decimal(entry.value) for entry in entries if entry.value is not None), Decimal("0"))
            per_period[period] = (float(total), dp.unit or "")
        result[name] = per_period
    return result


def aggregate_metric_range(
    name: str, per_period: dict[date, tuple[float | None, str]], months: list[date]
) -> tuple[float | None, str]:
    values = [per_period[month][0] for month in months if per_period[month][0] is not None]
    unit = next((per_period[month][1] for month in months if per_period[month][1]), "")
    if not values:
        return None, unit
    if METRIC_RANGE_AGGREGATION.get(name) == "average":
        return sum(values) / len(values), unit
    return sum(values), unit
