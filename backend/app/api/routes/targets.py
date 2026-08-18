import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, require_roles
from app.core.metrics_registry import CHARTABLE_METRICS
from app.db.models import EmissionTarget, Location, User
from app.db.session import get_db
from app.schemas.targets import (
    BaselineMonthOut,
    BaselinePreviewRequest,
    BaselinePreviewResponse,
    TargetActivateRequest,
    TargetableMetricOut,
    TargetBulkImportRequest,
    TargetBulkImportResponse,
    TargetBulkRowResult,
    TargetCreate,
    TargetMonthPerformance,
    TargetOut,
    TargetPerformanceResponse,
    TargetUpdate,
)
from app.services.rollups import month_start
from app.services.target_calculation import (
    TARGETABLE_METRIC_KEYS,
    boundary_config_hash,
    denominator_mapping_id,
    classify_status,
    compute_baseline,
    extract_metric_value,
    extract_metric_value_batch,
    metric_label,
    metric_unit,
    months_between,
    target_value_for_month,
    validate_monthly_phasing,
)

router = APIRouter(prefix="/targets", tags=["targets"])

VIEW_ROLES = ("Admin", "Manager", "Approver")
MANAGE_ROLES = ("Admin", "Approver")


def _get_tenant_location(db: Session, tenant_id: uuid.UUID, location_id: uuid.UUID | None) -> Location | None:
    if location_id is None:
        return None
    loc = db.query(Location).filter(Location.id == location_id, Location.tenant_id == tenant_id).first()
    if loc is None:
        raise HTTPException(status_code=404, detail="Location not found")
    return loc


def _get_tenant_target(db: Session, tenant_id: uuid.UUID, target_id: uuid.UUID) -> EmissionTarget:
    target = db.get(EmissionTarget, target_id)
    if target is None or target.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Target not found")
    return target


def _validate_metric_key(metric_key: str) -> None:
    if metric_key not in TARGETABLE_METRIC_KEYS:
        raise HTTPException(status_code=422, detail="Unknown or unsupported target metric.")


def _target_out(db: Session, target: EmissionTarget) -> TargetOut:
    location = db.get(Location, target.location_id) if target.location_id else None
    owner = db.get(User, target.owner_id) if target.owner_id else None
    approver = db.get(User, target.approved_by) if target.approved_by else None

    status_label = None
    if target.status == "active":
        now = datetime.now(timezone.utc)
        period = month_start(now.date())
        if period < target.target_period_start:
            # Comparing this month's actual against a target period that
            # hasn't started yet (e.g. a target set now for a future year)
            # isn't a real comparison -- the target commits to an outcome
            # BY that period, not one owed starting today.
            status_label = "Not started yet"
        elif period > target.target_period_end:
            status_label = "Target period ended"
        else:
            value, _ = extract_metric_value(db, target.tenant_id, target.location_id, target.metric_key, [period])
            num_months = len(months_between(target.target_period_start, target.target_period_end))
            month_target = target_value_for_month(
                target.monthly_phasing, period, float(target.target_value) if target.target_value is not None else None, num_months, target.metric_key
            )
            status_label = classify_status(value, month_target)

    return TargetOut(
        id=target.id,
        location_id=target.location_id,
        location_name=location.name if location else None,
        metric_key=target.metric_key,
        metric_label=metric_label(target.metric_key),
        metric_unit=metric_unit(target.metric_key),
        baseline_period_start=target.baseline_period_start,
        baseline_period_end=target.baseline_period_end,
        baseline_value=float(target.baseline_value) if target.baseline_value is not None else None,
        baseline_completeness_pct=float(target.baseline_completeness_pct) if target.baseline_completeness_pct is not None else None,
        baseline_locked_at=target.baseline_locked_at,
        reduction_percentage=float(target.reduction_percentage) if target.reduction_percentage is not None else None,
        target_period_start=target.target_period_start,
        target_period_end=target.target_period_end,
        target_value=float(target.target_value) if target.target_value is not None else None,
        monthly_phasing=target.monthly_phasing or [],
        status=target.status,
        owner_id=target.owner_id,
        owner_email=owner.email if owner else None,
        rationale=target.rationale,
        approved_by=target.approved_by,
        approved_by_email=approver.email if approver else None,
        approved_at=target.approved_at,
        boundary_config_hash=target.boundary_config_hash,
        created_at=target.created_at,
        updated_at=target.updated_at,
        current_status_label=status_label,
    )


