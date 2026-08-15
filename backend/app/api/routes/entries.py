import uuid
from datetime import date

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, require_roles
from app.core.supabase_storage import upload_file
from app.db.models import Approval, AuditLog, Attachment, Category, DataPoint, Entry, Location, User
from app.db.session import get_db
from app.schemas.entries import (
    AttachmentOut,
    AuditLogOut,
    CategoryOut,
    DataPointOut,
    EntryOut,
    EntryUpsertRequest,
    LastValueOut,
    RejectRequest,
    SubmitRequest,
)
from app.services.audit import write_audit
from app.services.rollups import recompute_rollup_for_entry

router = APIRouter(prefix="/entries", tags=["entries"])

CLASSIC_MODE_CATEGORIES = {"ETP-Water", "STP-Water", "Air Emissions"}


def _is_provisional(validation_rules: dict | None) -> bool:
    return bool(validation_rules and validation_rules.get("provisional"))


def _entry_out(db: Session, entry: Entry) -> EntryOut:
    dp = db.get(DataPoint, entry.data_point_id)
    category = db.get(Category, dp.category_id)
    location = db.get(Location, entry.location_id)
    submitter_email = None
    if entry.submitted_by:
        submitter = db.get(User, entry.submitted_by)
        submitter_email = submitter.email if submitter else None
    return EntryOut(
        id=entry.id,
        data_point_id=entry.data_point_id,
        data_point_name=dp.name,
        category_name=category.name,
        location_id=entry.location_id,
        location_name=location.name,
        period=entry.period,
        value=float(entry.value) if entry.value is not None else None,
        status=entry.status,
        note=entry.note,
        submitted_by=entry.submitted_by,
        submitted_by_email=submitter_email,
    )


@router.get("/categories", response_model=list[CategoryOut])
def list_categories(current: CurrentUser = Depends(require_roles("Admin", "Manager", "Approver")), db: Session = Depends(get_db)):
    categories = (
        db.query(Category).filter(Category.tenant_id == current.tenant_id).order_by(Category.display_order).all()
    )
    out = []
    for category in categories:
        data_points = db.query(DataPoint).filter(DataPoint.category_id == category.id).order_by(DataPoint.name).all()
        default_mode = "classic" if category.name in CLASSIC_MODE_CATEGORIES else "guided"
        dp_out = [
            DataPointOut(
                id=dp.id,
                name=dp.name,
                unit=dp.unit,
                input_type=dp.input_type,
                default_mode=default_mode,
                is_provisional=_is_provisional(dp.validation_rules),
            )
            for dp in data_points
        ]
        out.append(
            CategoryOut(
                id=category.id,
                name=category.name,
                display_order=category.display_order,
                is_provisional=any(d.is_provisional for d in dp_out),
                data_points=dp_out,
            )
        )
    return out


@router.get("/last-value", response_model=LastValueOut)
def last_value(
    data_point_id: uuid.UUID,
    location_id: uuid.UUID,
    before_period: date,
    current: CurrentUser = Depends(require_roles("Admin", "Manager", "Approver")),
    db: Session = Depends(get_db),
):
    entry = (
        db.query(Entry)
        .filter(
            Entry.data_point_id == data_point_id,
            Entry.location_id == location_id,
            Entry.period < before_period,
            Entry.status == "Approved",
        )
        .order_by(Entry.period.desc())
        .first()
    )
    if entry is None:
        return LastValueOut(value=None, period=None)
    return LastValueOut(value=float(entry.value) if entry.value is not None else None, period=entry.period)


@router.get("/current", response_model=list[EntryOut])
def current_entries(
    category: str,
    period: date,
    location_id: uuid.UUID,
    current: CurrentUser = Depends(require_roles("Admin", "Manager", "Approver")),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(Entry)
        .join(DataPoint, DataPoint.id == Entry.data_point_id)
        .join(Category, Category.id == DataPoint.category_id)
        .filter(
            Category.tenant_id == current.tenant_id,
            Category.name == category,
            Entry.period == period,
            Entry.location_id == location_id,
        )
        .all()
    )
    return [_entry_out(db, e) for e in rows]


@router.post("", response_model=list[EntryOut])
def upsert_entries(
    payload: list[EntryUpsertRequest],
    current: CurrentUser = Depends(require_roles("Admin", "Manager")),
    db: Session = Depends(get_db),
):
    results = []
    for item in payload:
        entry = (
            db.query(Entry)
            .filter(
                Entry.data_point_id == item.data_point_id,
                Entry.location_id == item.location_id,
                Entry.period == item.period,
            )
            .first()
        )
        if entry is not None and entry.status not in ("Draft", "Rejected"):
            raise HTTPException(status_code=409, detail=f"Entry for this field is already {entry.status.lower()}")

        if entry is None:
            entry = Entry(
                data_point_id=item.data_point_id,
                location_id=item.location_id,
                period=item.period,
                value=item.value,
                note=item.note,
                meter_id=item.meter_id,
                method_of_entry="Manual",
                status="Draft",
                submitted_by=current.id,
            )
            db.add(entry)
            db.commit()
            db.refresh(entry)
            write_audit(db, entry.id, current.email, "created", None, str(item.value))
        else:
            old_value = str(entry.value) if entry.value is not None else None
            entry.value = item.value
            entry.note = item.note
            entry.meter_id = item.meter_id
            entry.status = "Draft"
            entry.submitted_by = current.id
            db.commit()
            db.refresh(entry)
            write_audit(db, entry.id, current.email, "edited", old_value, str(item.value))

        results.append(_entry_out(db, entry))
    return results


