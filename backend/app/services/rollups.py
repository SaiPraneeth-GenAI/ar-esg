import uuid
from datetime import date

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.models import Category, DataPoint, Entry, Location, Rollup, Threshold


def month_start(d: date) -> date:
    return d.replace(day=1)


def recompute_rollup(db: Session, tenant_id: uuid.UUID, location_id: uuid.UUID, category_name: str, period: date) -> Rollup:
    """Recomputes and stores the rollup for one tenant/location/category/month.

    Called the moment an entry is approved for that slice -- the dashboard
    reads only from this table, never aggregating raw entries live.
    """
    period = month_start(period)

    data_point_ids = [
        dp.id
        for dp in (
            db.query(DataPoint)
            .join(Category, Category.id == DataPoint.category_id)
            .filter(Category.tenant_id == tenant_id, Category.name == category_name)
            .all()
        )
    ]

    aggregated_value = None
    target_value = None

    if data_point_ids:
        total = (
            db.query(func.sum(Entry.value))
            .filter(
                Entry.data_point_id.in_(data_point_ids),
                Entry.location_id == location_id,
                Entry.status == "Approved",
                Entry.period >= period,
                Entry.period < _next_month(period),
            )
            .scalar()
        )
        aggregated_value = float(total) if total is not None else None

        target_total = (
            db.query(func.sum(Threshold.target_value))
            .filter(Threshold.data_point_id.in_(data_point_ids))
            .scalar()
        )
        target_value = float(target_total) if target_total is not None else None

    rollup = (
        db.query(Rollup)
        .filter(
            Rollup.tenant_id == tenant_id,
            Rollup.location_id == location_id,
            Rollup.category == category_name,
            Rollup.period == period,
        )
        .first()
    )

    if rollup is None:
        rollup = Rollup(
            tenant_id=tenant_id,
            location_id=location_id,
            period=period,
            category=category_name,
            aggregated_value=aggregated_value,
            target_value=target_value,
        )
        db.add(rollup)
    else:
        rollup.aggregated_value = aggregated_value
        rollup.target_value = target_value

    db.commit()
    db.refresh(rollup)
    return rollup


def recompute_rollup_for_entry(db: Session, entry: Entry) -> None:
    """Convenience hook for wherever an entry transitions to Approved."""
    data_point = db.get(DataPoint, entry.data_point_id)
    category = db.get(Category, data_point.category_id)
    recompute_rollup(db, category.tenant_id, entry.location_id, category.name, entry.period)


def _next_month(d: date) -> date:
    if d.month == 12:
        return d.replace(year=d.year + 1, month=1)
    return d.replace(month=d.month + 1)
