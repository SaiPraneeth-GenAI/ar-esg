"""Peer benchmarking v1 -- Amara Raja vs a single fixed comparison target
(Exide Industries, auto-provisioned per tenant so the UI never needs a
"manage peer companies" step). A year's figures come from uploading that
year's BRSR PDF: GPT-4o-mini (see app/services/peer_extraction.py) extracts
the ~16 comparable figures, the caller reviews/edits them, then saves via
the same upsert-by-period endpoint a manual entry would use. Peer figures
are keyed by the same metric keys the Chart Builder's CHARTABLE_METRICS
registry uses, so they plug directly into the comparison machinery. This is
a per-year snapshot comparison (not a trend) -- comparison periods are
always the peer's full reporting year, stored as Jan 1 of that year."""

import uuid
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.routes.charts import CHARTABLE_METRICS, get_metric_data
from app.core.auth import CurrentUser, require_roles
from app.db.models import PeerCompany, PeerData, User
from app.db.session import get_db
from app.schemas.peers import (
    PeerCompanyCreate,
    PeerCompanyOut,
    PeerCompareYearGroup,
    PeerCompareYearMetric,
    PeerCompareYearOut,
    PeerDataCreate,
    PeerDataOut,
    PeerExtractOut,
    PeerExtractRow,
)
from app.services.peer_extraction import extract_metrics_via_ai, select_relevant_pages

router = APIRouter(prefix="/peers", tags=["peers"])

CONFIDENCE_LEVELS = ("verified", "self_reported", "estimated")
DEFAULT_PEER_NAME = "Exide Industries"


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


def _self_year_value(key: str, year: int, current: CurrentUser, db: Session) -> float | None:
    """Amara Raja's own full-calendar-year figure for `key` -- the same
    computation the dashboard uses, anchored at December so the 'ytd' bucket
    covers the whole year rather than a partial one."""
    data = get_metric_data(metric=key, period=date(year, 12, 1), period_mode="ytd", months=1, location_id=None, current=current, db=db)
    return data.points[-1].value if data.points else None


@router.get("/default-company", response_model=PeerCompanyOut)
def get_default_company(
    current: CurrentUser = Depends(require_roles("Admin", "Manager", "Approver")),
    db: Session = Depends(get_db),
):
    company = db.query(PeerCompany).filter(PeerCompany.tenant_id == current.tenant_id, PeerCompany.name == DEFAULT_PEER_NAME).first()
    if company is None:
        company = PeerCompany(tenant_id=current.tenant_id, name=DEFAULT_PEER_NAME, industry="Battery manufacturing", country="India", created_by=current.id)
        db.add(company)
        db.commit()
        db.refresh(company)
    count = db.query(PeerData).filter(PeerData.tenant_id == current.tenant_id, PeerData.peer_company_id == company.id).count()
    return PeerCompanyOut(id=company.id, name=company.name, industry=company.industry, country=company.country, created_at=company.created_at, period_count=count)


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


@router.post("/{company_id}/extract", response_model=PeerExtractOut)
async def extract_peer_pdf(
    company_id: uuid.UUID,
    year: int = Form(...),
    file: UploadFile = File(...),
    current: CurrentUser = Depends(require_roles("Admin", "Manager", "Approver")),
    db: Session = Depends(get_db),
):
    """Upload one year's BRSR/annual report PDF; GPT-4o-mini extracts the
    comparable figures. Returns a review row per metric (Amara Raja's own
    value alongside the extracted peer value) -- nothing is saved yet, the
    caller confirms/edits and calls POST /{company_id}/data to save."""
    company = _get_owned_company(db, current, company_id)
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=422, detail="Upload a PDF file.")

    pdf_bytes = await file.read()
    page_images = select_relevant_pages(pdf_bytes)
    extracted = extract_metrics_via_ai(page_images)

    rows = [
        PeerExtractRow(
            key=key,
            label=spec["label"],
            unit=spec["unit"],
            group=spec["group"],
            amara_raja_value=_self_year_value(key, year, current, db),
            peer_value=extracted.get(key),
        )
        for key, spec in CHARTABLE_METRICS.items()
    ]
    return PeerExtractOut(peer_company_id=company.id, peer_company_name=company.name, year=year, source_filename=file.filename or "report.pdf", rows=rows)


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

    period = payload.period.replace(month=1, day=1)
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


@router.get("/{company_id}/compare-year", response_model=PeerCompareYearOut)
def compare_year(
    company_id: uuid.UUID,
    year: int,
    current: CurrentUser = Depends(require_roles("Admin", "Manager", "Approver")),
    db: Session = Depends(get_db),
):
    """All 16 metrics, Amara Raja vs the saved peer figures for one
    calendar year, grouped the same way the Chart Builder groups them (GHG /
    Intensity by production / Intensity by revenue / Safety) -- powers the
    grouped double-bar charts, not a trend."""
    company = _get_owned_company(db, current, company_id)
    row = (
        db.query(PeerData)
        .filter(PeerData.tenant_id == current.tenant_id, PeerData.peer_company_id == company_id, PeerData.period == date(year, 1, 1))
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail=f"No peer data saved for {year} yet.")

    groups: dict[str, list[PeerCompareYearMetric]] = {}
    for key, spec in CHARTABLE_METRICS.items():
        groups.setdefault(spec["group"], []).append(
            PeerCompareYearMetric(
                key=key,
                label=spec["label"],
                unit=spec["unit"],
                amara_raja_value=_self_year_value(key, year, current, db),
                peer_value=row.metrics.get(key),
            )
        )
    return PeerCompareYearOut(
        year=year,
        peer_company_name=company.name,
        groups=[PeerCompareYearGroup(group=g, metrics=m) for g, m in groups.items()],
    )
