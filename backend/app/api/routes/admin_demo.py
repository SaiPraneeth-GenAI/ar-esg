"""Settings -> Approval Settings -> Simulate Sample: an Admin-only, tenant-
scoped destructive reset plus three downloadable sample workbooks, so a
demo can start from a clean slate and repopulate itself end-to-end through
the app's own Bulk Upload flows -- nothing here writes an entry, factor,
or target directly."""

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, require_roles
from app.db.models import Entry, EmissionTarget, Location, PeerData
from app.db.session import get_db
from app.services.demo_data import build_emission_factors_workbook, build_entries_workbook, build_targets_workbook

router = APIRouter(prefix="/admin/demo", tags=["admin"])

_XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class ClearDemoDataResponse(BaseModel):
    entries_deleted: int
    targets_deleted: int
    peer_data_deleted: int


@router.post("/clear", response_model=ClearDemoDataResponse)
def clear_demo_data(
    current: CurrentUser = Depends(require_roles("Admin")),
    db: Session = Depends(get_db),
):
    """Deletes every Entry (cascading to Approval/AuditLog/Attachment/
    EmissionCalculation via FK ondelete=CASCADE), every EmissionTarget, and
    every PeerData row for this tenant. Deliberately leaves Users, Roles,
    Locations, Categories/DataPoints, Emission Factors, and Peer Company
    names untouched -- those are tenant setup, not demo data, and clearing
    them would mean redoing setup before every demo instead of just
    repopulating the numbers."""
    location_ids = [loc.id for loc in db.query(Location).filter(Location.tenant_id == current.tenant_id).all()]

    entries_deleted = db.query(Entry).filter(Entry.location_id.in_(location_ids)).delete(synchronize_session=False)
    targets_deleted = db.query(EmissionTarget).filter(EmissionTarget.tenant_id == current.tenant_id).delete(synchronize_session=False)
    peer_data_deleted = db.query(PeerData).filter(PeerData.tenant_id == current.tenant_id).delete(synchronize_session=False)
    db.commit()

    return ClearDemoDataResponse(
        entries_deleted=entries_deleted, targets_deleted=targets_deleted, peer_data_deleted=peer_data_deleted
    )


@router.get("/entries-workbook")
def download_entries_workbook(
    current: CurrentUser = Depends(require_roles("Admin")),
    db: Session = Depends(get_db),
):
    content = build_entries_workbook(db, current.tenant_id)
    return Response(
        content=content,
        media_type=_XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": 'attachment; filename="demo_entries_aug2024_aug2026.xlsx"'},
    )


@router.get("/emission-factors-workbook")
def download_emission_factors_workbook(
    current: CurrentUser = Depends(require_roles("Admin")),
):
    content = build_emission_factors_workbook()
    return Response(
        content=content,
        media_type=_XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": 'attachment; filename="demo_emission_factors.xlsx"'},
    )


@router.get("/targets-workbook")
def download_targets_workbook(
    current: CurrentUser = Depends(require_roles("Admin")),
):
    content = build_targets_workbook()
    return Response(
        content=content,
        media_type=_XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": 'attachment; filename="demo_targets.xlsx"'},
    )
