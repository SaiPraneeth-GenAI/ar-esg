import uuid
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, require_roles
from app.core.carbon_mapping import get_carbon_mapping
from app.db.models import Category, DataPoint, EmissionCalculation, EmissionTarget, Entry, Location, User
from app.db.session import get_db
from app.schemas.carbon import (
    CarbonOverview,
    CarbonOverviewSource,
    CarbonPreviewRequest,
    CarbonPreviewResponse,
    CarbonTrendPoint,
    EmissionCalculationOut,
    RecalculateResponse,
    TargetComparison,
)
from app.services.carbon_calculation import (
    CalculationOutcome,
    calculate_entries_batch,
    compute_period_totals,
    compute_period_totals_batch,
    compute_range_totals,
    months_in_range,
    prior_month,
    prior_range_for_mode,
    prior_year,
    prior_year_range_for_mode,
    range_bounds_for_mode,
    run_calculation,
    to_decimal,
)
from app.services.rollups import month_start
from app.services.target_calculation import INTENSITY_METRIC_TYPES, classify_status, months_between, target_value_for_month

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


@router.get("/calculations", response_model=list[EmissionCalculationOut])
def list_calculations(
    period: date,
    scope: int | None = None,
    calculation_method: str | None = None,
    data_point_name: str | None = None,
    location_id: uuid.UUID | None = None,
    current: CurrentUser = Depends(require_roles("Admin", "Manager", "Approver")),
    db: Session = Depends(get_db),
):
    """Drill-down evidence for one card/source: every current calculation
    row (calculated or unresolved) contributing to it, each carrying its
    own factor snapshot and a link back to the entry for full audit
    history."""
    period = month_start(period)
    q = db.query(EmissionCalculation).filter(
        EmissionCalculation.tenant_id == current.tenant_id,
        EmissionCalculation.reporting_period == period,
        EmissionCalculation.status.in_(["calculated", "unresolved"]),
    )
    if scope is not None:
        q = q.filter(EmissionCalculation.scope == scope)
    if calculation_method is not None:
        q = q.filter(EmissionCalculation.calculation_method == calculation_method)
    if location_id is not None:
        q = q.filter(EmissionCalculation.location_id == location_id)
    rows = q.all()

    if data_point_name is not None:
        dp_ids = {dp.id for dp in db.query(DataPoint).filter(DataPoint.name == data_point_name).all()}
        rows = [r for r in rows if r.data_point_id in dp_ids]

    rows.sort(key=lambda r: r.calculated_at, reverse=True)
    return [_calc_out(db, r) for r in rows]


def _trailing_months(period: date, count: int) -> list[date]:
    months = []
    cursor = period
    for _ in range(count):
        months.append(cursor)
        year = cursor.year - (1 if cursor.month == 1 else 0)
        month = 12 if cursor.month == 1 else cursor.month - 1
        cursor = cursor.replace(year=year, month=month)
    return list(reversed(months))


@router.get("/trend", response_model=list[CarbonTrendPoint])
def carbon_trend(
    period: date,
    months: int = 6,
    location_id: uuid.UUID | None = None,
    current: CurrentUser = Depends(require_roles("Admin", "Manager", "Approver")),
    db: Session = Depends(get_db),
):
    """Scope 1+2 (location-based) and intensity for the trailing N months in
    one batched query set -- powers the dashboard trend chart without one
    full /carbon/overview round trip per bar."""
    period = month_start(period)
    trailing = _trailing_months(period, min(max(months, 1), 24))
    totals_by_period = compute_period_totals_batch(db, current.tenant_id, location_id, trailing)
    return [
        CarbonTrendPoint(
            period=p,
            scope1_tco2e=totals_by_period[p]["scope1_tco2e"],
            scope2_location_based_tco2e=totals_by_period[p]["scope2_loc_tco2e"],
            scope1_2_location_based_tco2e=totals_by_period[p]["scope1_2_loc_tco2e"],
            scope3_tco2e=None,
            intensity_tco2e_per_mnah=totals_by_period[p]["intensity"],
        )
        for p in trailing
    ]


