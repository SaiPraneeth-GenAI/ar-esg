"""Peer benchmarking v1 -- see docs/CHART_SIMPLIFICATION_AND_PEER_ANALYSIS.md
Part 2. Entry is manual (a form) or via a downloadable CSV template with
Amara Raja's own values pre-filled and the peer's columns left blank to
fill in and re-upload -- parsed client-side (matching how /entries' own
bulk-upload wizard already parses CSV/Excel in the browser and posts
structured JSON, rather than a server-side file-upload endpoint). Peer
figures are keyed by the same metric keys the Chart Builder's
CHARTABLE_METRICS registry uses, so they plug directly into the
comparison-chart machinery."""

import csv
import io
import uuid
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.routes.charts import CHARTABLE_METRICS, get_metric_data
from app.core.auth import CurrentUser, require_roles
from app.db.models import PeerCompany, PeerData, User
from app.db.session import get_db
from app.schemas.peers import (
    PeerCompanyCreate,
    PeerCompanyOut,
    PeerCompareEntry,
    PeerCompareOut,
    PeerDataCreate,
    PeerDataOut,
)

router = APIRouter(prefix="/peers", tags=["peers"])

CONFIDENCE_LEVELS = ("verified", "self_reported", "estimated")


def _get_owned_company(db: Session, current: CurrentUser, company_id: uuid.UUID) -> PeerCompany:
    company = db.query(PeerCompany).filter(PeerCompany.id == company_id, PeerCompany.tenant_id == current.tenant_id).first()
    if company is None:
        raise HTTPException(status_code=404, detail="Peer company not found.")
    return company


def _validate_metrics(metrics: dict[str, float]) -> None:
    if not metrics:
        raise HTTPException(status_code=422, detail="Enter at least one metric value.")
    unknown = [k for k in metrics if k not in CHARTABLE_METRICS]
    if unknown:
        raise HTTPException(status_code=422, detail=f"Unknown metric(s): {', '.join(unknown)}")


@router.get("/{company_id}/template")
def download_template(
    company_id: uuid.UUID,
    period: date,
    metrics: str,
    location_id: uuid.UUID | None = None,
    current: CurrentUser = Depends(require_roles("Admin", "Manager", "Approver")),
    db: Session = Depends(get_db),
):
    """One row per requested metric, Amara Raja's own value pre-filled
    (the same computation the dashboard uses) and the peer's column left
    blank -- fill it in and re-upload via the same form the manual-entry
    path uses (parsed in the browser, not a server-side file endpoint)."""
    company = _get_owned_company(db, current, company_id)
    keys = [k for k in metrics.split(",") if k.strip()]
    unknown = [k for k in keys if k not in CHARTABLE_METRICS]
    if unknown:
        raise HTTPException(status_code=422, detail=f"Unknown metric(s): {', '.join(unknown)}")

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["metric_key", "metric_label", "unit", "amara_raja_value", f"{company.name}_value"])
    for key in keys:
        spec = CHARTABLE_METRICS[key]
        data = get_metric_data(metric=key, period=period, period_mode="month", months=1, location_id=location_id, current=current, db=db)
        self_value = data.points[-1].value if data.points else None
        writer.writerow([key, spec["label"], spec["unit"], self_value if self_value is not None else "", ""])

    filename = f"{company.name.replace(' ', '_')}_{period.isoformat()[:7]}_template.csv"
    return Response(content=buffer.getvalue(), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.post("", response_model=PeerCompanyOut)
def create_peer_company(
    payload: PeerCompanyCreate,
    current: CurrentUser = Depends(require_roles("Admin", "Manager", "Approver")),
    db: Session = Depends(get_db),
):
    company = PeerCompany(tenant_id=current.tenant_id, name=payload.name, industry=payload.industry, country=payload.country, created_by=current.id)
    db.add(company)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="A peer company with this name already exists.")
    db.refresh(company)
    return PeerCompanyOut(id=company.id, name=company.name, industry=company.industry, country=company.country, created_at=company.created_at, period_count=0)


@router.get("", response_model=list[PeerCompanyOut])
def list_peer_companies(
    current: CurrentUser = Depends(require_roles("Admin", "Manager", "Approver")),
    db: Session = Depends(get_db),
):
    companies = db.query(PeerCompany).filter(PeerCompany.tenant_id == current.tenant_id).order_by(PeerCompany.name).all()
    counts = dict(
        db.query(PeerData.peer_company_id, func.count(PeerData.id))
        .filter(PeerData.tenant_id == current.tenant_id)
        .group_by(PeerData.peer_company_id)
        .all()
    )
    return [
        PeerCompanyOut(id=c.id, name=c.name, industry=c.industry, country=c.country, created_at=c.created_at, period_count=counts.get(c.id, 0))
        for c in companies
    ]


@router.delete("/{company_id}", status_code=204)
def delete_peer_company(
    company_id: uuid.UUID,
    current: CurrentUser = Depends(require_roles("Admin", "Manager", "Approver")),
    db: Session = Depends(get_db),
):
    company = _get_owned_company(db, current, company_id)
    db.delete(company)
    db.commit()


