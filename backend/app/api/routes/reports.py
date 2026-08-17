import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, require_roles
from app.db.session import get_db
from app.services.dashboard_report import build_report_sections
from app.services.report_pdf import build_pdf
from app.services.report_pptx import build_pptx

router = APIRouter(prefix="/reports", tags=["reports"])

_MEDIA_TYPES = {
    "pdf": "application/pdf",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}


@router.get("/dashboard-export")
def dashboard_export(
    period: date,
    format: str = "pdf",
    location_id: uuid.UUID | None = None,
    period_mode: str = "month",
    current: CurrentUser = Depends(require_roles("Admin", "Manager", "Approver")),
    db: Session = Depends(get_db),
):
    """One-click export of all four dashboard tabs -- deterministic charts
    and figures (the same overview/trend functions the dashboard itself
    calls), with one AI-generated narrative paragraph per section (see
    services/dashboard_insight.py's guardrails: numbers-only input, no
    fabrication, deterministic fallback on any failure)."""
    if format not in _MEDIA_TYPES:
        raise HTTPException(status_code=422, detail="format must be 'pdf' or 'pptx'")

    sections, meta = build_report_sections(db, current, period, period_mode, location_id)
    content = build_pdf(sections, meta) if format == "pdf" else build_pptx(sections, meta)
    filename = f"amara_raja_esg_dashboard_{meta.period_slug}.{format}"

    return Response(
        content=content,
        media_type=_MEDIA_TYPES[format],
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