@router.get("/overview", response_model=CarbonOverview)
def carbon_overview(
    period: date,
    location_id: uuid.UUID | None = None,
    period_mode: str = "month",
    current: CurrentUser = Depends(require_roles("Admin", "Manager", "Approver")),
    db: Session = Depends(get_db),
):
    """Approved calculation snapshots only -- never a live sum of raw
    entries (rule #10). period_mode selects how far back "current" reaches
    before period: 'month' (default, unchanged), 'quarter' (quarter-to-
    date), or 'ytd' (year-to-date). Absolutes sum across the range;
    intensity is recomputed from those summed totals, never averaged."""
    period = month_start(period)
    range_start, range_end = range_bounds_for_mode(period, period_mode)
    current_months = months_in_range(range_start, range_end)
    prior_start, prior_end = prior_range_for_mode(range_start, range_end, period_mode)
    prior_months = months_in_range(prior_start, prior_end)
    prior_year_start, prior_year_end = prior_year_range_for_mode(range_start, range_end)
    prior_year_months = months_in_range(prior_year_start, prior_year_end)

    current_totals = compute_range_totals(db, current.tenant_id, location_id, current_months)
    prior_totals = compute_range_totals(db, current.tenant_id, location_id, prior_months)
    prior_year_totals = compute_range_totals(db, current.tenant_id, location_id, prior_year_months)
    rows = current_totals["rows"]
    unresolved_count = current_totals["unresolved_count"]
    calculated_count = current_totals["calculated_count"]
    completeness_pct = current_totals["completeness_pct"]

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

    insight = _build_insight(sources, current_totals["scope1_2_loc_tco2e"], prior_totals["scope1_2_loc_tco2e"], unresolved_count)

    scope1_2_target = _active_target_comparison(
        db, current.tenant_id, location_id, "1_2_combined", "absolute_tco2e", current_months, current_totals["scope1_2_loc_tco2e"]
    )
    intensity_target = _active_target_comparison(
        db, current.tenant_id, location_id, "1_2_combined", "intensity_tco2e_per_mnah", current_months, current_totals["intensity"]
    )

    return CarbonOverview(
        period=period,
        period_mode=period_mode,
        period_start=range_start,
        period_end=range_end,
        scope1_tco2e=current_totals["scope1_tco2e"],
        scope2_location_based_tco2e=current_totals["scope2_loc_tco2e"],
        scope2_market_based_tco2e=current_totals["scope2_mkt_tco2e"],
        scope1_2_location_based_tco2e=current_totals["scope1_2_loc_tco2e"],
        prior_scope1_2_location_based_tco2e=prior_totals["scope1_2_loc_tco2e"],
        prior_intensity_tco2e_per_mnah=prior_totals["intensity"],
        prior_year_scope1_2_location_based_tco2e=prior_year_totals["scope1_2_loc_tco2e"],
        prior_year_intensity_tco2e_per_mnah=prior_year_totals["intensity"],
        production_value=current_totals["production_value"],
        production_unit=current_totals["production_unit"],
        intensity_tco2e_per_mnah=current_totals["intensity"],
        unresolved_count=unresolved_count,
        calculated_count=calculated_count,
        completeness_pct=completeness_pct,
        sources=sources,
        insight=insight,
        scope1_2_target=scope1_2_target,
        intensity_target=intensity_target,
    )


def _active_target_comparison(
    db: Session, tenant_id, location_id, scope: str, metric_type: str, months: list[date], actual: float | None
) -> TargetComparison | None:
    """Only ever reads an active target for the exact same boundary this
    card already shows -- never substitutes a different location/scope
    target, and never fabricates a comparison when none has been
    declared (rule: targets are never auto-created). `months` is the same
    range the actual figure was aggregated over (one month, or a
    quarter-to-date/year-to-date range): an absolute target's budget is
    summed across exactly those months so it's comparable to a multi-month
    actual; an intensity target's value is a rate and stays constant
    regardless of range length."""
    anchor_period = months[-1]
    target = (
        db.query(EmissionTarget)
        .filter(
            EmissionTarget.tenant_id == tenant_id,
            EmissionTarget.location_id == location_id,
            EmissionTarget.scope == scope,
            EmissionTarget.metric_type == metric_type,
            EmissionTarget.status == "active",
            EmissionTarget.target_period_start <= anchor_period,
            EmissionTarget.target_period_end >= anchor_period,
        )
        .first()
    )
    if target is None or target.target_value is None:
        return None
    num_months = len(months_between(target.target_period_start, target.target_period_end))
    if metric_type in INTENSITY_METRIC_TYPES:
        range_target = target_value_for_month(
            target.monthly_phasing, anchor_period, float(target.target_value), num_months, target.metric_type
        )
    else:
        relevant = [m for m in months if target.target_period_start <= m <= target.target_period_end]
        monthly_targets = [
            target_value_for_month(target.monthly_phasing, m, float(target.target_value), num_months, target.metric_type)
            for m in relevant
        ]
        monthly_targets = [t for t in monthly_targets if t is not None]
        range_target = sum(monthly_targets) if monthly_targets else None
    if range_target is None:
        return None
    return TargetComparison(target_id=target.id, target_value=range_target, status=classify_status(actual, range_target))


def _build_insight(sources: list[CarbonOverviewSource], current_total: float | None, prior_total: float | None, unresolved_count: int) -> str | None:
    """Short, deterministic observation from the actual numbers -- largest
    source and period-over-period variance. No causal claims (rule in
    Prompt 4's dashboard section)."""
    parts = []
    if sources:
        largest = max(sources, key=lambda s: s.emissions_tco2e)
        if current_total and current_total > 0:
            share = largest.emissions_tco2e / current_total * 100
            parts.append(f"{largest.data_point_name} is the largest source this period, at {share:.0f}% of Scope 1+2 location-based emissions.")
    if prior_total is not None and prior_total > 0 and current_total is not None:
        delta_pct = (current_total - prior_total) / prior_total * 100
        direction = "up" if delta_pct > 0 else "down"
        parts.append(f"Total Scope 1+2 emissions are {direction} {abs(delta_pct):.0f}% versus the prior month.")
    if unresolved_count > 0:
        parts.append(f"{unresolved_count} entr{'y is' if unresolved_count == 1 else 'ies are'} not yet reflected -- see the unresolved queue.")
    return " ".join(parts) if parts else None