@router.get("/metrics", response_model=list[TargetableMetricOut])
def list_targetable_metrics(current: CurrentUser = Depends(require_roles(*VIEW_ROLES))):
    """The exact same metrics the dashboards show -- picking a target is
    picking one of these, nothing else to configure."""
    return [
        TargetableMetricOut(key=k, label=CHARTABLE_METRICS[k]["label"], unit=CHARTABLE_METRICS[k]["unit"], group=CHARTABLE_METRICS[k]["group"])
        for k in TARGETABLE_METRIC_KEYS
    ]


@router.post("/baseline-preview", response_model=BaselinePreviewResponse)
def baseline_preview(
    payload: BaselinePreviewRequest,
    current: CurrentUser = Depends(require_roles(*MANAGE_ROLES)),
    db: Session = Depends(get_db),
):
    """Read-only: computes what a baseline would be for a given metric and
    period, without creating anything. Powers step 2 of the target wizard."""
    _get_tenant_location(db, current.tenant_id, payload.location_id)
    _validate_metric_key(payload.metric_key)

    result = compute_baseline(
        db, current.tenant_id, payload.location_id, payload.metric_key,
        month_start(payload.baseline_period_start), month_start(payload.baseline_period_end),
    )
    return BaselinePreviewResponse(
        ready=result.ready,
        provisional=result.provisional,
        baseline_value=result.baseline_value,
        completeness_pct=result.completeness_pct,
        message=result.message,
        months=[BaselineMonthOut(period=m.period, value=m.value, completeness_pct=m.completeness_pct) for m in result.months],
    )


@router.post("", response_model=TargetOut)
def create_target(
    payload: TargetCreate,
    current: CurrentUser = Depends(require_roles(*MANAGE_ROLES)),
    db: Session = Depends(get_db),
):
    _get_tenant_location(db, current.tenant_id, payload.location_id)
    _validate_metric_key(payload.metric_key)

    phasing = [p.model_dump(mode="json") for p in payload.monthly_phasing]
    if phasing and payload.target_value is not None:
        phasing_error = validate_monthly_phasing(phasing, payload.target_value, payload.target_period_start, payload.target_period_end)
        if phasing_error:
            raise HTTPException(status_code=422, detail=phasing_error)

    target = EmissionTarget(
        tenant_id=current.tenant_id,
        location_id=payload.location_id,
        metric_key=payload.metric_key,
        baseline_period_start=month_start(payload.baseline_period_start),
        baseline_period_end=month_start(payload.baseline_period_end),
        reduction_percentage=payload.reduction_percentage,
        target_period_start=month_start(payload.target_period_start),
        target_period_end=month_start(payload.target_period_end),
        target_value=payload.target_value,
        monthly_phasing=phasing,
        status="draft",
        owner_id=payload.owner_id,
        rationale=payload.rationale,
        created_by=current.id,
    )
    db.add(target)
    db.commit()
    db.refresh(target)
    return _target_out(db, target)