def _data_out(db: Session, row: PeerData) -> PeerDataOut:
    user = db.get(User, row.uploaded_by) if row.uploaded_by else None
    return PeerDataOut(
        id=row.id,
        peer_company_id=row.peer_company_id,
        period=row.period,
        metrics=row.metrics,
        data_source=row.data_source,
        source_link=row.source_link,
        data_confidence=row.data_confidence,
        notes=row.notes,
        uploaded_by_email=user.email if user else None,
        uploaded_at=row.uploaded_at,
        updated_at=row.updated_at,
    )


@router.post("/{company_id}/data", response_model=PeerDataOut)
def upsert_peer_data(
    company_id: uuid.UUID,
    payload: PeerDataCreate,
    current: CurrentUser = Depends(require_roles("Admin", "Manager", "Approver")),
    db: Session = Depends(get_db),
):
    _get_owned_company(db, current, company_id)
    _validate_metrics(payload.metrics)
    if payload.data_confidence is not None and payload.data_confidence not in CONFIDENCE_LEVELS:
        raise HTTPException(status_code=422, detail=f"data_confidence must be one of {CONFIDENCE_LEVELS}")

    period = payload.period.replace(day=1)
    row = (
        db.query(PeerData)
        .filter(PeerData.tenant_id == current.tenant_id, PeerData.peer_company_id == company_id, PeerData.period == period)
        .first()
    )
    if row is None:
        row = PeerData(tenant_id=current.tenant_id, peer_company_id=company_id, period=period, uploaded_by=current.id)
        db.add(row)
    row.metrics = payload.metrics
    row.data_source = payload.data_source
    row.source_link = payload.source_link
    row.data_confidence = payload.data_confidence
    row.notes = payload.notes
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return _data_out(db, row)


@router.get("/{company_id}/data", response_model=list[PeerDataOut])
def list_peer_data(
    company_id: uuid.UUID,
    current: CurrentUser = Depends(require_roles("Admin", "Manager", "Approver")),
    db: Session = Depends(get_db),
):
    _get_owned_company(db, current, company_id)
    rows = (
        db.query(PeerData)
        .filter(PeerData.tenant_id == current.tenant_id, PeerData.peer_company_id == company_id)
        .order_by(PeerData.period.desc())
        .all()
    )
    return [_data_out(db, r) for r in rows]


@router.delete("/{company_id}/data/{data_id}", status_code=204)
def delete_peer_data(
    company_id: uuid.UUID,
    data_id: uuid.UUID,
    current: CurrentUser = Depends(require_roles("Admin", "Manager", "Approver")),
    db: Session = Depends(get_db),
):
    _get_owned_company(db, current, company_id)
    row = (
        db.query(PeerData)
        .filter(PeerData.id == data_id, PeerData.tenant_id == current.tenant_id, PeerData.peer_company_id == company_id)
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Peer data not found.")
    db.delete(row)
    db.commit()


@router.get("/compare", response_model=PeerCompareOut)
def compare_peers(
    metric: str,
    period: date,
    period_mode: str = "month",
    location_id: uuid.UUID | None = None,
    peer_ids: str = "",
    current: CurrentUser = Depends(require_roles("Admin", "Manager", "Approver")),
    db: Session = Depends(get_db),
):
    """Amara Raja's own value for `metric` (the exact same computation the
    dashboard and trend charts use) alongside each selected peer's most
    recent value at or before `period` -- peer data is entered
    periodically, not necessarily for the exact same month, so an
    approximate-but-labeled match beats silently showing nothing."""
    spec = CHARTABLE_METRICS.get(metric)
    if spec is None:
        raise HTTPException(status_code=404, detail="Unknown metric.")

    self_data = get_metric_data(metric=metric, period=period, period_mode=period_mode, months=1, location_id=location_id, current=current, db=db)
    self_value = self_data.points[-1].value if self_data.points else None

    entries = [PeerCompareEntry(name="Amara Raja", is_self=True, value=self_value, period=period.replace(day=1))]

    ids = [uuid.UUID(pid) for pid in peer_ids.split(",") if pid.strip()]
    for peer_id in ids:
        company = db.query(PeerCompany).filter(PeerCompany.id == peer_id, PeerCompany.tenant_id == current.tenant_id).first()
        if company is None:
            continue
        row = (
            db.query(PeerData)
            .filter(PeerData.tenant_id == current.tenant_id, PeerData.peer_company_id == peer_id, PeerData.period <= period)
            .order_by(PeerData.period.desc())
            .first()
        )
        value = row.metrics.get(metric) if row else None
        entries.append(PeerCompareEntry(name=company.name, is_self=False, value=value, period=row.period if row else None))

    return PeerCompareOut(metric=metric, label=spec["label"], unit=spec["unit"], period=period.replace(day=1), entries=entries)
