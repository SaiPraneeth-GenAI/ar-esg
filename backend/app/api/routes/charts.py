"""Chart Builder v1 -- scoped to the existing stack (see
docs/CHART_BRAINSTORM_QA.md for the original, larger spec this descends
from: that one assumed React + Apache ECharts + S3, this one reuses the
Angular app's existing hand-rolled charts and Postgres). A "chart" here is
never custom SQL or an arbitrary query -- it's a metric key picked from
the fixed CHARTABLE_METRICS registry below, each of which is a thin
pass-through to the SAME trend functions /carbon, /intensity, and /safety
already expose, so a custom chart's numbers can never drift from the
dashboard's. Saved charts store only that metric key plus display
settings (chart kind, period mode, months, location) -- never a snapshot,
so a chart always reflects live approved data at view time."""

import uuid
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.routes.carbon import carbon_overview, carbon_trend
from app.api.routes.intensity import intensity_trend
from app.api.routes.safety import safety_trend
from app.core.auth import CurrentUser, require_roles
from app.db.models import SavedChart, User
from app.db.session import get_db
from app.schemas.charts import (
    BreakdownDataOut,
    BreakdownDimensionOut,
    BreakdownSlice,
    ChartMetricDataOut,
    ChartMetricOut,
    ChartMetricPoint,
    SavedChartCreate,
    SavedChartOut,
    SavedChartUpdate,
)

router = APIRouter(prefix="/charts", tags=["charts"])

CHARTABLE_METRICS: dict[str, dict] = {
    "scope1_tco2e": {
        "label": "Scope 1", "unit": "tCO2e", "group": "GHG",
        "source": "carbon", "field": "scope1_tco2e", "prior_field": "prior_year_scope1_tco2e",
    },
    "scope2_tco2e": {
        "label": "Scope 2 (location-based)", "unit": "tCO2e", "group": "GHG",
        "source": "carbon", "field": "scope2_location_based_tco2e", "prior_field": "prior_year_scope2_location_based_tco2e",
    },
    "scope1_2_tco2e": {
        "label": "Scope 1+2 (location-based)", "unit": "tCO2e", "group": "GHG",
        "source": "carbon", "field": "scope1_2_location_based_tco2e", "prior_field": "prior_year_scope1_2_location_based_tco2e",
    },
    "ghg_intensity_production": {
        "label": "GHG intensity", "unit": "tCO2e/MnAh", "group": "Intensity by production",
        "source": "carbon", "field": "intensity_tco2e_per_mnah", "prior_field": "prior_year_intensity_tco2e_per_mnah",
    },
    "energy_per_production": {
        "label": "Energy intensity", "unit": "GJ/MnAh", "group": "Intensity by production",
        "source": "intensity", "field": "energy_per_production", "prior_field": "prior_year_energy_per_production",
    },
    "water_per_production": {
        "label": "Water intensity", "unit": "KL/MnAh", "group": "Intensity by production",
        "source": "intensity", "field": "water_per_production", "prior_field": "prior_year_water_per_production",
    },
    "waste_per_production": {
        "label": "Waste intensity", "unit": "MT/MnAh", "group": "Intensity by production",
        "source": "intensity", "field": "waste_per_production", "prior_field": "prior_year_waste_per_production",
    },
    "ghg_per_revenue": {
        "label": "GHG intensity", "unit": "tCO2e/Cr", "group": "Intensity by revenue",
        "source": "intensity", "field": "ghg_per_revenue", "prior_field": "prior_year_ghg_per_revenue",
    },
    "energy_per_revenue": {
        "label": "Energy intensity", "unit": "GJ/Cr", "group": "Intensity by revenue",
        "source": "intensity", "field": "energy_per_revenue", "prior_field": "prior_year_energy_per_revenue",
    },
    "water_per_revenue": {
        "label": "Water intensity", "unit": "KL/Cr", "group": "Intensity by revenue",
        "source": "intensity", "field": "water_per_revenue", "prior_field": "prior_year_water_per_revenue",
    },
    "waste_per_revenue": {
        "label": "Waste intensity", "unit": "MT/Cr", "group": "Intensity by revenue",
        "source": "intensity", "field": "waste_per_revenue", "prior_field": "prior_year_waste_per_revenue",
    },
    "safety_fatality": {"label": "Fatalities", "unit": "Nos", "group": "Safety", "source": "safety", "field": "Fatality"},
    "safety_ltifr": {"label": "LTIFR", "unit": "Rate", "group": "Safety", "source": "safety", "field": "LTIFR"},
    "safety_training": {
        "label": "Defensive Driving Training", "unit": "%", "group": "Safety",
        "source": "safety", "field": "Defensive Driving Training",
    },
    "safety_unsafe": {"label": "Unsafe Conditions", "unit": "Nos", "group": "Safety", "source": "safety", "field": "Unsafe Conditions"},
    "safety_near_miss": {"label": "Near Miss", "unit": "Nos", "group": "Safety", "source": "safety", "field": "Near Miss"},
}


