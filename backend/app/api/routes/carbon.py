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
    AiInsightOut,
    CarbonOverview,
    CarbonOverviewSource,
    CarbonPreviewRequest,
    CarbonPreviewResponse,
    CarbonTrendPoint,
    EmissionCalculationOut,
    RecalculateResponse,
    TargetComparison,
    TargetStatusOut,
)
from app.services.carbon_calculation import (
    CalculationOutcome,
    calculate_entries_batch,
    compute_period_totals,
    compute_period_totals_batch,
    compute_range_totals,
    months_in_range,
    prior_range_for_mode,
    prior_year_range_for_mode,
    range_bounds_for_mode,
    run_calculation,
    to_decimal,
    trailing_buckets_for_mode,
)
from app.services.dashboard_insight import generate_dashboard_insight
from app.services.rollups import month_start
from app.services.target_calculation import (
    RATE_METRIC_KEYS,
    all_target_comparisons,
    classify_status,
    months_between,
    target_value_for_month,
)

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


def _calc_out(
    db: Session,
    calc: EmissionCalculation,
    dp_names: dict[uuid.UUID, str] | None = None,
    loc_names: dict[uuid.UUID, str] | None = None,
    user_emails: dict[uuid.UUID, str] | None = None,
) -> EmissionCalculationOut:
    """Pass pre-fetched dp_names/loc_names/user_emails (see _calc_out_batch)
    when rendering a list -- without them, this falls back to one db.get()
    per lookup, correct but N+1 across a list of many calculations."""
    if dp_names is not None:
        dp_name = dp_names.get(calc.data_point_id, "")
    else:
        dp = db.get(DataPoint, calc.data_point_id)
        dp_name = dp.name if dp else ""
    if loc_names is not None:
        loc_name = loc_names.get(calc.location_id, "")
    else:
        loc = db.get(Location, calc.location_id)
        loc_name = loc.name if loc else ""
    if user_emails is not None:
        calculated_by_email = user_emails.get(calc.calculated_by) if calc.calculated_by else None
    else:
        calculated_by_email = None
        if calc.calculated_by:
            user = db.get(User, calc.calculated_by)
            calculated_by_email = user.email if user else None
    emissions_kg = float(calc.emissions_kgco2e) if calc.emissions_kgco2e is not None else None
    return EmissionCalculationOut(
        id=calc.id,
        entry_id=calc.entry_id,
        data_point_id=calc.data_point_id,
        data_point_name=dp_name,
        location_id=calc.location_id,
        location_name=loc_name,
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


def _calc_out_batch(db: Session, calcs: list[EmissionCalculation]) -> list[EmissionCalculationOut]:
    """3 queries for the whole list instead of up to 3 per row -- the
    dp/location/user id sets are usually far smaller than the row count
    (many calculations share the same data point/location)."""
    if not calcs:
        return []
    dp_ids = {c.data_point_id for c in calcs}
    loc_ids = {c.location_id for c in calcs}
    user_ids = {c.calculated_by for c in calcs if c.calculated_by}
    dp_names = {dp.id: dp.name for dp in db.query(DataPoint).filter(DataPoint.id.in_(dp_ids)).all()}
    loc_names = {loc.id: loc.name for loc in db.query(Location).filter(Location.id.in_(loc_ids)).all()}
    user_emails = {u.id: u.email for u in db.query(User).filter(User.id.in_(user_ids)).all()} if user_ids else {}
    return [_calc_out(db, c, dp_names, loc_names, user_emails) for c in calcs]


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
        results=_calc_out_batch(db, calculated + unresolved),
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
    return _calc_out_batch(db, rows)


@router.get("/calculations", response_model=list[EmissionCalculationOut])
def list_calculations(
    period: date,
    period_mode: str = "month",
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
    history. period_mode widens the window to a quarter-to-date/
    year-to-date range the same way the overview cards do; default 'month'
    keeps the original single-period behavior every existing caller relies
    on."""
    period = month_start(period)
    range_start, range_end = range_bounds_for_mode(period, period_mode)
    periods = months_in_range(range_start, range_end)
    q = db.query(EmissionCalculation).filter(
        EmissionCalculation.tenant_id == current.tenant_id,
        EmissionCalculation.reporting_period.in_(periods),
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
    return _calc_out_batch(db, rows)


@router.get("/trend", response_model=list[CarbonTrendPoint])
def carbon_trend(
    period: date,
    months: int = 6,
    location_id: uuid.UUID | None = None,
    period_mode: str = "month",
    current: CurrentUser = Depends(require_roles("Admin", "Manager", "Approver")),
    db: Session = Depends(get_db),
):
    """Scope 1+2 (location-based) and intensity for the trailing N buckets,
    each paired with the same bucket one year earlier for a year-over-year
    comparison -- all in one batched query set (one query covering every
    month every bucket and its year-ago counterpart touches), not one
    round trip per bucket. period_mode picks the bucket granularity:
    'month' (default), 'quarter', or 'ytd' (year buckets)."""
    period = month_start(period)
    count = min(max(months, 1), 24) if period_mode == "month" else min(max(months, 1), 8)
    buckets = trailing_buckets_for_mode(period, period_mode, count)

    all_months: set[date] = set()
    prior_year_buckets: list[tuple[date, date]] = []
    for start, end in buckets:
        all_months.update(months_in_range(start, end))
        py_start, py_end = prior_year_range_for_mode(start, end)
        prior_year_buckets.append((py_start, py_end))
        all_months.update(months_in_range(py_start, py_end))

    by_month = compute_period_totals_batch(db, current.tenant_id, location_id, sorted(all_months))
    targets_by_metric = _active_targets_by_metric(db, current.tenant_id, location_id, _TREND_TARGET_METRICS)

    points = []
    for (start, end), (py_start, py_end) in zip(buckets, prior_year_buckets):
        bucket_months = months_in_range(start, end)
        totals = compute_range_totals(db, current.tenant_id, location_id, bucket_months, by_month=by_month)
        py_totals = compute_range_totals(
            db, current.tenant_id, location_id, months_in_range(py_start, py_end), by_month=by_month
        )
        points.append(
            CarbonTrendPoint(
                period=end,
                bucket_start=start,
                bucket_end=end,
                scope1_tco2e=totals["scope1_tco2e"],
                scope2_location_based_tco2e=totals["scope2_loc_tco2e"],
                scope1_2_location_based_tco2e=totals["scope1_2_loc_tco2e"],
                scope3_tco2e=None,
                intensity_tco2e_per_mnah=totals["intensity"],
                prior_year_scope1_tco2e=py_totals["scope1_tco2e"],
                prior_year_scope2_location_based_tco2e=py_totals["scope2_loc_tco2e"],
                prior_year_scope1_2_location_based_tco2e=py_totals["scope1_2_loc_tco2e"],
                prior_year_intensity_tco2e_per_mnah=py_totals["intensity"],
                target_scope1_tco2e=_target_value_for_bucket(targets_by_metric.get("scope1_tco2e"), "scope1_tco2e", bucket_months),
                target_scope2_location_based_tco2e=_target_value_for_bucket(targets_by_metric.get("scope2_tco2e"), "scope2_tco2e", bucket_months),
                target_scope1_2_location_based_tco2e=_target_value_for_bucket(
                    targets_by_metric.get("scope1_2_tco2e"), "scope1_2_tco2e", bucket_months
                ),
                target_intensity_tco2e_per_mnah=_target_value_for_bucket(
                    targets_by_metric.get("ghg_intensity_production"), "ghg_intensity_production", bucket_months
                ),
            )
        )
    return points


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
        db, current.tenant_id, location_id, "scope1_2_tco2e", current_months, current_totals["scope1_2_loc_tco2e"]
    )
    intensity_target = _active_target_comparison(
        db, current.tenant_id, location_id, "ghg_intensity_production", current_months, current_totals["intensity"]
    )
    scope1_target = _active_target_comparison(
        db, current.tenant_id, location_id, "scope1_tco2e", current_months, current_totals["scope1_tco2e"]
    )
    scope2_target = _active_target_comparison(
        db, current.tenant_id, location_id, "scope2_tco2e", current_months, current_totals["scope2_loc_tco2e"]
    )
    all_targets = [
        TargetStatusOut(
            target_id=t.target_id, metric_key=t.metric_key, label=t.label, unit=t.unit,
            actual=t.actual, target_value=t.target_value, status=t.status,
        )
        for t in all_target_comparisons(db, current.tenant_id, location_id, current_months)
    ]

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
        scope1_target=scope1_target,
        scope2_target=scope2_target,
        all_targets=all_targets,
    )


@router.get("/ai-insight", response_model=AiInsightOut)
def carbon_ai_insight(
    period: date,
    location_id: uuid.UUID | None = None,
    period_mode: str = "month",
    current: CurrentUser = Depends(require_roles("Admin", "Manager", "Approver")),
    db: Session = Depends(get_db),
):
    """A guardrailed AI summary of the same figures the overview cards show
    -- kept off the /overview response on purpose so a slow or unavailable
    OpenAI call never blocks the dashboard's main load; the frontend fetches
    this separately and reveals it once ready. Always falls back to the
    existing deterministic sentence on any AI failure (see
    services/dashboard_insight.py)."""
    period = month_start(period)
    range_start, range_end = range_bounds_for_mode(period, period_mode)
    current_months = months_in_range(range_start, range_end)
    prior_start, prior_end = prior_range_for_mode(range_start, range_end, period_mode)
    prior_months = months_in_range(prior_start, prior_end)

    current_totals = compute_range_totals(db, current.tenant_id, location_id, current_months)
    prior_totals = compute_range_totals(db, current.tenant_id, location_id, prior_months)
    rows = current_totals["rows"]

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
            data_point_name=name, scope=scope, calculation_method=method,
            emissions_tco2e=float(sum((r.emissions_kgco2e for r in group), Decimal("0")) / 1000),
            entry_count=len(group),
        )
        for (name, scope, method), group in sorted(by_source.items())
    ]

    fallback = _build_insight(sources, current_totals["scope1_2_loc_tco2e"], prior_totals["scope1_2_loc_tco2e"], current_totals["unresolved_count"])

    targets = all_target_comparisons(db, current.tenant_id, location_id, current_months)
    context = {
        "period_label": period.isoformat(),
        "period_mode": period_mode,
        "scope1_tco2e": current_totals["scope1_tco2e"],
        "scope2_location_based_tco2e": current_totals["scope2_loc_tco2e"],
        "scope1_2_location_based_tco2e": current_totals["scope1_2_loc_tco2e"],
        "prior_scope1_2_location_based_tco2e": prior_totals["scope1_2_loc_tco2e"],
        "ghg_intensity_tco2e_per_mnah": current_totals["intensity"],
        "prior_ghg_intensity_tco2e_per_mnah": prior_totals["intensity"],
        "unresolved_count": current_totals["unresolved_count"],
        "completeness_pct": current_totals["completeness_pct"],
        "top_contributors": [
            {"name": s.data_point_name, "scope": s.scope, "emissions_tco2e": round(s.emissions_tco2e, 2)}
            for s in sorted(sources, key=lambda s: s.emissions_tco2e, reverse=True)[:5]
        ],
        "targets": [
            {
                "metric": t.label,
                "unit": t.unit,
                "actual": round(t.actual, 3) if t.actual is not None else None,
                "target_value": round(t.target_value, 3),
                "status": t.status,
            }
            for t in targets
        ],
    }

    insight = generate_dashboard_insight(context, fallback)
    return AiInsightOut(insight=insight)


def _target_value_for_bucket(target: EmissionTarget | None, metric_key: str, months: list[date]) -> float | None:
    """The metric's target figure for exactly this bucket -- None (not
    substituted with anything) when the target doesn't apply here, either
    because there is no active target for this metric/location or because
    this bucket falls outside the target's own period (e.g. a 2027 target
    contributes nothing to a 2026 bucket). `months` is the same range the
    actual figure was aggregated over: a budget metric's total is summed
    across exactly those months so it's comparable to a multi-month
    actual; a rate metric's value stays constant regardless of range
    length."""
    if target is None or target.target_value is None:
        return None
    anchor_period = months[-1]
    if not (target.target_period_start <= anchor_period <= target.target_period_end):
        return None
    num_months = len(months_between(target.target_period_start, target.target_period_end))
    if metric_key in RATE_METRIC_KEYS:
        return target_value_for_month(target.monthly_phasing, anchor_period, float(target.target_value), num_months, metric_key)
    relevant = [m for m in months if target.target_period_start <= m <= target.target_period_end]
    monthly_targets = [
        target_value_for_month(target.monthly_phasing, m, float(target.target_value), num_months, metric_key)
        for m in relevant
    ]
    monthly_targets = [t for t in monthly_targets if t is not None]
    return sum(monthly_targets) if monthly_targets else None


def _active_target_comparison(
    db: Session, tenant_id, location_id, metric_key: str, months: list[date], actual: float | None
) -> TargetComparison | None:
    """Only ever reads an active target for the exact same boundary this
    card already shows -- never substitutes a different location/metric
    target, and never fabricates a comparison when none has been
    declared (rule: targets are never auto-created). Returns None only
    when there's truly no active target for this metric/location -- a
    target that exists but whose period doesn't cover this month (not
    started yet, or already ended) still returns a comparison, carrying
    that status instead of a fabricated actual-vs-target number, so the
    card can say "Not started yet" instead of the misleading "No target
    set" (a real target was declared -- it's just not in force yet)."""
    target = (
        db.query(EmissionTarget)
        .filter(
            EmissionTarget.tenant_id == tenant_id,
            EmissionTarget.location_id == location_id,
            EmissionTarget.metric_key == metric_key,
            EmissionTarget.status == "active",
        )
        .first()
    )
    if target is None:
        return None
    anchor_period = months[-1]
    if anchor_period < target.target_period_start:
        return TargetComparison(
            target_id=target.id,
            target_value=float(target.target_value) if target.target_value is not None else None,
            status="Not started yet",
        )
    if anchor_period > target.target_period_end:
        return TargetComparison(
            target_id=target.id,
            target_value=float(target.target_value) if target.target_value is not None else None,
            status="Target period ended",
        )
    range_target = _target_value_for_bucket(target, metric_key, months)
    if range_target is None:
        return None
    return TargetComparison(target_id=target.id, target_value=range_target, status=classify_status(actual, range_target))


_TREND_TARGET_METRICS = ["scope1_tco2e", "scope2_tco2e", "scope1_2_tco2e", "ghg_intensity_production"]


def _active_targets_by_metric(db: Session, tenant_id, location_id, metric_keys: list[str]) -> dict[str, EmissionTarget]:
    """One query for every active target this trend chart could need a
    reference line for -- targets are few (at most one per metric per
    location), so this is never worth batching per-bucket."""
    targets = (
        db.query(EmissionTarget)
        .filter(
            EmissionTarget.tenant_id == tenant_id,
            EmissionTarget.location_id == location_id,
            EmissionTarget.metric_key.in_(metric_keys),
            EmissionTarget.status == "active",
        )
        .all()
    )
    return {t.metric_key: t for t in targets}


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
