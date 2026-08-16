import uuid
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, require_roles
from app.core.carbon_mapping import get_carbon_mapping
from app.db.models import Category, DataPoint, EmissionCalculation, Entry, Location, User
from app.db.session import get_db
from app.schemas.carbon import (
    CarbonOverview,
    CarbonOverviewSource,
    CarbonPreviewRequest,
    CarbonPreviewResponse,
    EmissionCalculationOut,
    RecalculateResponse,
)
from app.services.carbon_calculation import CalculationOutcome, calculate_entries_batch, run_calculation, to_decimal
from app.services.rollups import month_start

router = APIRouter(prefix="/carbon", tags=["carbon"])


def _get_tenant_data_point(db: Session, tenant_id, data_point_id: uuid.UUID) -> DataPoint:
    dp = (
        db.query(DataPoint)
        .join(Category, Category.id == DataPoint.category_id)
        .filter(DataPoint.id == data_point_id, Category.tenant_id == tenant_id)
        .first()
    )
    if dp is None:
        raise HTTPException(status_code=404, detail="Data point not found")
    return dp


@router.post("/preview", response_model=CarbonPreviewResponse)
def preview_calculation(
    payload: CarbonPreviewRequest,
    current: CurrentUser = Depends(require_roles("Admin", "Manager", "Approver")),
    db: Session = Depends(get_db),
):
    """Read-only evidence for a draft entry -- never persists a footprint,
    never lets the caller override the resolved factor. Shows exactly what
    an approval would calculate, before it happens."""
    dp = _get_tenant_data_point(db, current.tenant_id, payload.data_point_id)
    mapping = get_carbon_mapping(dp.name)
    activity_unit = payload.unit or dp.unit or ""

    if mapping is None:
        return CarbonPreviewResponse(
            data_point_name=dp.name,
            scope=None,
            status="not_a_ghg_source",
            activity_value=payload.value,
            activity_unit=activity_unit,
            normalized_activity_value=None,
            normalized_activity_unit=None,
            factor_version=None,
            factor_value=None,
            factor_unit=None,
            factor_source=None,
            calculation_method=None,
            formula=None,
            emissions_kgco2e=None,
            emissions_tco2e=None,
            resolution_reason=None,
            warning="This data point isn't mapped to a GHG calculation in this release.",
        )

    outcome = run_calculation(db, current.tenant_id, mapping, to_decimal(payload.value), activity_unit, payload.period)
    return _preview_from_outcome(dp.name, payload.value, activity_unit, outcome)


def _preview_from_outcome(data_point_name: str, activity_value: float, activity_unit: str, outcome: CalculationOutcome) -> CarbonPreviewResponse:
    emissions_kg = float(outcome.emissions_kgco2e) if outcome.emissions_kgco2e is not None else None
    return CarbonPreviewResponse(
        data_point_name=data_point_name,
        scope=outcome.scope,
        status=outcome.status,
        activity_value=activity_value,
        activity_unit=activity_unit,
        normalized_activity_value=float(outcome.normalized_activity_value) if outcome.normalized_activity_value is not None else None,
        normalized_activity_unit=outcome.normalized_activity_unit,
        factor_version=outcome.resolved.version if outcome.resolved else None,
        factor_value=float(outcome.resolved.value) if outcome.resolved else None,
        factor_unit=outcome.resolved.unit if outcome.resolved else None,
        factor_source=outcome.resolved.source if outcome.resolved else None,
        calculation_method=outcome.calculation_method,
        formula=outcome.formula,
        emissions_kgco2e=emissions_kg,
        emissions_tco2e=(emissions_kg / 1000) if emissions_kg is not None else None,
        resolution_reason=outcome.resolution_reason,
    )