@router.get("/metrics", response_model=list[ChartMetricOut])
def list_chartable_metrics(current: CurrentUser = Depends(require_roles("Admin", "Manager", "Approver"))):
    return [ChartMetricOut(key=key, label=spec["label"], unit=spec["unit"], group=spec["group"]) for key, spec in CHARTABLE_METRICS.items()]


@router.get("/metric-data", response_model=ChartMetricDataOut)
def get_metric_data(
    metric: str,
    period: date,
    period_mode: str = "month",
    months: int = 6,
    location_id: uuid.UUID | None = None,
    current: CurrentUser = Depends(require_roles("Admin", "Manager", "Approver")),
    db: Session = Depends(get_db),
):
    """One metric's trend, by delegating to the same carbon/intensity/
    safety trend functions the built-in dashboard charts call -- never a
    separate calculation path, so a custom chart's numbers can never
    disagree with the dashboard's."""
    spec = CHARTABLE_METRICS.get(metric)
    if spec is None:
        raise HTTPException(status_code=404, detail="Unknown metric.")

    if spec["source"] == "carbon":
        rows = carbon_trend(period=period, months=months, location_id=location_id, period_mode=period_mode, current=current, db=db)
        points = [
            ChartMetricPoint(
                period=r.period, bucket_start=r.bucket_start, bucket_end=r.bucket_end,
                value=getattr(r, spec["field"]), prior_year_value=getattr(r, spec["prior_field"]),
            )
            for r in rows
        ]
    elif spec["source"] == "intensity":
        rows = intensity_trend(period=period, months=months, location_id=location_id, period_mode=period_mode, current=current, db=db)
        points = [
            ChartMetricPoint(
                period=r.period, bucket_start=r.bucket_start, bucket_end=r.bucket_end,
                value=getattr(r, spec["field"]), prior_year_value=getattr(r, spec["prior_field"]),
            )
            for r in rows
        ]
    else:
        rows = safety_trend(period=period, months=months, location_id=location_id, period_mode=period_mode, current=current, db=db)
        points = [
            ChartMetricPoint(
                period=r.period, bucket_start=r.bucket_start, bucket_end=r.bucket_end,
                value=r.values.get(spec["field"]), prior_year_value=r.prior_year_values.get(spec["field"]),
            )
            for r in rows
        ]

    return ChartMetricDataOut(metric=metric, label=spec["label"], unit=spec["unit"], period_mode=period_mode, points=points)


# "Breakdown" question type ("what % is X vs Y vs Z", "who's the top
# contributor") -- reuses the exact source-level breakdown carbon_overview
# already computes for the dashboard's contributor pies, sliced to total
# emissions or to one scope. GHG is the only category with a genuine
# multi-source breakdown in this platform right now (Water/Waste are
# single approved-total categories, not itemized by source the way GHG's
# five source data points are) -- more dimensions can be added here as the
# underlying per-source data exists elsewhere.
BREAKDOWN_DIMENSIONS: dict[str, str] = {
    "ghg_total": "Total emissions, by source",
    "ghg_scope1": "Scope 1, by source",
    "ghg_scope2": "Scope 2 (location-based), by source",
}


@router.get("/breakdown-dimensions", response_model=list[BreakdownDimensionOut])
def list_breakdown_dimensions(current: CurrentUser = Depends(require_roles("Admin", "Manager", "Approver"))):
    return [BreakdownDimensionOut(key=key, label=label) for key, label in BREAKDOWN_DIMENSIONS.items()]


@router.get("/breakdown-data", response_model=BreakdownDataOut)
def get_breakdown_data(
    dimension: str,
    period: date,
    period_mode: str = "month",
    location_id: uuid.UUID | None = None,
    current: CurrentUser = Depends(require_roles("Admin", "Manager", "Approver")),
    db: Session = Depends(get_db),
):
    if dimension not in BREAKDOWN_DIMENSIONS:
        raise HTTPException(status_code=404, detail="Unknown breakdown dimension.")

    overview = carbon_overview(period=period, location_id=location_id, period_mode=period_mode, current=current, db=db)
    sources = [s for s in overview.sources if s.calculation_method != "market_based"]
    if dimension == "ghg_scope1":
        sources = [s for s in sources if s.scope == 1]
    elif dimension == "ghg_scope2":
        sources = [s for s in sources if s.scope == 2]

    by_name: dict[str, float] = {}
    for s in sources:
        by_name[s.data_point_name] = by_name.get(s.data_point_name, 0.0) + s.emissions_tco2e

    slices = [BreakdownSlice(label=name, value=value) for name, value in by_name.items()]
    return BreakdownDataOut(dimension=dimension, label=BREAKDOWN_DIMENSIONS[dimension], unit="tCO2e", period_mode=period_mode, slices=slices)


