import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, require_roles
from app.db.models import EmissionTarget, Location, User
from app.db.session import get_db
from app.schemas.targets import (
    BaselineMonthOut,
    BaselinePreviewRequest,
    BaselinePreviewResponse,
    TargetActivateRequest,
    TargetCreate,
    TargetMonthPerformance,
    TargetOut,
    TargetPerformanceResponse,
    TargetUpdate,
)
from app.services.carbon_calculation import compute_period_totals
from app.services.rollups import month_start
from app.services.target_calculation import (
    boundary_config_hash,
    classify_status,
    compute_baseline,
    extract_metric_value,
    get_active_production_mapping,
    months_between,
    target_value_for_month,
    validate_metric_scope,
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


def _target_out(db: Session, target: EmissionTarget) -> TargetOut:
    location = db.get(Location, target.location_id) if target.location_id else None
    owner = db.get(User, target.owner_id) if target.owner_id else None
    approver = db.get(User, target.approved_by) if target.approved_by else None

    status_label = None
    if target.status == "active":
        now = datetime.now(timezone.utc)
        period = month_start(now.date())
        totals = compute_period_totals(db, target.tenant_id, target.location_id, period)
        actual, _ = extract_metric_value(totals, target.scope, target.calculation_method, target.metric_type)
        num_months = len(months_between(target.target_period_start, target.target_period_end))
        month_target = target_value_for_month(
            target.monthly_phasing, period, float(target.target_value) if target.target_value is not None else None, num_months, target.metric_type
        )
        status_label = classify_status(actual, month_target)

    return TargetOut(
        id=target.id,
        location_id=target.location_id,
        location_name=location.name if location else None,
        scope=target.scope,
        calculation_method=target.calculation_method,
        metric_type=target.metric_type,
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


@router.post("/baseline-preview", response_model=BaselinePreviewResponse)
def baseline_preview(
    payload: BaselinePreviewRequest,
    current: CurrentUser = Depends(require_roles(*MANAGE_ROLES)),
    db: Session = Depends(get_db),
):
    """Read-only: computes what a baseline would be for a given boundary and
    period, without creating anything. Powers step 2 of the target wizard."""
    _get_tenant_location(db, current.tenant_id, payload.location_id)
    scope_error = validate_metric_scope(payload.scope, payload.metric_type)
    if scope_error:
        raise HTTPException(status_code=422, detail=scope_error)

    result = compute_baseline(
        db,
        current.tenant_id,
        payload.location_id,
        payload.scope,
        payload.calculation_method,
        payload.metric_type,
        month_start(payload.baseline_period_start),
        month_start(payload.baseline_period_end),
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
    scope_error = validate_metric_scope(payload.scope, payload.metric_type)
    if scope_error:
        raise HTTPException(status_code=422, detail=scope_error)

    phasing = [p.model_dump(mode="json") for p in payload.monthly_phasing]
    if phasing and payload.target_value is not None:
        phasing_error = validate_monthly_phasing(phasing, payload.target_value, payload.target_period_start, payload.target_period_end)
        if phasing_error:
            raise HTTPException(status_code=422, detail=phasing_error)

    target = EmissionTarget(
        tenant_id=current.tenant_id,
        location_id=payload.location_id,
        scope=payload.scope,
        calculation_method=payload.calculation_method,
        metric_type=payload.metric_type,
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
    for field, value in updates.items():
        if field in ("baseline_period_start", "baseline_period_end", "target_period_start", "target_period_end") and value is not None:
            value = month_start(value)
        setattr(target, field, value)

    if payload.monthly_phasing is not None:
        target.monthly_phasing = [p.model_dump(mode="json") for p in payload.monthly_phasing]

    scope_error = validate_metric_scope(target.scope, target.metric_type)
    if scope_error:
        raise HTTPException(status_code=422, detail=scope_error)

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
    boundary edit after this point can never silently move the target."""
    target = _get_tenant_target(db, current.tenant_id, target_id)
    if target.status != "draft":
        raise HTTPException(status_code=409, detail="Only a draft target can be activated.")
    if target.target_value is None:
        raise HTTPException(status_code=422, detail="Set a target value (directly or via a reduction percentage) before activating.")
    if not payload.rationale or not payload.rationale.strip():
        raise HTTPException(status_code=422, detail="A rationale is required to activate a target.")

    if target.monthly_phasing:
        phasing_error = validate_monthly_phasing(
            target.monthly_phasing, float(target.target_value), target.target_period_start, target.target_period_end
        )
        if phasing_error:
            raise HTTPException(status_code=422, detail=phasing_error)

    baseline = compute_baseline(
        db,
        current.tenant_id,
        target.location_id,
        target.scope,
        target.calculation_method,
        target.metric_type,
        target.baseline_period_start,
        target.baseline_period_end,
    )
    if not baseline.ready:
        raise HTTPException(status_code=422, detail=baseline.message)

    existing_active = (
        db.query(EmissionTarget)
        .filter(
            EmissionTarget.tenant_id == current.tenant_id,
            EmissionTarget.location_id == target.location_id,
            EmissionTarget.scope == target.scope,
            EmissionTarget.metric_type == target.metric_type,
            EmissionTarget.status == "active",
        )
        .first()
    )
    if existing_active is not None:
        raise HTTPException(
            status_code=409,
            detail="An active target already exists for this boundary and metric. Archive it before activating a new one.",
        )

    prod_mapping = get_active_production_mapping(db, current.tenant_id, target.location_id)
    all_calc_ids = [str(cid) for m in baseline.months for cid in m.calculation_ids]

    target.baseline_value = baseline.baseline_value
    target.baseline_completeness_pct = baseline.completeness_pct
    target.baseline_calculation_ids = all_calc_ids
    target.baseline_locked_at = datetime.now(timezone.utc)
    target.boundary_config_hash = boundary_config_hash(
        current.tenant_id, target.location_id, target.scope, target.calculation_method, target.metric_type,
        prod_mapping.id if prod_mapping else None,
    )
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

    out_months: list[TargetMonthPerformance] = []
    for period in months:
        totals = compute_period_totals(db, current.tenant_id, target.location_id, period)
        actual, _ = extract_metric_value(totals, target.scope, target.calculation_method, target.metric_type)
        month_target = target_value_for_month(target.monthly_phasing, period, target_value, num_months, target.metric_type)
        variance_pct = None
        if actual is not None and month_target is not None and month_target != 0:
            variance_pct = (actual - month_target) / month_target * 100
        out_months.append(
            TargetMonthPerformance(
                period=period,
                actual=actual,
                target=month_target,
                variance_pct=variance_pct,
                status=classify_status(actual, month_target),
                completeness_pct=totals["completeness_pct"],
            )
        )

    return TargetPerformanceResponse(target_id=target.id, metric_type=target.metric_type, months=out_months)