@router.post("/bulk-import", response_model=TargetBulkImportResponse)
def bulk_import_targets(
    payload: TargetBulkImportRequest,
    current: CurrentUser = Depends(require_roles(*MANAGE_ROLES)),
    db: Session = Depends(get_db),
):
    """One row per target: creates it, computes its baseline, and activates
    immediately if the baseline is ready -- mirrors what the wizard does in
    three clicks, for a whole sheet at once. Meant for demo/bulk seeding
    (see services/demo_data.py's sample workbook), not a replacement for
    the wizard's baseline preview/monthly-phasing UI, so every target
    created this way gets an even monthly spread, no custom phasing."""
    results: list[TargetBulkRowResult] = []
    activated_count = 0
    error_count = 0
    location_cache: dict[str, uuid.UUID | None] = {}

    for row in payload.rows:
        if row.metric_key not in TARGETABLE_METRIC_KEYS:
            results.append(TargetBulkRowResult(row_index=row.row_index, status="error", metric_key=row.metric_key, message="Unknown or unsupported target metric."))
            error_count += 1
            continue

        location_id: uuid.UUID | None = None
        if row.location_name and row.location_name.strip():
            key = row.location_name.strip().lower()
            if key not in location_cache:
                loc = (
                    db.query(Location)
                    .filter(Location.tenant_id == current.tenant_id, Location.name.ilike(row.location_name.strip()))
                    .first()
                )
                location_cache[key] = loc.id if loc else None
            location_id = location_cache[key]
            if location_id is None:
                results.append(TargetBulkRowResult(row_index=row.row_index, status="error", metric_key=row.metric_key, message=f"Site '{row.location_name}' not found."))
                error_count += 1
                continue

        baseline_start = month_start(row.baseline_period_start)
        baseline_end = month_start(row.baseline_period_end)
        target_start = month_start(row.target_period_start)
        target_end = month_start(row.target_period_end)

        if not payload.commit:
            results.append(TargetBulkRowResult(row_index=row.row_index, status="valid", metric_key=row.metric_key))
            continue

        baseline = compute_baseline(db, current.tenant_id, location_id, row.metric_key, baseline_start, baseline_end)
        if not baseline.ready:
            results.append(TargetBulkRowResult(row_index=row.row_index, status="error", metric_key=row.metric_key, message=baseline.message))
            error_count += 1
            continue

        target_value = row.target_value
        if target_value is None and row.reduction_percentage is not None and baseline.baseline_value is not None:
            target_value = baseline.baseline_value * (1 - row.reduction_percentage / 100)
        if target_value is None:
            results.append(
                TargetBulkRowResult(row_index=row.row_index, status="error", metric_key=row.metric_key, message="Provide a target value or a reduction percentage.")
            )
            error_count += 1
            continue

        existing_active = (
            db.query(EmissionTarget)
            .filter(
                EmissionTarget.tenant_id == current.tenant_id,
                EmissionTarget.location_id == location_id,
                EmissionTarget.metric_key == row.metric_key,
                EmissionTarget.status == "active",
            )
            .first()
        )
        if existing_active is not None:
            results.append(
                TargetBulkRowResult(
                    row_index=row.row_index, status="error", metric_key=row.metric_key,
                    message="An active target already exists for this metric/site -- archive it first.",
                )
            )
            error_count += 1
            continue

        denominator_id = denominator_mapping_id(db, current.tenant_id, location_id, row.metric_key)
        all_calc_ids = [str(cid) for m in baseline.months for cid in m.calculation_ids]

        target = EmissionTarget(
            tenant_id=current.tenant_id,
            location_id=location_id,
            metric_key=row.metric_key,
            baseline_period_start=baseline_start,
            baseline_period_end=baseline_end,
            baseline_value=baseline.baseline_value,
            baseline_completeness_pct=baseline.completeness_pct,
            baseline_calculation_ids=all_calc_ids,
            baseline_locked_at=datetime.now(timezone.utc),
            reduction_percentage=row.reduction_percentage,
            target_period_start=target_start,
            target_period_end=target_end,
            target_value=target_value,
            monthly_phasing=[],
            status="active",
            rationale=row.rationale,
            boundary_config_hash=boundary_config_hash(current.tenant_id, location_id, row.metric_key, denominator_id),
            approved_by=current.id,
            approved_at=datetime.now(timezone.utc),
            created_by=current.id,
        )
        db.add(target)
        db.flush()
        results.append(TargetBulkRowResult(row_index=row.row_index, status="activated", metric_key=row.metric_key, target_id=target.id))
        activated_count += 1

    if payload.commit:
        db.commit()

    return TargetBulkImportResponse(rows=results, activated_count=activated_count, error_count=error_count)


