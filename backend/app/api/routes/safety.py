import uuid
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, require_roles
from app.db.models import Category, DataPoint, Entry
from app.db.session import get_db
from app.schemas.safety import SafetyMetricOut, SafetyOverviewOut
from app.services.carbon_calculation import prior_month, to_decimal
from app.services.rollups import month_start

router = APIRouter(prefix="/safety", tags=["safety"])

CATEGORY_NAME = "Safety"

# Safety metrics are categorically different units (a count, a rate, a
# percentage) that must never be summed into one blended "total" the way
# Water's four sub-sources correctly are -- each is read and shown on its
# own, one Entry per data point per period (not a Rollup category sum).
METRIC_NAMES = ["Fatality", "LTIFR", "Defensive Driving Training", "Unsafe Conditions", "Near Miss"]


def _metric_value(db: Session, tenant_id: uuid.UUID, location_id: uuid.UUID | None, period: date, dp_name: str) -> tuple[float | None, str]:
    dp = (
        db.query(DataPoint)
        .join(Category, Category.id == DataPoint.category_id)
        .filter(Category.tenant_id == tenant_id, Category.name == CATEGORY_NAME, DataPoint.name == dp_name)
        .first()
    )
    if dp is None:
        return None, ""

    q = db.query(Entry).filter(Entry.data_point_id == dp.id, Entry.status == "Approved", Entry.period == period)
    if location_id is not None:
        q = q.filter(Entry.location_id == location_id)
    entries = q.all()
    if not entries:
        return None, dp.unit or ""

    total = sum((to_decimal(e.value) for e in entries if e.value is not None), Decimal("0"))
    return float(total), dp.unit or ""


@router.get("/overview", response_model=SafetyOverviewOut)
def safety_overview(
    period: date,
    location_id: uuid.UUID | None = None,
    current: CurrentUser = Depends(require_roles("Admin", "Manager", "Approver")),
    db: Session = Depends(get_db),
):
    period = month_start(period)
    prior = prior_month(period)

    metrics = []
    for name in METRIC_NAMES:
        value, unit = _metric_value(db, current.tenant_id, location_id, period, name)
        prior_value, _ = _metric_value(db, current.tenant_id, location_id, prior, name)
        metrics.append(SafetyMetricOut(name=name, value=value, unit=unit, prior_value=prior_value))

    return SafetyOverviewOut(period=period, metrics=metrics)
