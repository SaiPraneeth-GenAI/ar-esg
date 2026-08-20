import uuid
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, require_roles
from app.db.models import (
    EnergyAssuranceImportBatch,
    EnergyAssuranceMeter,
    EnergyAssuranceReading,
    EnergyAssuranceReference,
    EnergyAssuranceSite,
    EnergyAssuranceSource,
)
from app.db.session import get_db
from app.schemas.energy_assurance import (
    AssuranceSummaryOut,
    ImportRequest,
    ImportResponse,
    ImportRowResult,
    MeterIn,
    MeterOut,
    MeterUpdate,
    ReadingIn,
    ReadingOut,
    ReadingUpdate,
    ReconciliationOut,
    SiteOut,
    SourceIn,
    SourceOut,
    SourceUpdate,
    TraceInputOut,
    TraceOut,
    WorkspaceOut,
)
from app.services.energy_assurance import (
    GRID_FACTOR_KGCO2E_PER_KWH,
    assert_tenant,
    location_scope2,
    normalize_energy,
    reconcile_energy,
)

router = APIRouter(prefix="/energy-assurance", tags=["energy-assurance"])
VIEW_ROLES = ("Admin", "Manager", "Approver")
EDIT_ROLES = ("Admin", "Manager", "Approver")
SOURCE_TYPES = {"grid", "onsite_renewable", "offsite_renewable", "captive", "generator", "other"}
DIRECTIONS = {"import", "export", "generation", "consumption"}
READING_STATUSES = {"review", "approved", "rejected"}