@router.get("", response_model=list[TargetOut])
def list_targets(
    status: str | None = None,
    current: CurrentUser = Depends(require_roles(*VIEW_ROLES)),
    db: Session = Depends(get_db),
):
    q = db.query(EmissionTarget).filter(EmissionTarget.tenant_id == current.tenant_id)
    if status is not None:
        q = q.filter(EmissionTarget.status == status)
    targets = q.order_by(EmissionTarget.created_at.desc()).all()
    return [_target_out(db, t) for t in targets]


@router.get("/{target_id}", response_model=TargetOut)
def get_target(
    target_id: uuid.UUID,
    current: CurrentUser = Depends(require_roles(*VIEW_ROLES)),
    db: Session = Depends(get_db),
):
    target = _get_tenant_target(db, current.tenant_id, target_id)
    return _target_out(db, target)


@router.patch("/{target_id}", response_model=TargetOut)
def update_target(
    target_id: uuid.UUID,
    payload: TargetUpdate,
    current: CurrentUser = Depends(require_roles(*MANAGE_ROLES)),
    db: Session = Depends(get_db),
):
    target = _get_tenant_target(db, current.tenant_id, target_id)
    if target.status != "draft":
        raise HTTPException(status_code=409, detail="Only draft targets can be edited -- archive and recreate an active target instead.")

    updates = payload.model_dump(exclude_unset=True, exclude={"monthly_phasing"})
    if "location_id" in updates:
        _get_tenant_location(db, current.tenant_id, updates["location_id"])
    if "metric_key" in updates and updates["metric_key"] is not None:
        _validate_metric_key(updates["metric_key"])
    for field, value in updates.items():
        if field in ("baseline_period_start", "baseline_period_end", "target_period_start", "target_period_end") and value is not None:
            value = month_start(value)
        setattr(target, field, value)

    if payload.monthly_phasing is not None:
        target.monthly_phasing = [p.model_dump(mode="json") for p in payload.monthly_phasing]

    target.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(target)
    return _target_out(db, target)


@router.delete("/{target_id}", status_code=204)
def delete_target(
    target_id: uuid.UUID,
    current: CurrentUser = Depends(require_roles(*MANAGE_ROLES)),
    db: Session = Depends(get_db),
):
    target = _get_tenant_target(db, current.tenant_id, target_id)
    if target.status != "draft":
        raise HTTPException(status_code=409, detail="Only draft targets can be deleted -- archive an active target instead.")
    db.delete(target)
    db.commit()