def _calc_out(db: Session, calc: EmissionCalculation) -> EmissionCalculationOut:
    dp = db.get(DataPoint, calc.data_point_id)
    loc = db.get(Location, calc.location_id)
    calculated_by_email = None
    if calc.calculated_by:
        user = db.get(User, calc.calculated_by)
        calculated_by_email = user.email if user else None
    emissions_kg = float(calc.emissions_kgco2e) if calc.emissions_kgco2e is not None else None
    return EmissionCalculationOut(
        id=calc.id,
        entry_id=calc.entry_id,
        data_point_id=calc.data_point_id,
        data_point_name=dp.name if dp else "",
        location_id=calc.location_id,
        location_name=loc.name if loc else "",
        reporting_period=calc.reporting_period,
        scope=calc.scope,
        calculation_method=calc.calculation_method,
        status=calc.status,
        activity_value=float(calc.activity_value),
        activity_unit=calc.activity_unit,
        normalized_activity_value=float(calc.normalized_activity_value) if calc.normalized_activity_value is not None else None,
        normalized_activity_unit=calc.normalized_activity_unit,
        factor_version=calc.factor_version,
        factor_value=float(calc.factor_value) if calc.factor_value is not None else None,
        factor_unit=calc.factor_unit,
        factor_source=calc.factor_source,
        factor_effective_year=calc.factor_effective_year,
        emissions_kgco2e=emissions_kg,
        emissions_tco2e=(emissions_kg / 1000) if emissions_kg is not None else None,
        formula=calc.formula,
        resolution_reason=calc.resolution_reason,
        calculated_at=calc.calculated_at,
        calculated_by_email=calculated_by_email,
        supersedes_calculation_id=calc.supersedes_calculation_id,
    )


