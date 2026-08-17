import csv
import io
import uuid
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, require_roles
from app.core.config import get_settings
from app.core.supabase_storage import upload_file
from app.core.unit_conversion import convert_unit, units_equivalent
from app.db.models import (
    Approval,
    AuditLog,
    Attachment,
    Category,
    ColumnMappingMemory,
    DataPoint,
    EmailLog,
    Entry,
    Location,
    MappingTemplate,
    Tenant,
    User,
)
from app.db.session import get_db
from app.schemas.entries import (
    AttachmentOut,
    AuditLogOut,
    BulkImportRequest,
    BulkImportResponse,
    BulkImportRowIn,
    BulkImportRowResult,
    CategoryOut,
    DataPointOut,
    EntryOut,
    EntryUpsertRequest,
    LastValueEntry,
    LastValueOut,
    RejectRequest,
    SubmitRequest,
)
from app.schemas.mapping import (
    ColumnSuggestion,
    DetectRequest,
    DetectResponse,
    MappingTemplateOut,
    SaveTemplateRequest,
    SheetDetectionResult,
)
from app.services.audit import write_audit
from app.services.carbon_calculation import calculate_entry
from app.services.mailing import MailingError, send_email
from app.services.mapping import header_fingerprint, infer_period, match_category, match_data_point, match_metadata_field, normalize
from app.services.rollups import recompute_rollup_for_entry

router = APIRouter(prefix="/entries", tags=["entries"])


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

    latest_rejection_note = None
    if entry.status == "Rejected":
        latest_reject = (
            db.query(Approval)
            .filter(Approval.entry_id == entry.id, Approval.action == "reject")
            .order_by(Approval.timestamp.desc())
            .first()
        )
        latest_rejection_note = latest_reject.reject_note if latest_reject else None

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
        latest_rejection_note=latest_rejection_note,
    )