@router.post("/{target_id}/activate", response_model=TargetOut)
def activate_target(
    target_id: uuid.UUID,
    payload: TargetActivateRequest,
    current: CurrentUser = Depends(require_roles(*MANAGE_ROLES)),
    db: Session = Depends(get_db),
):
    """Locks the baseline to the exact calculation snapshots behind it and
    the boundary this target was defined against. A recalculation or a
    denominator-mapping edit after this point can never silently move the
    target."""
    target = _get_tenant_target(db, current.tenant_id, target_id)
    if target.status != "draft":
        raise HTTPException(status_code=409, detail="Only a draft target can be activated.")
    if target.target_value is None:
        raise HTTPException(status_code=422, detail="Set a target value (directly or via a reduction percentage) before activating.")

    if target.monthly_phasing:
        phasing_error = validate_monthly_phasing(
            target.monthly_phasing, float(target.target_value), target.target_period_start, target.target_period_end
        )
        if phasing_error:
            raise HTTPException(status_code=422, detail=phasing_error)

    baseline = compute_baseline(db, current.tenant_id, target.location_id, target.metric_key, target.baseline_period_start, target.baseline_period_end)
    if not baseline.ready:
        raise HTTPException(status_code=422, detail=baseline.message)

    existing_active = (
        db.query(EmissionTarget)
        .filter(
            EmissionTarget.tenant_id == current.tenant_id,
            EmissionTarget.location_id == target.location_id,
            EmissionTarget.metric_key == target.metric_key,
            EmissionTarget.status == "active",
        )
        .first()
    )
    if existing_active is not None:
        raise HTTPException(
            status_code=409,
            detail="An active target already exists for this metric. Archive it before activating a new one.",
        )

    denominator_id = denominator_mapping_id(db, current.tenant_id, target.location_id, target.metric_key)
    all_calc_ids = [str(cid) for m in baseline.months for cid in m.calculation_ids]

    target.baseline_value = baseline.baseline_value
    target.baseline_completeness_pct = baseline.completeness_pct
    target.baseline_calculation_ids = all_calc_ids
    target.baseline_locked_at = datetime.now(timezone.utc)
    target.boundary_config_hash = boundary_config_hash(current.tenant_id, target.location_id, target.metric_key, denominator_id)
    target.rationale = payload.rationale
    target.approved_by = current.id
    target.approved_at = datetime.now(timezone.utc)
    target.status = "active"
    target.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(target)
    return _target_out(db, target)


@router.post("/{target_id}/archive", response_model=TargetOut)
def archive_target(
    target_id: uuid.UUID,
    current: CurrentUser = Depends(require_roles(*MANAGE_ROLES)),
    db: Session = Depends(get_db),
):
    target = _get_tenant_target(db, current.tenant_id, target_id)
    if target.status == "archived":
        raise HTTPException(status_code=409, detail="Target is already archived.")
    target.status = "archived"
    target.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(target)
    return _target_out(db, target)


@router.post("/{target_id}/restore", response_model=TargetOut)
def restore_target(
    target_id: uuid.UUID,
    current: CurrentUser = Depends(require_roles(*MANAGE_ROLES)),
    db: Session = Depends(get_db),
):
    """Brings an archived target back as a draft -- not directly back to
    active, since real time has passed since it was archived and its old
    baseline lock may no longer reflect the tenant's current data. The
    user reviews it and re-activates through the normal flow, the same
    way any other draft does."""
    target = _get_tenant_target(db, current.tenant_id, target_id)
    if target.status != "archived":
        raise HTTPException(status_code=409, detail="Only an archived target can be restored.")
    target.status = "draft"
    target.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(target)
    return _target_out(db, target)


@router.get("/{target_id}/performance", response_model=TargetPerformanceResponse)
def target_performance(
    target_id: uuid.UUID,
    current: CurrentUser = Depends(require_roles(*VIEW_ROLES)),
    db: Session = Depends(get_db),
):
    target = _get_tenant_target(db, current.tenant_id, target_id)
    months = months_between(target.target_period_start, target.target_period_end)
    num_months = len(months)
    target_value = float(target.target_value) if target.target_value is not None else None

    values_by_month = extract_metric_value_batch(db, current.tenant_id, target.location_id, target.metric_key, months)

    out_months: list[TargetMonthPerformance] = []
    for period in months:
        actual, completeness = values_by_month[period]
        month_target = target_value_for_month(target.monthly_phasing, period, target_value, num_months, target.metric_key)
        variance_pct = None
        if actual is not None and month_target is not None and month_target != 0:
            variance_pct = (actual - month_target) / month_target * 100
        out_months.append(
            TargetMonthPerformance(
                period=period, actual=actual, target=month_target, variance_pct=variance_pct,
                status=classify_status(actual, month_target), completeness_pct=completeness,
            )
        )

    return TargetPerformanceResponse(target_id=target.id, metric_key=target.metric_key, months=out_months)