@router.post("/submit", response_model=list[EntryOut])
def submit_entries(
    payload: SubmitRequest,
    current: CurrentUser = Depends(require_roles("Admin", "Manager")),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(Entry)
        .join(DataPoint, DataPoint.id == Entry.data_point_id)
        .join(Category, Category.id == DataPoint.category_id)
        .filter(
            Category.tenant_id == current.tenant_id,
            Category.name == payload.category,
            Entry.period == payload.period,
            Entry.location_id == payload.location_id,
            Entry.status == "Draft",
        )
        .all()
    )
    for entry in rows:
        entry.status = "Submitted"
        db.commit()
        write_audit(db, entry.id, current.email, "submitted", "Draft", "Submitted")
    return [_entry_out(db, e) for e in rows]


@router.get("/queue", response_model=list[EntryOut])
def approval_queue(
    current: CurrentUser = Depends(require_roles("Admin", "Approver")),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(Entry)
        .join(DataPoint, DataPoint.id == Entry.data_point_id)
        .join(Category, Category.id == DataPoint.category_id)
        .filter(Category.tenant_id == current.tenant_id, Entry.status == "Submitted")
        .order_by(Entry.period.desc())
        .all()
    )
    return [_entry_out(db, e) for e in rows]


def _load_entry_for_decision(db: Session, entry_id: uuid.UUID, tenant_id) -> Entry:
    entry = db.get(Entry, entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Entry not found")
    dp = db.get(DataPoint, entry.data_point_id)
    category = db.get(Category, dp.category_id)
    if category.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Entry not found")
    if entry.status != "Submitted":
        raise HTTPException(status_code=409, detail=f"Entry is {entry.status.lower()}, not awaiting approval")
    return entry


@router.post("/{entry_id}/approve", response_model=EntryOut)
def approve_entry(
    entry_id: uuid.UUID,
    current: CurrentUser = Depends(require_roles("Admin", "Approver")),
    db: Session = Depends(get_db),
):
    entry = _load_entry_for_decision(db, entry_id, current.tenant_id)
    if entry.submitted_by is not None and str(entry.submitted_by) == str(current.id):
        raise HTTPException(status_code=403, detail="You cannot approve your own submission")

    entry.status = "Approved"
    db.add(Approval(entry_id=entry.id, approver_id=current.id, action="approve"))
    db.commit()
    write_audit(db, entry.id, current.email, "approved", "Submitted", "Approved")
    recompute_rollup_for_entry(db, entry)

    return _entry_out(db, entry)


@router.post("/{entry_id}/reject", response_model=EntryOut)
def reject_entry(
    entry_id: uuid.UUID,
    payload: RejectRequest,
    current: CurrentUser = Depends(require_roles("Admin", "Approver")),
    db: Session = Depends(get_db),
):
    if not payload.reject_note.strip():
        raise HTTPException(status_code=422, detail="A rejection note is required")

    entry = _load_entry_for_decision(db, entry_id, current.tenant_id)
    if entry.submitted_by is not None and str(entry.submitted_by) == str(current.id):
        raise HTTPException(status_code=403, detail="You cannot reject your own submission")

    entry.status = "Rejected"
    db.add(Approval(entry_id=entry.id, approver_id=current.id, action="reject", reject_note=payload.reject_note))
    db.commit()
    write_audit(db, entry.id, current.email, "rejected", "Submitted", f"Rejected: {payload.reject_note}")

    return _entry_out(db, entry)


@router.get("/{entry_id}/history", response_model=list[AuditLogOut])
def entry_history(
    entry_id: uuid.UUID,
    current: CurrentUser = Depends(require_roles("Admin", "Manager", "Approver")),
    db: Session = Depends(get_db),
):
    rows = db.query(AuditLog).filter(AuditLog.entry_id == entry_id).order_by(AuditLog.timestamp).all()
    return [
        AuditLogOut(id=r.id, actor=r.actor, action=r.action, old_value=r.old_value, new_value=r.new_value, timestamp=r.timestamp)
        for r in rows
    ]


@router.get("/{entry_id}/attachments", response_model=list[AttachmentOut])
def list_attachments(
    entry_id: uuid.UUID,
    current: CurrentUser = Depends(require_roles("Admin", "Manager", "Approver")),
    db: Session = Depends(get_db),
):
    rows = db.query(Attachment).filter(Attachment.entry_id == entry_id).order_by(Attachment.uploaded_at).all()
    return [
        AttachmentOut(id=r.id, file_url=r.file_url, file_type=r.file_type, uploaded_by=r.uploaded_by, uploaded_at=r.uploaded_at)
        for r in rows
    ]


@router.post("/{entry_id}/attachments", response_model=AttachmentOut, status_code=201)
async def upload_attachment(
    entry_id: uuid.UUID,
    file: UploadFile = File(...),
    current: CurrentUser = Depends(require_roles("Admin", "Manager", "Approver")),
    db: Session = Depends(get_db),
):
    entry = db.get(Entry, entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Entry not found")

    content = await file.read()
    path = f"{entry_id}/{uuid.uuid4()}-{file.filename}"
    file_url = upload_file(path, content, file.content_type or "application/octet-stream")

    attachment = Attachment(
        entry_id=entry_id,
        file_url=file_url,
        file_type=file.content_type,
        uploaded_by=current.id,
    )
    db.add(attachment)
    db.commit()
    db.refresh(attachment)
    write_audit(db, entry_id, current.email, "attachment_added", None, file.filename)

    return AttachmentOut(
        id=attachment.id,
        file_url=attachment.file_url,
        file_type=attachment.file_type,
        uploaded_by=attachment.uploaded_by,
        uploaded_at=attachment.uploaded_at,
    )