def _chart_out(db: Session, chart: SavedChart) -> SavedChartOut:
    owner = db.get(User, chart.owner_id)
    return SavedChartOut(
        id=chart.id,
        name=chart.name,
        description=chart.description,
        config=chart.config,
        owner_id=chart.owner_id,
        owner_email=owner.email if owner else None,
        created_at=chart.created_at,
        updated_at=chart.updated_at,
    )


def _get_owned_chart(db: Session, current: CurrentUser, chart_id: uuid.UUID) -> SavedChart:
    """Personal-only in v1 -- an owner can see/edit/delete their own
    charts, no org sharing yet (matches the doc's own MVP permissions
    section: sharing is explicitly a v2 decision, not v1)."""
    chart = (
        db.query(SavedChart)
        .filter(SavedChart.id == chart_id, SavedChart.tenant_id == current.tenant_id, SavedChart.owner_id == current.id)
        .first()
    )
    if chart is None:
        raise HTTPException(status_code=404, detail="Chart not found.")
    return chart


def _validate_config(config) -> None:
    """Each question type stores different fields -- validate only the
    ones the picked question actually uses, against the fixed registries
    above (never arbitrary values)."""
    if config.question_type == "trend":
        if config.metric not in CHARTABLE_METRICS:
            raise HTTPException(status_code=422, detail="Unknown metric.")
    elif config.question_type == "breakdown":
        if config.dimension not in BREAKDOWN_DIMENSIONS:
            raise HTTPException(status_code=422, detail="Unknown breakdown dimension.")
    elif config.question_type == "comparison":
        if config.comparison_mode == "peers":
            if config.metric not in CHARTABLE_METRICS:
                raise HTTPException(status_code=422, detail="Unknown metric.")
            if not config.compare_peer_ids:
                raise HTTPException(status_code=422, detail="Pick at least one peer to compare against.")
        else:
            if not config.metrics or not (2 <= len(config.metrics) <= 6):
                raise HTTPException(status_code=422, detail="Pick between 2 and 6 metrics to compare.")
            if any(m not in CHARTABLE_METRICS for m in config.metrics):
                raise HTTPException(status_code=422, detail="Unknown metric.")
    else:
        raise HTTPException(status_code=422, detail="Unknown question type.")


@router.post("", response_model=SavedChartOut)
def create_chart(
    payload: SavedChartCreate,
    current: CurrentUser = Depends(require_roles("Admin", "Manager", "Approver")),
    db: Session = Depends(get_db),
):
    _validate_config(payload.config)
    chart = SavedChart(
        tenant_id=current.tenant_id,
        owner_id=current.id,
        name=payload.name,
        description=payload.description,
        config=payload.config.model_dump(mode="json"),
    )
    db.add(chart)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="You already have a chart with this name.")
    db.refresh(chart)
    return _chart_out(db, chart)


@router.get("", response_model=list[SavedChartOut])
def list_charts(
    current: CurrentUser = Depends(require_roles("Admin", "Manager", "Approver")),
    db: Session = Depends(get_db),
):
    charts = (
        db.query(SavedChart)
        .filter(SavedChart.tenant_id == current.tenant_id, SavedChart.owner_id == current.id)
        .order_by(SavedChart.updated_at.desc())
        .all()
    )
    return [_chart_out(db, c) for c in charts]


@router.get("/{chart_id}", response_model=SavedChartOut)
def get_chart(
    chart_id: uuid.UUID,
    current: CurrentUser = Depends(require_roles("Admin", "Manager", "Approver")),
    db: Session = Depends(get_db),
):
    return _chart_out(db, _get_owned_chart(db, current, chart_id))


@router.put("/{chart_id}", response_model=SavedChartOut)
def update_chart(
    chart_id: uuid.UUID,
    payload: SavedChartUpdate,
    current: CurrentUser = Depends(require_roles("Admin", "Manager", "Approver")),
    db: Session = Depends(get_db),
):
    chart = _get_owned_chart(db, current, chart_id)
    if payload.name is not None:
        chart.name = payload.name
    if payload.description is not None:
        chart.description = payload.description
    if payload.config is not None:
        _validate_config(payload.config)
        chart.config = payload.config.model_dump(mode="json")
    chart.updated_at = datetime.now(timezone.utc)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="You already have a chart with this name.")
    db.refresh(chart)
    return _chart_out(db, chart)


@router.delete("/{chart_id}", status_code=204)
def delete_chart(
    chart_id: uuid.UUID,
    current: CurrentUser = Depends(require_roles("Admin", "Manager", "Approver")),
    db: Session = Depends(get_db),
):
    chart = _get_owned_chart(db, current, chart_id)
    db.delete(chart)
    db.commit()
