"""Settings -> Approval Settings -> Simulate Sample: an Admin-only, tenant-
scoped destructive reset plus three downloadable sample workbooks, so a
demo can start from a clean slate and repopulate itself end-to-end through
the app's own Bulk Upload flows -- nothing here writes an entry, factor,
or target directly, with one exception (populate_all_demo_data, see there)."""

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.routes.entries import bulk_import
from app.api.routes.targets import bulk_import_targets
from app.core.auth import CurrentUser, require_roles
from app.db.models import Entry, EmissionTarget, Location, PeerData
from app.db.session import get_db
from app.schemas.entries import BulkImportRequest, BulkImportRowIn
from app.schemas.targets import TargetBulkImportRequest, TargetBulkRowIn
from app.services.demo_data import (
    build_emission_factors_workbook,
    build_entries_workbook,
    build_targets_workbook,
    demo_entry_rows,
    demo_target_rows,
    ensure_demo_emission_factors,
)

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
    Locations, Categories/DataPoints, and Peer Company names untouched --
    those are tenant setup, not demo data, and clearing them would mean
    redoing setup before every demo instead of just repopulating the
    numbers. Emission factors are the one exception: ensure_demo_emission_factors()
    idempotently backfills the Scope 1/2 factors the demo entries need
    (never removes or overwrites a tenant's own), so a demo entries upload
    can never land ahead of the factors it needs to calculate against."""
    location_ids = [loc.id for loc in db.query(Location).filter(Location.tenant_id == current.tenant_id).all()]

    entries_deleted = db.query(Entry).filter(Entry.location_id.in_(location_ids)).delete(synchronize_session=False)
    targets_deleted = db.query(EmissionTarget).filter(EmissionTarget.tenant_id == current.tenant_id).delete(synchronize_session=False)
    peer_data_deleted = db.query(PeerData).filter(PeerData.tenant_id == current.tenant_id).delete(synchronize_session=False)
    ensure_demo_emission_factors(db, current.tenant_id, current.id)
    db.commit()

    return ClearDemoDataResponse(
        entries_deleted=entries_deleted, targets_deleted=targets_deleted, peer_data_deleted=peer_data_deleted
    )


class PopulateAllResponse(BaseModel):
    entries_deleted: int
    targets_deleted: int
    entries_created: int
    entries_errors: int
    targets_activated: int
    targets_errors: int


@router.post("/populate-all", response_model=PopulateAllResponse)
async def populate_all_demo_data(
    current: CurrentUser = Depends(require_roles("Admin")),
    db: Session = Depends(get_db),
):
    """One click: clears this tenant's existing entries/targets, then
    creates the full demo dataset -- factors, all entries (auto-approved,
    since it's run by an Admin), and all targets, activated -- so a demo
    never lands mid-way through Draft/Submitted rows waiting on a separate
    approval step. Runs the same clear + bulk-import + bulk-import-targets
    logic the manual three-step flow already uses, directly instead of a
    download-then-reupload round trip through xlsx, but is otherwise the
    same operation -- just password-gated on the frontend (see
    ApprovalSettingsComponent.confirmPopulateAll) since it's destructive
    the same way /clear is."""
    location = db.query(Location).filter(Location.tenant_id == current.tenant_id).first()
    if location is None:
        return PopulateAllResponse(
            entries_deleted=0, targets_deleted=0, entries_created=0, entries_errors=0, targets_activated=0, targets_errors=0
        )

    location_ids = [loc.id for loc in db.query(Location).filter(Location.tenant_id == current.tenant_id).all()]
    entries_deleted = db.query(Entry).filter(Entry.location_id.in_(location_ids)).delete(synchronize_session=False)
    targets_deleted = db.query(EmissionTarget).filter(EmissionTarget.tenant_id == current.tenant_id).delete(synchronize_session=False)
    ensure_demo_emission_factors(db, current.tenant_id, current.id)
    db.commit()

    entry_rows = demo_entry_rows(db, current.tenant_id)
    entries_payload = BulkImportRequest(
        location_id=location.id,
        category=None,
        commit=True,
        rows=[
            BulkImportRowIn(
                row_index=i,
                category=row["category"],
                data_point_name=row["data_point_name"],
                year=row["year"],
                month=row["month"],
                value_raw=str(row["value"]),
                unit_raw=row["unit"],
                note=row["note"],
            )
            for i, row in enumerate(entry_rows)
        ],
    )
    entries_result = await bulk_import(entries_payload, current, db)

    target_rows = demo_target_rows()
    targets_payload = TargetBulkImportRequest(
        commit=True,
        rows=[TargetBulkRowIn(row_index=i, **row) for i, row in enumerate(target_rows)],
    )
    targets_result = bulk_import_targets(targets_payload, current, db)

    return PopulateAllResponse(
        entries_deleted=entries_deleted,
        targets_deleted=targets_deleted,
        entries_created=entries_result.created_count,
        entries_errors=entries_result.error_count,
        targets_activated=targets_result.activated_count,
        targets_errors=targets_result.error_count,
    )


@router.get("/entries-workbook")
def download_entries_workbook(
    current: CurrentUser = Depends(require_roles("Admin")),
    db: Session = Depends(get_db),
):
    # Belt-and-braces alongside /clear -- guarantees the factors this
    # workbook's entries need exist at the moment someone is actually about
    # to upload it, even if /clear ran a while ago or was skipped entirely.
    ensure_demo_emission_factors(db, current.tenant_id, current.id)
    db.commit()
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