@router.get("/categories", response_model=list[CategoryOut])
def list_categories(current: CurrentUser = Depends(require_roles("Admin", "Manager", "Approver")), db: Session = Depends(get_db)):
    categories = (
        db.query(Category).filter(Category.tenant_id == current.tenant_id).order_by(Category.display_order).all()
    )
    # One query for every data point across all categories, instead of one query per category.
    all_data_points = (
        db.query(DataPoint)
        .join(Category, Category.id == DataPoint.category_id)
        .filter(Category.tenant_id == current.tenant_id)
        .order_by(DataPoint.name)
        .all()
    )
    points_by_category: dict[uuid.UUID, list[DataPoint]] = {}
    for dp in all_data_points:
        points_by_category.setdefault(dp.category_id, []).append(dp)

    out = []
    for category in categories:
        dp_out = [
            DataPointOut(
                id=dp.id,
                name=dp.name,
                unit=dp.unit,
                input_type=dp.input_type,
                is_provisional=_is_provisional(dp.validation_rules),
                tooltip=(dp.validation_rules or {}).get("tooltip"),
                example=(dp.validation_rules or {}).get("example"),
            )
            for dp in points_by_category.get(category.id, [])
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


@router.get("/last-values", response_model=list[LastValueEntry])
def last_values_batch(
    category: str,
    location_id: uuid.UUID,
    before_period: date,
    current: CurrentUser = Depends(require_roles("Admin", "Manager", "Approver")),
    db: Session = Depends(get_db),
):
    """Same as /last-value but for every data point in a category at once --
    one query instead of one round trip per field, which is what was making
    the entry form slow to open on categories with many fields."""
    data_point_ids = [
        dp.id
        for dp in (
            db.query(DataPoint)
            .join(Category, Category.id == DataPoint.category_id)
            .filter(Category.tenant_id == current.tenant_id, Category.name == category)
            .all()
        )
    ]
    if not data_point_ids:
        return []

    rows = (
        db.query(Entry.data_point_id, Entry.value, Entry.period)
        .filter(
            Entry.data_point_id.in_(data_point_ids),
            Entry.location_id == location_id,
            Entry.status == "Approved",
            Entry.period < before_period,
        )
        .order_by(Entry.data_point_id, Entry.period.desc())
        .distinct(Entry.data_point_id)
        .all()
    )
    return [
        LastValueEntry(data_point_id=dp_id, value=float(value) if value is not None else None, period=period)
        for dp_id, value, period in rows
    ]


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


def _upsert_one(
    db: Session,
    current: CurrentUser,
    data_point_id: uuid.UUID,
    location_id: uuid.UUID,
    period: date,
    value: float | None,
    note: str | None,
    meter_id: str | None = None,
    method_of_entry: str = "Manual",
    target_status: str = "Draft",
    audit_action: str | None = None,
) -> Entry:
    entry = (
        db.query(Entry)
        .filter(Entry.data_point_id == data_point_id, Entry.location_id == location_id, Entry.period == period)
        .first()
    )
    if entry is not None and entry.status not in ("Draft", "Rejected"):
        raise HTTPException(status_code=409, detail=f"Entry for this field is already {entry.status.lower()}")

    if entry is None:
        entry = Entry(
            data_point_id=data_point_id,
            location_id=location_id,
            period=period,
            value=value,
            note=note,
            meter_id=meter_id,
            method_of_entry=method_of_entry,
            status=target_status,
            submitted_by=current.id,
        )
        db.add(entry)
        db.commit()
        db.refresh(entry)
        write_audit(db, entry.id, current.email, audit_action or "created", None, str(value))
    else:
        old_value = str(entry.value) if entry.value is not None else None
        entry.value = value
        entry.note = note
        entry.meter_id = meter_id
        entry.method_of_entry = method_of_entry
        entry.status = target_status
        entry.submitted_by = current.id
        db.commit()
        db.refresh(entry)
        write_audit(db, entry.id, current.email, audit_action or "edited", old_value, str(value))

    return entry


@router.post("", response_model=list[EntryOut])
def upsert_entries(
    payload: list[EntryUpsertRequest],
    current: CurrentUser = Depends(require_roles("Admin", "Manager")),
    db: Session = Depends(get_db),
):
    results = []
    for item in payload:
        entry = _upsert_one(db, current, item.data_point_id, item.location_id, item.period, item.value, item.note, item.meter_id)
        results.append(_entry_out(db, entry))
    return results


@router.post("/bulk-import/detect", response_model=DetectResponse)
def detect_bulk_import(
    payload: DetectRequest,
    current: CurrentUser = Depends(require_roles("Admin", "Manager")),
    db: Session = Depends(get_db),
):
    """Fully deterministic: exact alias hit -> fuzzy match -> unmatched. No
    AI/LLM call. Per sheet: guesses which category it belongs to (from the
    sheet name, falling back to the filename), then maps each column header
    either to a metadata field (period/note) or directly to one of that
    category's data points. If a mapping was confirmed before for this exact
    header signature, it's reused and the customer skips straight to preview."""
    categories = db.query(Category).filter(Category.tenant_id == current.tenant_id).all()
    category_names = [c.name for c in categories]
    categories_by_name = {c.name: c for c in categories}

    all_data_points = (
        db.query(DataPoint)
        .join(Category, Category.id == DataPoint.category_id)
        .filter(Category.tenant_id == current.tenant_id)
        .all()
    )
    dp_by_category: dict[uuid.UUID, list[tuple[str, str]]] = {}
    dp_name_by_id: dict[str, str] = {}
    for dp in all_data_points:
        dp_by_category.setdefault(dp.category_id, []).append((str(dp.id), dp.name))
        dp_name_by_id[str(dp.id)] = dp.name

    results: list[SheetDetectionResult] = []
    for sheet in payload.sheets:
        fingerprint = header_fingerprint(sheet.headers)

        cat_match = match_category(sheet.name, category_names)
        if cat_match.key is None:
            cat_match = match_category(sheet.filename, category_names)
        category = categories_by_name.get(cat_match.key) if cat_match.key else None

        template = None
        if category is not None:
            template = (
                db.query(MappingTemplate)
                .filter(
                    MappingTemplate.tenant_id == current.tenant_id,
                    MappingTemplate.category_id == category.id,
                    MappingTemplate.header_fingerprint == fingerprint,
                )
                .first()
            )

        columns: list[ColumnSuggestion] = []
        if template is not None:
            for header in sheet.headers:
                target = template.column_mapping.get(header)
                if target in ("period", "note"):
                    columns.append(ColumnSuggestion(header=header, target=target, target_type="metadata", score=1.0, rule="template"))
                elif target:
                    columns.append(
                        ColumnSuggestion(
                            header=header,
                            target=target,
                            target_type="data_point",
                            data_point_name=dp_name_by_id.get(target),
                            score=1.0,
                            rule="template",
                        )
                    )
                else:
                    columns.append(ColumnSuggestion(header=header, target=None, target_type="unmatched", score=1.0, rule="template"))
        elif category is not None:
            category_dps = dp_by_category.get(category.id, [])
            memory_by_header = {
                m.source_header: m
                for m in db.query(ColumnMappingMemory).filter(
                    ColumnMappingMemory.tenant_id == current.tenant_id,
                    ColumnMappingMemory.category_id == category.id,
                )
            }
            for header in sheet.headers:
                mem = memory_by_header.get(normalize(header))
                if mem is not None:
                    columns.append(
                        ColumnSuggestion(
                            header=header,
                            target=mem.target,
                            target_type=mem.target_type,
                            data_point_name=dp_name_by_id.get(mem.target) if mem.target_type == "data_point" else None,
                            score=mem.confidence,
                            rule="memory",
                        )
                    )
                    continue

                meta_match = match_metadata_field(header)
                if meta_match.key:
                    columns.append(
                        ColumnSuggestion(header=header, target=meta_match.key, target_type="metadata", score=meta_match.score, rule=meta_match.rule)
                    )
                    continue
                dp_match, dp_id = match_data_point(header, category_dps)
                if dp_id:
                    columns.append(
                        ColumnSuggestion(
                            header=header,
                            target=dp_id,
                            target_type="data_point",
                            data_point_name=dp_name_by_id.get(dp_id),
                            score=dp_match.score,
                            rule=dp_match.rule,
                        )
                    )
                else:
                    columns.append(ColumnSuggestion(header=header, target=None, target_type="unmatched", score=dp_match.score, rule="no_match"))
        else:
            columns = [ColumnSuggestion(header=h, target=None, target_type="unmatched", score=0.0, rule="no_match") for h in sheet.headers]

        has_period_column = any(c.target == "period" for c in columns)
        inferred_period = None if has_period_column else infer_period(sheet.name, sheet.filename)

        results.append(
            SheetDetectionResult(
                sheet_name=sheet.name,
                header_fingerprint=fingerprint,
                category_id=category.id if category else None,
                category_name=category.name if category else None,
                category_score=cat_match.score,
                category_rule=cat_match.rule,
                columns=columns,
                inferred_period=inferred_period,
                from_template=template is not None,
                template_id=template.id if template else None,
            )
        )

    return DetectResponse(sheets=results)


@router.post("/bulk-import/save-template", response_model=MappingTemplateOut)
def save_mapping_template(
    payload: SaveTemplateRequest,
    current: CurrentUser = Depends(require_roles("Admin", "Manager")),
    db: Session = Depends(get_db),
):
    category = db.get(Category, payload.category_id)
    if category is None or category.tenant_id != current.tenant_id:
        raise HTTPException(status_code=404, detail="Category not found")

    template = (
        db.query(MappingTemplate)
        .filter(
            MappingTemplate.tenant_id == current.tenant_id,
            MappingTemplate.category_id == payload.category_id,
            MappingTemplate.header_fingerprint == payload.header_fingerprint,
        )
        .first()
    )
    if template is None:
        template = MappingTemplate(
            tenant_id=current.tenant_id,
            category_id=payload.category_id,
            header_fingerprint=payload.header_fingerprint,
            column_mapping=payload.column_mapping,
            created_by=current.id,
        )
        db.add(template)
    else:
        template.column_mapping = payload.column_mapping

    # Also remember each column individually (not just this exact whole-file
    # signature) so a future file with the same header renamed/reordered/
    # mixed with new columns still gets this header right without asking again.
    for header, target in payload.column_mapping.items():
        if not target:
            continue
        norm_header = normalize(header)
        if not norm_header:
            continue
        mem = (
            db.query(ColumnMappingMemory)
            .filter(
                ColumnMappingMemory.tenant_id == current.tenant_id,
                ColumnMappingMemory.category_id == payload.category_id,
                ColumnMappingMemory.source_header == norm_header,
            )
            .first()
        )
        if mem is None:
            mem = ColumnMappingMemory(
                tenant_id=current.tenant_id,
                category_id=payload.category_id,
                source_header=norm_header,
                confirmed_by=current.id,
            )
            db.add(mem)
        mem.target_type = "metadata" if target in ("period", "note") else "data_point"
        mem.target = target
        mem.confidence = 1.0
        mem.source = "manual_confirm"
        mem.updated_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(template)

    return MappingTemplateOut(
        id=template.id,
        category_id=template.category_id,
        category_name=category.name,
        header_fingerprint=template.header_fingerprint,
        column_mapping=template.column_mapping,
        created_at=template.created_at,
        updated_at=template.updated_at,
    )


@router.get("/csv-template")
def csv_template(
    category: str | None = None,
    current: CurrentUser = Depends(require_roles("Admin", "Manager")),
    db: Session = Depends(get_db),
):
    """category=None downloads one combined template covering every
    category at once -- a Category column disambiguates the handful of
    field names that exist under more than one category (e.g. "Total
    Treated Effluent Generated" under both ETP-Water and STP-Water)."""
    q = (
        db.query(DataPoint, Category.name)
        .join(Category, Category.id == DataPoint.category_id)
        .filter(Category.tenant_id == current.tenant_id)
    )
    if category is not None:
        q = q.filter(Category.name == category)
    rows = q.order_by(Category.display_order, DataPoint.name).all()

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    # No Period column by default -- the wizard's own period selector covers
    # the common single-month case. Add one yourself (any header like
    # "Period" or "Month") if you want to backfill several months at once.
    if category is None:
        writer.writerow(["category", "data_point_name", "value", "unit", "note"])
        for dp, cat_name in rows:
            writer.writerow([cat_name, dp.name, "", dp.unit or "", ""])
        filename = "all_categories_template.csv"
    else:
        writer.writerow(["data_point_name", "value", "unit", "note"])
        for dp, _ in rows:
            writer.writerow([dp.name, "", dp.unit or "", ""])
        filename = f"{category.replace(' ', '_')}_template.csv"

    return Response(
        # UTF-8 BOM prefix: without it, Excel opens the file using the
        # system codepage (Windows-1252) instead of UTF-8, mangling the
        # em dash in data point names like "Battery Waste -- Incinerated"
        # into "â€"". The BOM makes Excel detect UTF-8 correctly.
        content="\ufeff" + buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/bulk-import", response_model=BulkImportResponse)
def bulk_import(
    payload: BulkImportRequest,
    current: CurrentUser = Depends(require_roles("Admin", "Manager")),
    db: Session = Depends(get_db),
):
    """Validates (commit=False) or creates (commit=True) a batch of rows the
    frontend has already parsed and column-mapped from an uploaded file.
    Every row is re-validated here regardless -- duplicate-within-file and
    duplicate-against-existing-entries checks need DB truth the client
    doesn't have.

    payload.category is None for the "all categories" upload -- rows are
    then matched by (row.category, data_point_name) since a handful of
    field names exist under more than one category (e.g. "Total Treated
    Effluent Generated" under both ETP-Water and STP-Water); a row with no
    category that matches more than one is an ambiguity error, not a
    guess."""
    q = db.query(DataPoint, Category.name).join(Category, Category.id == DataPoint.category_id).filter(
        Category.tenant_id == current.tenant_id
    )
    if payload.category is not None:
        q = q.filter(Category.name == payload.category)
    all_rows = q.all()

    by_cat_and_name: dict[tuple[str, str], DataPoint] = {}
    by_name_only: dict[str, list[tuple[DataPoint, str]]] = {}
    for dp, cat_name in all_rows:
        by_cat_and_name[(cat_name.strip().lower(), dp.name.strip().lower())] = dp
        by_name_only.setdefault(dp.name.strip().lower(), []).append((dp, cat_name))

    def resolve_data_point(row: BulkImportRowIn) -> tuple[DataPoint | None, str | None, str | None]:
        """Returns (data_point, category_name, error_message)."""
        name_key = row.data_point_name.strip().lower()
        if payload.category is not None:
            dp = by_cat_and_name.get((payload.category.strip().lower(), name_key))
            return (dp, payload.category, None) if dp else (None, None, f"'{row.data_point_name}' is not a field in {payload.category}")

        if row.category:
            dp = by_cat_and_name.get((row.category.strip().lower(), name_key))
            if dp is None:
                return None, None, f"'{row.data_point_name}' is not a field in '{row.category}'"
            return dp, row.category, None

        candidates = by_name_only.get(name_key, [])
        if len(candidates) == 0:
            return None, None, f"'{row.data_point_name}' does not match any field in this tenant"
        if len(candidates) > 1:
            options = ", ".join(sorted({c[1] for c in candidates}))
            return None, None, f"'{row.data_point_name}' exists in more than one category ({options}) -- add a Category column to specify which"
        dp, cat_name = candidates[0]
        return dp, cat_name, None

    results: list[BulkImportRowResult] = []
    seen_in_file: set[tuple[uuid.UUID, date]] = set()

    for row in payload.rows:
        dp, resolved_category, resolve_error = resolve_data_point(row)
        if dp is None:
            results.append(
                BulkImportRowResult(
                    row_index=row.row_index,
                    status="error",
                    data_point_name=row.data_point_name,
                    period=None,
                    value=None,
                    message=resolve_error,
                )
            )
            continue

        row_period_iso = row.period_iso.strip()
        period = None
        if row_period_iso:
            try:
                period = date.fromisoformat(row_period_iso)
            except ValueError:
                period = None
        if period is None and payload.default_period:
            try:
                period = date.fromisoformat(payload.default_period)
            except ValueError:
                period = None
        if period is None:
            if not row_period_iso and not payload.default_period:
                message = "No period given, and no default period was set for this upload"
            elif row_period_iso:
                message = f"Could not parse period '{row_period_iso}'"
            else:
                message = f"Could not parse default period '{payload.default_period}'"
            results.append(
                BulkImportRowResult(
                    row_index=row.row_index,
                    status="error",
                    data_point_name=row.data_point_name,
                    period=None,
                    value=None,
                    message=message,
                )
            )
            continue

        try:
            value = float(row.value_raw)
        except ValueError:
            results.append(
                BulkImportRowResult(
                    row_index=row.row_index,
                    status="error",
                    data_point_name=row.data_point_name,
                    period=period,
                    value=None,
                    message=f"'{row.value_raw}' is not a number",
                )
            )
            continue

        unit_note = None
        if row.unit_raw and dp.unit and not units_equivalent(row.unit_raw, dp.unit):
            converted = convert_unit(value, row.unit_raw, dp.unit)
            if converted is None:
                results.append(
                    BulkImportRowResult(
                        row_index=row.row_index,
                        status="error",
                        data_point_name=row.data_point_name,
                        period=period,
                        value=value,
                        message=f"'{row.unit_raw}' isn't recognized as, or convertible to, the expected unit '{dp.unit}'",
                        suggested_unit=dp.unit,
                    )
                )
                continue
            unit_note = f"Converted {value:g} {row.unit_raw} → {converted:g} {dp.unit}"
            value = converted

        key = (dp.id, period)
        if key in seen_in_file:
            results.append(
                BulkImportRowResult(
                    row_index=row.row_index,
                    status="error",
                    data_point_name=row.data_point_name,
                    period=period,
                    value=value,
                    message="Duplicate field + period elsewhere in this file",
                )
            )
            continue

        existing = (
            db.query(Entry)
            .filter(Entry.data_point_id == dp.id, Entry.location_id == payload.location_id, Entry.period == period)
            .first()
        )
        if existing is not None and existing.status not in ("Draft", "Rejected"):
            results.append(
                BulkImportRowResult(
                    row_index=row.row_index,
                    status="error",
                    data_point_name=row.data_point_name,
                    period=period,
                    value=value,
                    message=f"An entry for this field and period is already {existing.status.lower()}",
                )
            )
            continue

        seen_in_file.add(key)

        if not payload.commit:
            results.append(
                BulkImportRowResult(
                    row_index=row.row_index,
                    status="valid",
                    data_point_name=row.data_point_name,
                    period=period,
                    value=value,
                    unit_note=unit_note,
                    category=resolved_category,
                )
            )
            continue

        entry = _upsert_one(
            db,
            current,
            dp.id,
            payload.location_id,
            period,
            value,
            row.note,
            method_of_entry="Bulk Upload",
            target_status="Submitted",
            audit_action="bulk_uploaded",
        )
        results.append(
            BulkImportRowResult(
                row_index=row.row_index,
                status="created",
                data_point_name=row.data_point_name,
                period=period,
                value=value,
                entry_id=entry.id,
                unit_note=unit_note,
                category=resolved_category,
            )
        )

    return BulkImportResponse(
        rows=results,
        valid_count=sum(1 for r in results if r.status == "valid"),
        error_count=sum(1 for r in results if r.status == "error"),
        created_count=sum(1 for r in results if r.status == "created"),
    )


def _approve_entry_now(db: Session, entry: Entry, tenant_id, actor_id, actor_email: str, auto: bool) -> None:
    """Shared by a human Approver's decision and tenant-level
    auto-approval -- same status transition, same Approval/audit trail,
    same rollup + GHG recalculation, so an auto-approved entry is
    indistinguishable in every downstream calculation from a manually
    approved one. Only the audit trail's wording marks it as automatic."""
    entry.status = "Approved"
    db.add(Approval(entry_id=entry.id, approver_id=actor_id, action="approve"))
    db.commit()
    action = "auto_approved" if auto else "approved"
    note = "Auto-approved (tenant setting)" if auto else "Approved"
    write_audit(db, entry.id, actor_email, action, "Submitted", note)
    recompute_rollup_for_entry(db, entry)
    calculate_entry(db, entry, tenant_id, actor_id)
    db.commit()


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
    tenant = db.get(Tenant, current.tenant_id)
    auto_approve = bool(tenant and tenant.auto_approve_entries)
    for entry in rows:
        entry.status = "Submitted"
        db.commit()
        write_audit(db, entry.id, current.email, "submitted", "Draft", "Submitted")
        if auto_approve:
            _approve_entry_now(db, entry, current.tenant_id, current.id, current.email, auto=True)
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

    _approve_entry_now(db, entry, current.tenant_id, current.id, current.email, auto=False)

    return _entry_out(db, entry)


@router.post("/{entry_id}/reject", response_model=EntryOut)
async def reject_entry(
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

    await _send_rejection_email(db, entry, payload.reject_note)

    return _entry_out(db, entry)


async def _send_rejection_email(db: Session, entry: Entry, reject_note: str) -> None:
    if entry.submitted_by is None:
        return
    submitter = db.get(User, entry.submitted_by)
    if submitter is None:
        return

    dp = db.get(DataPoint, entry.data_point_id)
    category = db.get(Category, dp.category_id)
    settings = get_settings()
    link = f"{settings.frontend_url}/admin/data-entry?category={category.name}&period={entry.period.isoformat()[:7]}"
    subject = f"Enviqo: {category.name} entry for {entry.period.strftime('%B %Y')} was rejected"
    html_body = (
        f"<p>Your submission for <strong>{dp.name}</strong> ({category.name}, {entry.period.strftime('%B %Y')}) "
        f"was rejected.</p>"
        f"<p><strong>Reason:</strong> {reject_note}</p>"
        f'<p><a href="{link}">Open this entry in Enviqo</a> to fix and resubmit it.</p>'
    )
    text_body = (
        f"Your submission for {dp.name} ({category.name}, {entry.period.strftime('%B %Y')}) was rejected.\n\n"
        f"Reason: {reject_note}\n\nFix and resubmit: {link}"
    )

    status = "sent"
    try:
        await send_email(submitter.email, subject, html_body, text_body)
    except MailingError:
        status = "failed"
    db.add(EmailLog(recipient=submitter.email, subject=subject, related_id=entry.id, status=status))
    db.commit()


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
