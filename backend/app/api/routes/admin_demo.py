"""Settings -> Approval Settings -> Simulate Sample: an Admin-only, tenant-
scoped destructive reset plus three downloadable sample workbooks, so a
demo can start from a clean slate and repopulate itself end-to-end through
the app's own Bulk Upload flows -- nothing here writes an entry, factor,
or target directly, with one exception (populate_all_demo_data, see there)."""

import uuid

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel
from sqlalchemy import update as sa_update
from sqlalchemy.orm import Session

from app.api.routes.entries import bulk_import
from app.api.routes.targets import bulk_import_targets
from app.core.auth import CurrentUser, require_roles
from app.db.models import Approval, AuditLog, Entry, EmissionTarget, Location, PeerData
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
from app.services.rollups import recompute_rollups_for_entries

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


class PopulateAllRequest(BaseModel):
    # Demo-only knobs: pull this many of the just-approved entries back
    # into Rejected/Submitted instead of leaving all 1275 pre-approved, so
    # there's real material to demo the reject-track-close workflow and a
    # live approval against, rather than a backdrop with nothing left to
    # act on. Both default to 0 (the original all-approved behavior).
    rejected_count: int = 0
    pending_count: int = 0


class PopulateAllResponse(BaseModel):
    entries_deleted: int
    targets_deleted: int
    entries_created: int
    entries_errors: int
    targets_activated: int
    targets_errors: int
    entries_rejected: int
    entries_pending: int


_DEMO_REJECT_NOTE = "Reported value looks out of range for this site/period -- please recheck the source reading and resubmit."


def _seed_demo_decisions(db: Session, to_reject: list[uuid.UUID], to_pending: list[uuid.UUID], current: CurrentUser) -> None:
    """Moves a handful of already-approved demo entries back to
    Rejected/Submitted -- direct status writes (not the normal single/bulk
    reject endpoints, which require Submitted as the starting state) since
    this is seeding a demo scenario, not a real reviewer decision."""
    if to_reject:
        db.execute(sa_update(Entry).where(Entry.id.in_(to_reject)).values(status="Rejected"))
        db.add_all(
            [Approval(entry_id=eid, approver_id=current.id, action="reject", reject_note=_DEMO_REJECT_NOTE) for eid in to_reject]
        )
        db.add_all(
            [
                AuditLog(entry_id=eid, actor=current.email, action="rejected", old_value="Approved", new_value=f"Rejected: {_DEMO_REJECT_NOTE}")
                for eid in to_reject
            ]
        )
    if to_pending:
        db.execute(sa_update(Entry).where(Entry.id.in_(to_pending)).values(status="Submitted"))
        db.add_all(
            [
                AuditLog(entry_id=eid, actor=current.email, action="reverted_to_submitted", old_value="Approved", new_value="Submitted")
                for eid in to_pending
            ]
        )
    db.commit()

    # Approved-only aggregates (Rollup) need to stop counting whichever of
    # these just stopped being Approved -- recompute_rollups_for_entries()
    # always does a fresh SUM against current status, so this is safe to
    # call after the status change above rather than before it.
    changed = db.query(Entry).filter(Entry.id.in_(to_reject + to_pending)).all()
    if changed:
        recompute_rollups_for_entries(db, changed)
        db.commit()


@router.post("/populate-all", response_model=PopulateAllResponse)
async def populate_all_demo_data(
    payload: PopulateAllRequest = PopulateAllRequest(),
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
    the same way /clear is.

    payload.rejected_count/pending_count optionally pull a few of the
    entries from the most recent demo month back out of Approved
    afterward, so the demo has a couple of real Rejected entries to track
    and close, and a couple of real Submitted ones to approve live,
    instead of a dataset where everything already happened."""
    location = db.query(Location).filter(Location.tenant_id == current.tenant_id).first()
    if location is None:
        return PopulateAllResponse(
            entries_deleted=0, targets_deleted=0, entries_created=0, entries_errors=0,
            targets_activated=0, targets_errors=0, entries_rejected=0, entries_pending=0,
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

    rejected_count = max(0, payload.rejected_count)
    pending_count = max(0, payload.pending_count)
    total_needed = rejected_count + pending_count
    entries_rejected = entries_pending = 0
    if total_needed > 0:
        # The tail of the created rows is the most recent demo month (rows
        # are generated month-major, oldest first) -- picking from there
        # means whatever the dashboard shows by default already includes
        # the seeded Rejected/Submitted entries.
        created_ids = [r.entry_id for r in entries_result.rows if r.entry_id is not None]
        tail = created_ids[-total_needed:]
        to_reject = tail[:rejected_count]
        to_pending = tail[rejected_count:]
        _seed_demo_decisions(db, to_reject, to_pending, current)
        entries_rejected = len(to_reject)
        entries_pending = len(to_pending)

    return PopulateAllResponse(
        entries_deleted=entries_deleted,
        targets_deleted=targets_deleted,
        entries_created=entries_result.created_count,
        entries_errors=entries_result.error_count,
        targets_activated=targets_result.activated_count,
        targets_errors=targets_result.error_count,
        entries_rejected=entries_rejected,
        entries_pending=entries_pending,
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