def _site(db: Session, tenant_id, site_id: uuid.UUID) -> EnergyAssuranceSite:
    row = db.get(EnergyAssuranceSite, site_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Energy Assurance site not found")
    assert_tenant(row.tenant_id, tenant_id, "Energy Assurance site")
    return row


def _source(db: Session, tenant_id, source_id: uuid.UUID) -> EnergyAssuranceSource:
    row = db.get(EnergyAssuranceSource, source_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Energy source not found")
    assert_tenant(row.tenant_id, tenant_id, "Energy source")
    return row


def _meter(db: Session, tenant_id, meter_id: uuid.UUID) -> EnergyAssuranceMeter:
    row = db.get(EnergyAssuranceMeter, meter_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Meter not found")
    assert_tenant(row.tenant_id, tenant_id, "Meter")
    return row


def _reading(db: Session, tenant_id, reading_id: uuid.UUID) -> EnergyAssuranceReading:
    row = db.get(EnergyAssuranceReading, reading_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Reading not found")
    assert_tenant(row.tenant_id, tenant_id, "Reading")
    return row


def _source_out(source: EnergyAssuranceSource, meter_count: int = 0) -> SourceOut:
    return SourceOut(
        id=source.id,
        site_id=source.site_id,
        name=source.name,
        source_type=source.source_type,
        supplier=source.supplier,
        renewable=source.renewable,
        active=source.active,
        meter_count=meter_count,
    )


def _meter_out(meter: EnergyAssuranceMeter, source_name: str) -> MeterOut:
    return MeterOut(
        id=meter.id,
        site_id=meter.site_id,
        source_id=meter.source_id,
        source_name=source_name,
        meter_code=meter.meter_code,
        name=meter.name,
        unit=meter.unit,
        direction=meter.direction,
        active=meter.active,
    )


def _reading_out(reading: EnergyAssuranceReading, meter: EnergyAssuranceMeter, source: EnergyAssuranceSource) -> ReadingOut:
    normalized = normalize_energy(reading.value, reading.unit)
    return ReadingOut(
        id=reading.id,
        site_id=reading.site_id,
        source_id=reading.source_id,
        source_name=source.name,
        source_type=source.source_type,
        meter_id=reading.meter_id,
        meter_code=meter.meter_code,
        meter_name=meter.name,
        period=reading.period,
        value=float(reading.value),
        normalized_kwh=float(normalized) if normalized is not None else None,
        unit=reading.unit,
        evidence_reference=reading.evidence_reference,
        status=reading.status,
        quality_flags=list(reading.quality_flags or []),
        source_row=reading.source_row,
    )


@router.post("/demo-seed", response_model=SiteOut)
def seed_demo(
    current: CurrentUser = Depends(require_roles(*EDIT_ROLES)),
    db: Session = Depends(get_db),
):
    existing = (
        db.query(EnergyAssuranceSite)
        .filter(EnergyAssuranceSite.tenant_id == current.tenant_id, EnergyAssuranceSite.name == "Synthetic Battery Plant")
        .first()
    )
    if existing is not None:
        return SiteOut(id=existing.id, name=existing.name, description=existing.description, is_synthetic=existing.is_synthetic)

    site = EnergyAssuranceSite(
        tenant_id=current.tenant_id,
        name="Synthetic Battery Plant",
        description="Isolated showcase workspace. No customer operational data is used.",
        is_synthetic=True,
    )
    db.add(site)
    db.flush()

    source_specs = [
        ("Grid supply", "grid", "Demo DISCOM", False),
        ("Rooftop solar", "onsite_renewable", "On-site generation", True),
        ("Diesel generator", "generator", "Facility backup", False),
    ]
    sources: dict[str, EnergyAssuranceSource] = {}
    for name, source_type, supplier, renewable in source_specs:
        source = EnergyAssuranceSource(
            tenant_id=current.tenant_id,
            site_id=site.id,
            name=name,
            source_type=source_type,
            supplier=supplier,
            renewable=renewable,
        )
        db.add(source)
        db.flush()
        sources[source_type] = source

    meter_specs = [
        (sources["grid"], "GRID-MAIN-01", "Main grid incomer", "import"),
        (sources["onsite_renewable"], "SOLAR-INV-01", "Solar inverter 1", "generation"),
        (sources["onsite_renewable"], "SOLAR-INV-02", "Solar inverter 2", "generation"),
        (sources["generator"], "DG-METER-01", "Backup generator meter", "generation"),
    ]
    meters: dict[str, EnergyAssuranceMeter] = {}
    for source, code, name, direction in meter_specs:
        meter = EnergyAssuranceMeter(
            tenant_id=current.tenant_id,
            site_id=site.id,
            source_id=source.id,
            meter_code=code,
            name=name,
            unit="kWh",
            direction=direction,
        )
        db.add(meter)
        db.flush()
        meters[code] = meter

    period = date(2026, 8, 1)
    demo_readings = [
        (meters["GRID-MAIN-01"], sources["grid"], Decimal("98400"), "August grid bill — synthetic", []),
        (meters["SOLAR-INV-01"], sources["onsite_renewable"], Decimal("11000"), "Inverter statement A — synthetic", []),
        (meters["SOLAR-INV-02"], sources["onsite_renewable"], Decimal("10500"), None, ["evidence_missing"]),
    ]
    for row_number, (meter, source, value, evidence, flags) in enumerate(demo_readings, start=2):
        db.add(
            EnergyAssuranceReading(
                tenant_id=current.tenant_id,
                site_id=site.id,
                source_id=source.id,
                meter_id=meter.id,
                period=period,
                value=value,
                unit="kWh",
                evidence_reference=evidence,
                source_row=row_number,
                status="approved",
                quality_flags=flags,
                created_by=current.id,
            )
        )

    reference_specs = [
        (sources["grid"], "utility_bill", Decimal("100000"), "August electricity bill — synthetic"),
        (sources["onsite_renewable"], "renewable_claim", Decimal("24000"), "Renewable claim register — synthetic"),
        (sources["generator"], "generation_statement", Decimal("1850"), "DG operations register — synthetic"),
    ]
    for source, reference_type, value, evidence in reference_specs:
        db.add(
            EnergyAssuranceReference(
                tenant_id=current.tenant_id,
                site_id=site.id,
                source_id=source.id,
                period=period,
                reference_type=reference_type,
                reference_value=value,
                unit="kWh",
                evidence_reference=evidence,
            )
        )
    db.commit()
    db.refresh(site)
    return SiteOut(id=site.id, name=site.name, description=site.description, is_synthetic=site.is_synthetic)


@router.get("/workspace", response_model=WorkspaceOut)
def workspace(
    site_id: uuid.UUID | None = None,
    period: date = date(2026, 8, 1),
    current: CurrentUser = Depends(require_roles(*VIEW_ROLES)),
    db: Session = Depends(get_db),
):
    sites = db.query(EnergyAssuranceSite).filter(EnergyAssuranceSite.tenant_id == current.tenant_id).order_by(EnergyAssuranceSite.name).all()
    if not sites:
        raise HTTPException(status_code=404, detail="No Energy Assurance workspace. Load the synthetic demonstration first.")
    active_site = _site(db, current.tenant_id, site_id) if site_id else sites[0]

    sources = (
        db.query(EnergyAssuranceSource)
        .filter(EnergyAssuranceSource.tenant_id == current.tenant_id, EnergyAssuranceSource.site_id == active_site.id)
        .order_by(EnergyAssuranceSource.name)
        .all()
    )
    meters = (
        db.query(EnergyAssuranceMeter)
        .filter(EnergyAssuranceMeter.tenant_id == current.tenant_id, EnergyAssuranceMeter.site_id == active_site.id)
        .order_by(EnergyAssuranceMeter.meter_code)
        .all()
    )
    readings = (
        db.query(EnergyAssuranceReading)
        .filter(
            EnergyAssuranceReading.tenant_id == current.tenant_id,
            EnergyAssuranceReading.site_id == active_site.id,
            EnergyAssuranceReading.period == period,
        )
        .order_by(EnergyAssuranceReading.created_at)
        .all()
    )
    references = (
        db.query(EnergyAssuranceReference)
        .filter(
            EnergyAssuranceReference.tenant_id == current.tenant_id,
            EnergyAssuranceReference.site_id == active_site.id,
            EnergyAssuranceReference.period == period,
        )
        .all()
    )
    source_by_id = {s.id: s for s in sources}
    meter_by_id = {m.id: m for m in meters}
    reference_by_source = {r.source_id: r for r in references}
    readings_by_source: dict[uuid.UUID, list[EnergyAssuranceReading]] = {s.id: [] for s in sources}
    for reading in readings:
        readings_by_source.setdefault(reading.source_id, []).append(reading)

    reconciliations: list[ReconciliationOut] = []
    for source in sources:
        source_readings = readings_by_source.get(source.id, [])
        values = [n for r in source_readings if (n := normalize_energy(r.value, r.unit)) is not None and r.status != "rejected"]
        reference = reference_by_source.get(source.id)
        reference_kwh = normalize_energy(reference.reference_value, reference.unit) if reference else None
        result = reconcile_energy(values, reference_kwh)
        reconciliations.append(
            ReconciliationOut(
                source_id=source.id,
                source_name=source.name,
                source_type=source.source_type,
                meter_total_kwh=float(result.actual_kwh),
                reference_type=reference.reference_type if reference else None,
                reference_value_kwh=float(result.reference_kwh) if result.reference_kwh is not None else None,
                variance_kwh=float(result.variance_kwh) if result.variance_kwh is not None else None,
                variance_pct=float(result.variance_pct) if result.variance_pct is not None else None,
                status=result.status,
                message=result.message,
                evidence_reference=reference.evidence_reference if reference else None,
            )
        )

    active_meters = [m for m in meters if m.active]
    received_meter_ids = {r.meter_id for r in readings if r.status != "rejected"}
    completeness = (len(received_meter_ids) / len(active_meters) * 100) if active_meters else 100.0
    considered = [r for r in readings if r.status != "rejected"]
    evidence_count = sum(1 for r in considered if r.evidence_reference)
    evidence_coverage = (evidence_count / len(considered) * 100) if considered else 0.0
    reconciled_count = sum(1 for r in reconciliations if r.status == "passed")
    open_exceptions = sum(1 for r in reconciliations if r.status != "passed") + sum(
        1 for r in considered if not r.evidence_reference
    )

    grid_readings = [
        r for r in considered if source_by_id.get(r.source_id) and source_by_id[r.source_id].source_type == "grid"
    ]
    grid_values = [n for r in grid_readings if (n := normalize_energy(r.value, r.unit)) is not None]
    result_tonnes, formula = location_scope2(grid_values)
    trace_inputs = [
        TraceInputOut(
            reading_id=r.id,
            meter_code=meter_by_id[r.meter_id].meter_code,
            source_name=source_by_id[r.source_id].name,
            value_kwh=float(normalize_energy(r.value, r.unit) or Decimal("0")),
            evidence_reference=r.evidence_reference,
            source_row=r.source_row,
        )
        for r in grid_readings
    ]

    meter_counts = {s.id: sum(1 for m in meters if m.source_id == s.id) for s in sources}
    latest_batch = (
        db.query(EnergyAssuranceImportBatch)
        .filter(EnergyAssuranceImportBatch.tenant_id == current.tenant_id, EnergyAssuranceImportBatch.site_id == active_site.id)
        .order_by(EnergyAssuranceImportBatch.created_at.desc())
        .first()
    )
    site_outs = [SiteOut(id=s.id, name=s.name, description=s.description, is_synthetic=s.is_synthetic) for s in sites]
    return WorkspaceOut(
        period=period,
        sites=site_outs,
        active_site=SiteOut(id=active_site.id, name=active_site.name, description=active_site.description, is_synthetic=active_site.is_synthetic),
        summary=AssuranceSummaryOut(
            completeness_pct=round(completeness, 1),
            evidence_coverage_pct=round(evidence_coverage, 1),
            readings_received=len(received_meter_ids),
            readings_expected=len(active_meters),
            sources_reconciled=reconciled_count,
            sources_total=len(sources),
            open_exceptions=open_exceptions,
            reporting_status="Ready" if open_exceptions == 0 and completeness == 100 else "Not ready",
        ),
        sources=[_source_out(s, meter_counts[s.id]) for s in sources],
        meters=[_meter_out(m, source_by_id[m.source_id].name) for m in meters],
        readings=[_reading_out(r, meter_by_id[r.meter_id], source_by_id[r.source_id]) for r in readings],
        reconciliations=reconciliations,
        trace=TraceOut(
            metric_name="Scope 2 (location-based) — demonstration",
            result_value=float(result_tonnes),
            unit="tCO2e",
            activity_value_kwh=float(sum(grid_values, Decimal("0"))),
            factor_value=float(GRID_FACTOR_KGCO2E_PER_KWH),
            factor_unit="kgCO2e/kWh",
            factor_source="Demonstration factor — replace during contractual discovery",
            formula=formula,
            inputs=trace_inputs,
        ),
        latest_import_at=latest_batch.created_at if latest_batch else None,
    )


@router.post("/sources", response_model=SourceOut, status_code=201)
def create_source(payload: SourceIn, current: CurrentUser = Depends(require_roles(*EDIT_ROLES)), db: Session = Depends(get_db)):
    _site(db, current.tenant_id, payload.site_id)
    if payload.source_type not in SOURCE_TYPES:
        raise HTTPException(status_code=422, detail="Unsupported source type")
    row = EnergyAssuranceSource(tenant_id=current.tenant_id, **payload.model_dump())
    db.add(row)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="A source with this name already exists") from exc
    db.refresh(row)
    return _source_out(row)


@router.patch("/sources/{source_id}", response_model=SourceOut)
def update_source(source_id: uuid.UUID, payload: SourceUpdate, current: CurrentUser = Depends(require_roles(*EDIT_ROLES)), db: Session = Depends(get_db)):
    row = _source(db, current.tenant_id, source_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    meter_count = db.query(EnergyAssuranceMeter).filter(EnergyAssuranceMeter.tenant_id == current.tenant_id, EnergyAssuranceMeter.source_id == row.id).count()
    return _source_out(row, meter_count)


@router.post("/meters", response_model=MeterOut, status_code=201)
def create_meter(payload: MeterIn, current: CurrentUser = Depends(require_roles(*EDIT_ROLES)), db: Session = Depends(get_db)):
    _site(db, current.tenant_id, payload.site_id)
    source = _source(db, current.tenant_id, payload.source_id)
    if source.site_id != payload.site_id:
        raise HTTPException(status_code=422, detail="Meter and source must belong to the same showcase site")
    if payload.direction not in DIRECTIONS:
        raise HTTPException(status_code=422, detail="Unsupported meter direction")
    row = EnergyAssuranceMeter(tenant_id=current.tenant_id, **payload.model_dump())
    db.add(row)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="This meter code already exists") from exc
    db.refresh(row)
    return _meter_out(row, source.name)


@router.patch("/meters/{meter_id}", response_model=MeterOut)
def update_meter(meter_id: uuid.UUID, payload: MeterUpdate, current: CurrentUser = Depends(require_roles(*EDIT_ROLES)), db: Session = Depends(get_db)):
    row = _meter(db, current.tenant_id, meter_id)
    changes = payload.model_dump(exclude_unset=True)
    if "source_id" in changes:
        source = _source(db, current.tenant_id, changes["source_id"])
        if source.site_id != row.site_id:
            raise HTTPException(status_code=422, detail="Meter and source must belong to the same showcase site")
    if changes.get("direction") and changes["direction"] not in DIRECTIONS:
        raise HTTPException(status_code=422, detail="Unsupported meter direction")
    for key, value in changes.items():
        setattr(row, key, value)
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    source = _source(db, current.tenant_id, row.source_id)
    return _meter_out(row, source.name)


@router.post("/readings", response_model=ReadingOut, status_code=201)
def create_reading(payload: ReadingIn, current: CurrentUser = Depends(require_roles(*EDIT_ROLES)), db: Session = Depends(get_db)):
    _site(db, current.tenant_id, payload.site_id)
    meter = _meter(db, current.tenant_id, payload.meter_id)
    if meter.site_id != payload.site_id:
        raise HTTPException(status_code=422, detail="Reading and meter must belong to the same showcase site")
    source = _source(db, current.tenant_id, meter.source_id)
    if normalize_energy(payload.value, payload.unit) is None:
        raise HTTPException(status_code=422, detail="Energy unit must be Wh, kWh, or MWh")
    if payload.status not in READING_STATUSES:
        raise HTTPException(status_code=422, detail="Unsupported reading status")
    flags = [] if payload.evidence_reference else ["evidence_missing"]
    row = EnergyAssuranceReading(
        tenant_id=current.tenant_id,
        site_id=payload.site_id,
        source_id=meter.source_id,
        meter_id=meter.id,
        period=payload.period,
        value=payload.value,
        unit=payload.unit,
        evidence_reference=payload.evidence_reference,
        status=payload.status,
        quality_flags=flags,
        created_by=current.id,
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="This meter already has a reading for the selected period") from exc
    db.refresh(row)
    return _reading_out(row, meter, source)


@router.patch("/readings/{reading_id}", response_model=ReadingOut)
def update_reading(reading_id: uuid.UUID, payload: ReadingUpdate, current: CurrentUser = Depends(require_roles(*EDIT_ROLES)), db: Session = Depends(get_db)):
    row = _reading(db, current.tenant_id, reading_id)
    changes = payload.model_dump(exclude_unset=True)
    next_value = changes.get("value", row.value)
    next_unit = changes.get("unit", row.unit)
    if normalize_energy(next_value, next_unit) is None:
        raise HTTPException(status_code=422, detail="Energy unit must be Wh, kWh, or MWh")
    if changes.get("status") and changes["status"] not in READING_STATUSES:
        raise HTTPException(status_code=422, detail="Unsupported reading status")
    for key, value in changes.items():
        setattr(row, key, value)
    row.quality_flags = [] if row.evidence_reference else ["evidence_missing"]
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    meter = _meter(db, current.tenant_id, row.meter_id)
    source = _source(db, current.tenant_id, row.source_id)
    return _reading_out(row, meter, source)


@router.post("/imports", response_model=ImportResponse)
def import_readings(payload: ImportRequest, current: CurrentUser = Depends(require_roles(*EDIT_ROLES)), db: Session = Depends(get_db)):
    _site(db, current.tenant_id, payload.site_id)
    meters = (
        db.query(EnergyAssuranceMeter)
        .filter(EnergyAssuranceMeter.tenant_id == current.tenant_id, EnergyAssuranceMeter.site_id == payload.site_id)
        .all()
    )
    meter_by_code = {m.meter_code.strip().lower(): m for m in meters}
    seen: set[tuple[uuid.UUID, date]] = set()
    validated: list[tuple[ImportRowResult, EnergyAssuranceMeter, Decimal]] = []
    results: list[ImportRowResult] = []

    for incoming in payload.rows:
        meter = meter_by_code.get(incoming.meter_code.strip().lower())
        if meter is None:
            results.append(ImportRowResult(row_index=incoming.row_index, status="error", meter_code=incoming.meter_code, message="Unknown meter code"))
            continue
        try:
            parsed_period = date.fromisoformat(incoming.period[:10]).replace(day=1)
        except ValueError:
            results.append(ImportRowResult(row_index=incoming.row_index, status="error", meter_code=incoming.meter_code, meter_name=meter.name, message="Period must be an ISO date such as 2026-08-01"))
            continue
        try:
            raw_value = Decimal(incoming.value.replace(",", "").strip())
        except (InvalidOperation, AttributeError):
            results.append(ImportRowResult(row_index=incoming.row_index, status="error", meter_code=incoming.meter_code, meter_name=meter.name, period=parsed_period, message="Value is not numeric"))
            continue
        normalized = normalize_energy(raw_value, incoming.unit)
        if normalized is None:
            results.append(ImportRowResult(row_index=incoming.row_index, status="error", meter_code=incoming.meter_code, meter_name=meter.name, period=parsed_period, message="Unit must be Wh, kWh, or MWh"))
            continue
        key = (meter.id, parsed_period)
        existing = db.query(EnergyAssuranceReading).filter(EnergyAssuranceReading.tenant_id == current.tenant_id, EnergyAssuranceReading.meter_id == meter.id, EnergyAssuranceReading.period == parsed_period).first()
        if key in seen or existing is not None:
            results.append(ImportRowResult(row_index=incoming.row_index, status="error", meter_code=incoming.meter_code, meter_name=meter.name, period=parsed_period, value=float(raw_value), normalized_kwh=float(normalized), message="Duplicate meter and period"))
            continue
        seen.add(key)
        result = ImportRowResult(row_index=incoming.row_index, status="valid", meter_code=incoming.meter_code, meter_name=meter.name, period=parsed_period, value=float(raw_value), normalized_kwh=float(normalized))
        results.append(result)
        validated.append((result, meter, raw_value))

    imported_count = 0
    if payload.commit and validated:
        batch = EnergyAssuranceImportBatch(tenant_id=current.tenant_id, site_id=payload.site_id, filename=payload.filename, row_count=len(validated), imported_by=current.id)
        db.add(batch)
        db.flush()
        incoming_by_row = {r.row_index: r for r in payload.rows}
        for result, meter, raw_value in validated:
            incoming = incoming_by_row[result.row_index]
            db.add(EnergyAssuranceReading(
                tenant_id=current.tenant_id,
                site_id=payload.site_id,
                source_id=meter.source_id,
                meter_id=meter.id,
                import_batch_id=batch.id,
                period=result.period,
                value=raw_value,
                unit=incoming.unit,
                evidence_reference=incoming.evidence_reference,
                source_row=incoming.row_index,
                status="review",
                quality_flags=[] if incoming.evidence_reference else ["evidence_missing"],
                created_by=current.id,
            ))
            result.status = "imported"
            imported_count += 1
        db.commit()

    return ImportResponse(rows=results, valid_count=sum(1 for r in results if r.status in {"valid", "imported"}), error_count=sum(1 for r in results if r.status == "error"), imported_count=imported_count)