@router.post("/entries/{entry_id}/calculate", response_model=EmissionCalculationOut | None)
def calculate_one_entry(
    entry_id: uuid.UUID,
    current: CurrentUser = Depends(require_roles("Admin", "Approver")),
    db: Session = Depends(get_db),
):
    entry = db.get(Entry, entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Entry not found")
    dp = db.get(DataPoint, entry.data_point_id)
    category = db.get(Category, dp.category_id)
    if category.tenant_id != current.tenant_id:
        raise HTTPException(status_code=404, detail="Entry not found")

    results = calculate_entries_batch(db, [entry], current.tenant_id, current.id)
    db.commit()
    _, calc = results[0]
    if calc is None:
        return None
    db.refresh(calc)
    return _calc_out(db, calc)


@router.post("/recalculate-period", response_model=RecalculateResponse)
def recalculate_period(
    period: date,
    location_id: uuid.UUID | None = None,
    current: CurrentUser = Depends(require_roles("Admin", "Approver")),
    db: Session = Depends(get_db),
):
    """Explicit, authorised rebuild for every approved entry in a period --
    e.g. after a factor publication. Bounded to one transaction: every row
    is added to the session and committed once, not per entry."""
    period = month_start(period)
    q = (
        db.query(Entry)
        .join(DataPoint, DataPoint.id == Entry.data_point_id)
        .join(Category, Category.id == DataPoint.category_id)
        .filter(Category.tenant_id == current.tenant_id, Entry.status == "Approved", Entry.period == period)
    )
    if location_id is not None:
        q = q.filter(Entry.location_id == location_id)
    entries = q.all()

    results = calculate_entries_batch(db, entries, current.tenant_id, current.id)
    db.commit()

    calculated = [c for _, c in results if c is not None and c.status == "calculated"]
    unresolved = [c for _, c in results if c is not None and c.status == "unresolved"]
    skipped = len(results) - len(calculated) - len(unresolved)

    for c in calculated + unresolved:
        db.refresh(c)

    return RecalculateResponse(
        calculated_count=len(calculated),
        unresolved_count=len(unresolved),
        skipped_not_ghg_count=skipped,
        results=[_calc_out(db, c) for c in (calculated + unresolved)],
    )


@router.get("/unresolved", response_model=list[EmissionCalculationOut])
def unresolved_queue(
    location_id: uuid.UUID | None = None,
    current: CurrentUser = Depends(require_roles("Admin", "Approver")),
    db: Session = Depends(get_db),
):
    q = db.query(EmissionCalculation).filter(
        EmissionCalculation.tenant_id == current.tenant_id, EmissionCalculation.status == "unresolved"
    )
    if location_id is not None:
        q = q.filter(EmissionCalculation.location_id == location_id)
    rows = q.order_by(EmissionCalculation.reporting_period.desc(), EmissionCalculation.calculated_at.desc()).all()
    return [_calc_out(db, r) for r in rows]


@router.get("/overview", response_model=CarbonOverview)
def carbon_overview(
    period: date,
    location_id: uuid.UUID | None = None,
    current: CurrentUser = Depends(require_roles("Admin", "Manager", "Approver")),
    db: Session = Depends(get_db),
):
    """Approved calculation snapshots only -- never a live sum of raw
    entries (rule #10)."""
    period = month_start(period)
    q = db.query(EmissionCalculation).filter(
        EmissionCalculation.tenant_id == current.tenant_id,
        EmissionCalculation.reporting_period == period,
        EmissionCalculation.status == "calculated",
    )
    if location_id is not None:
        q = q.filter(EmissionCalculation.location_id == location_id)
    rows = q.all()

    scope1 = sum((r.emissions_kgco2e for r in rows if r.scope == 1), Decimal("0"))
    scope2_loc = sum(
        (r.emissions_kgco2e for r in rows if r.scope == 2 and r.calculation_method == "location_based"), Decimal("0")
    )
    scope2_mkt = sum(
        (r.emissions_kgco2e for r in rows if r.scope == 2 and r.calculation_method == "market_based"), Decimal("0")
    )
    has_scope2_mkt = any(r.scope == 2 and r.calculation_method == "market_based" for r in rows)

    scope1_2_loc = scope1 + scope2_loc

    unresolved_q = db.query(EmissionCalculation).filter(
        EmissionCalculation.tenant_id == current.tenant_id,
        EmissionCalculation.reporting_period == period,
        EmissionCalculation.status == "unresolved",
    )
    if location_id is not None:
        unresolved_q = unresolved_q.filter(EmissionCalculation.location_id == location_id)
    unresolved_count = unresolved_q.count()

    by_source: dict[tuple[str, int, str | None], list] = {}
    dp_names: dict[uuid.UUID, str] = {}
    for r in rows:
        if r.data_point_id not in dp_names:
            dp = db.get(DataPoint, r.data_point_id)
            dp_names[r.data_point_id] = dp.name if dp else ""
        key = (dp_names[r.data_point_id], r.scope, r.calculation_method)
        by_source.setdefault(key, []).append(r)

    sources = [
        CarbonOverviewSource(
            data_point_name=name,
            scope=scope,
            calculation_method=method,
            emissions_tco2e=float(sum((r.emissions_kgco2e for r in group), Decimal("0")) / 1000),
            entry_count=len(group),
        )
        for (name, scope, method), group in sorted(by_source.items())
    ]

    production_value = None
    production_unit = None
    intensity = None
    from app.db.models import ProductionVolumeMapping

    prod_mapping_q = db.query(ProductionVolumeMapping).filter(
        ProductionVolumeMapping.tenant_id == current.tenant_id, ProductionVolumeMapping.is_active.is_(True)
    )
    if location_id is not None:
        prod_mapping_q = prod_mapping_q.filter(
            (ProductionVolumeMapping.location_id == location_id) | (ProductionVolumeMapping.location_id.is_(None))
        )
    prod_mapping = prod_mapping_q.first()

    if prod_mapping is not None:
        entry_q = db.query(Entry).filter(
            Entry.data_point_id == prod_mapping.data_point_id,
            Entry.status == "Approved",
            Entry.period == period,
        )
        if location_id is not None:
            entry_q = entry_q.filter(Entry.location_id == location_id)
        production_entries = entry_q.all()
        if production_entries:
            total_native = sum((to_decimal(e.value) for e in production_entries if e.value is not None), Decimal("0"))
            production_value = float(total_native * to_decimal(prod_mapping.conversion_multiplier))
            production_unit = prod_mapping.canonical_unit
            if production_value and production_value > 0:
                intensity = float(scope1_2_loc / 1000) / production_value

    return CarbonOverview(
        period=period,
        scope1_tco2e=float(scope1 / 1000),
        scope2_location_based_tco2e=float(scope2_loc / 1000),
        scope2_market_based_tco2e=(float(scope2_mkt / 1000) if has_scope2_mkt else None),
        scope1_2_location_based_tco2e=float(scope1_2_loc / 1000),
        production_value=production_value,
        production_unit=production_unit,
        intensity_tco2e_per_mnah=intensity,
        unresolved_count=unresolved_count,
        sources=sources,
    )
