import uuid
from datetime import date

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.models import Category, DataPoint, Entry, Location, Rollup, Threshold


def month_start(d: date) -> date:
    return d.replace(day=1)


def recompute_rollup(
    db: Session, tenant_id: uuid.UUID, location_id: uuid.UUID, category_name: str, period: date, commit: bool = True
) -> Rollup:
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

    if commit:
        db.commit()
        db.refresh(rollup)
    return rollup


def recompute_rollup_for_entry(db: Session, entry: Entry, commit: bool = True) -> None:
    """Convenience hook for wherever an entry transitions to Approved."""
    data_point = db.get(DataPoint, entry.data_point_id)
    category = db.get(Category, data_point.category_id)
    recompute_rollup(db, category.tenant_id, entry.location_id, category.name, entry.period, commit=commit)


def recompute_rollups_for_entries(db: Session, entries: list[Entry]) -> None:
    """Batched version of recompute_rollup_for_entry() for approving many
    entries at once (bulk upload auto-approve, bulk-approve action).

    Deduping to distinct (tenant, location, category, month) buckets isn't
    enough on its own -- a 25-month, 10-category bulk file touches on the
    order of hundreds of buckets, and recompute_rollup() runs 3-4 queries
    per bucket. That's hundreds of round trips that never show up as a
    commit, so the earlier per-row-commit fix didn't touch it -- this was
    the actual remaining wall-clock cost on a large auto-approving file.
    Every bucket is computed here from a fixed number of grouped queries
    instead, so the query count no longer scales with the row count."""
    if not entries:
        return

    dp_ids = {e.data_point_id for e in entries}
    dps = {dp.id: dp for dp in db.query(DataPoint).filter(DataPoint.id.in_(dp_ids)).all()}
    category_ids = {dp.category_id for dp in dps.values()}
    categories = {c.id: c for c in db.query(Category).filter(Category.id.in_(category_ids)).all()}

    buckets: set[tuple[uuid.UUID, uuid.UUID, str, date]] = set()
    for entry in entries:
        dp = dps.get(entry.data_point_id)
        category = categories.get(dp.category_id) if dp else None
        if category is None:
            continue
        buckets.add((category.tenant_id, entry.location_id, category.name, month_start(entry.period)))

    if not buckets:
        return

    tenant_ids = {b[0] for b in buckets}
    location_ids = {b[1] for b in buckets}
    category_names = {b[2] for b in buckets}
    periods = {b[3] for b in buckets}

    # Every data point in every touched category, once -- was one query per
    # bucket (recomputed from scratch each time even though many buckets
    # share the same category).
    category_dps = (
        db.query(DataPoint.id, Category.tenant_id, Category.name)
        .join(Category, Category.id == DataPoint.category_id)
        .filter(Category.tenant_id.in_(tenant_ids), Category.name.in_(category_names))
        .all()
    )
    dp_ids_by_bucket_cat: dict[tuple[uuid.UUID, str], list[uuid.UUID]] = {}
    all_dp_ids: set[uuid.UUID] = set()
    for dp_id, tenant_id, cat_name in category_dps:
        dp_ids_by_bucket_cat.setdefault((tenant_id, cat_name), []).append(dp_id)
        all_dp_ids.add(dp_id)

    # Approved-value sums for every (location, data point, month) in one
    # grouped query, instead of one SUM query per bucket. Entry.period is
    # always stored as a month's 1st (month_start is a no-op on real rows),
    # so grouping on it directly is equivalent to the per-bucket
    # [period, next_month) range scan it replaces.
    value_sums: dict[tuple[uuid.UUID, uuid.UUID, date], float] = {}
    if all_dp_ids:
        rows = (
            db.query(Entry.location_id, Entry.data_point_id, Entry.period, func.sum(Entry.value))
            .filter(
                Entry.data_point_id.in_(all_dp_ids),
                Entry.location_id.in_(location_ids),
                Entry.status == "Approved",
                Entry.period.in_(periods),
            )
            .group_by(Entry.location_id, Entry.data_point_id, Entry.period)
            .all()
        )
        for loc_id, dp_id, period, total in rows:
            value_sums[(loc_id, dp_id, period)] = float(total) if total is not None else 0.0

    # Target sums per data point (not period-scoped, matching the original
    # per-bucket query), once for every touched data point instead of once
    # per bucket.
    target_by_dp: dict[uuid.UUID, float] = {}
    if all_dp_ids:
        for dp_id, total in db.query(Threshold.data_point_id, func.sum(Threshold.target_value)).filter(
            Threshold.data_point_id.in_(all_dp_ids)
        ).group_by(Threshold.data_point_id):
            target_by_dp[dp_id] = float(total) if total is not None else 0.0

    # Every existing Rollup row for a touched bucket, in one query, instead
    # of one existence check per bucket.
    existing = (
        db.query(Rollup)
        .filter(
            Rollup.tenant_id.in_(tenant_ids),
            Rollup.location_id.in_(location_ids),
            Rollup.category.in_(category_names),
            Rollup.period.in_(periods),
        )
        .all()
    )
    existing_by_key = {(r.tenant_id, r.location_id, r.category, r.period): r for r in existing}

    for tenant_id, location_id, category_name, period in buckets:
        bucket_dp_ids = dp_ids_by_bucket_cat.get((tenant_id, category_name), [])
        if bucket_dp_ids:
            # None (not 0) when nothing matched, same as SQL SUM() over zero
            # rows -- a bucket with no approved data yet is "no data", not zero.
            matched_values = [value_sums[(location_id, dp_id, period)] for dp_id in bucket_dp_ids if (location_id, dp_id, period) in value_sums]
            aggregated_value = sum(matched_values) if matched_values else None
            matched_targets = [target_by_dp[dp_id] for dp_id in bucket_dp_ids if dp_id in target_by_dp]
            target_value = sum(matched_targets) if matched_targets else None
        else:
            aggregated_value = None
            target_value = None

        key = (tenant_id, location_id, category_name, period)
        rollup = existing_by_key.get(key)
        if rollup is None:
            db.add(
                Rollup(
                    tenant_id=tenant_id,
                    location_id=location_id,
                    period=period,
                    category=category_name,
                    aggregated_value=aggregated_value,
                    target_value=target_value,
                )
            )
        else:
            rollup.aggregated_value = aggregated_value
            rollup.target_value = target_value


def _next_month(d: date) -> date:
    if d.month == 12:
        return d.replace(year=d.year + 1, month=1)
    return d.replace(month=d.month + 1)
