import uuid
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, require_roles
from app.db.models import Category, DataPoint, Entry
from app.db.session import get_db
from app.schemas.safety import SafetyMetricOut, SafetyOverviewOut, SafetyTrendPoint
from app.services.carbon_calculation import prior_month, prior_year, to_decimal
from app.services.rollups import month_start

router = APIRouter(prefix="/safety", tags=["safety"])

CATEGORY_NAME = "Safety"

# Safety metrics are categorically different units (a count, a rate, a
# percentage) that must never be summed into one blended "total" the way
# Water's four sub-sources correctly are -- each is read and shown on its
# own, one Entry per data point per period (not a Rollup category sum).
METRIC_NAMES = ["Fatality", "LTIFR", "Defensive Driving Training", "Unsafe Conditions", "Near Miss"]


def _metric_values_batch(
    db: Session, tenant_id: uuid.UUID, location_id: uuid.UUID | None, periods: list[date]
) -> dict[str, dict[date, tuple[float | None, str]]]:
    """{metric_name: {period: (value, unit)}} for every metric and period
    in one DataPoint query + one Entry query, not one pair per metric per
    period."""
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
    for e in entry_q.all():
        entries_by_dp_period.setdefault((e.data_point_id, e.period), []).append(e)

    result: dict[str, dict[date, tuple[float | None, str]]] = {}
    for name in METRIC_NAMES:
        dp = dp_by_name.get(name)
        per_period: dict[date, tuple[float | None, str]] = {}
        for p in periods:
            if dp is None:
                per_period[p] = (None, "")
                continue
            entries = entries_by_dp_period.get((dp.id, p))
            if not entries:
                per_period[p] = (None, dp.unit or "")
                continue
            total = sum((to_decimal(e.value) for e in entries if e.value is not None), Decimal("0"))
            per_period[p] = (float(total), dp.unit or "")
        result[name] = per_period
    return result


@router.get("/overview", response_model=SafetyOverviewOut)
def safety_overview(
    period: date,
    location_id: uuid.UUID | None = None,
    current: CurrentUser = Depends(require_roles("Admin", "Manager", "Approver")),
    db: Session = Depends(get_db),
):
    period = month_start(period)
    periods = [period, prior_month(period), prior_year(period)]
    values = _metric_values_batch(db, current.tenant_id, location_id, periods)

    metrics = []
    for name in METRIC_NAMES:
        value, unit = values[name][periods[0]]
        prior_value, _ = values[name][periods[1]]
        prior_year_value, _ = values[name][periods[2]]
        metrics.append(
            SafetyMetricOut(name=name, value=value, unit=unit, prior_value=prior_value, prior_year_value=prior_year_value)
        )

    return SafetyOverviewOut(period=period, metrics=metrics)


def _trailing_months(period: date, count: int) -> list[date]:
    months = []
    cursor = period
    for _ in range(count):
        months.append(cursor)
        year = cursor.year - (1 if cursor.month == 1 else 0)
        month = 12 if cursor.month == 1 else cursor.month - 1
        cursor = cursor.replace(year=year, month=month)
    return list(reversed(months))


@router.get("/trend", response_model=list[SafetyTrendPoint])
def safety_trend(
    period: date,
    months: int = 6,
    location_id: uuid.UUID | None = None,
    current: CurrentUser = Depends(require_roles("Admin", "Manager", "Approver")),
    db: Session = Depends(get_db),
):
    period = month_start(period)
    trailing = _trailing_months(period, min(max(months, 1), 24))
    values = _metric_values_batch(db, current.tenant_id, location_id, trailing)
    return [
        SafetyTrendPoint(period=p, values={name: values[name][p][0] for name in METRIC_NAMES})
        for p in trailing
    ]
