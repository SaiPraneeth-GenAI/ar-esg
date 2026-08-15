from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, get_current_user
from app.db.models import Category, DataPoint, Entry, Location, Rollup
from app.db.session import get_db
from app.schemas.dashboard import DashboardCard, DashboardSummary, DrilldownEntry, DrilldownResponse
from app.services.rollups import month_start

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

# Categories with rollups wired up so far. Grows as Ozone/Effluent/Air ship.
REPORTABLE_CATEGORIES = ["Water", "Waste"]
PRODUCTION_CATEGORY = "Production"


def _prior_month(d: date) -> date:
    if d.month == 1:
        return d.replace(year=d.year - 1, month=12)
    return d.replace(month=d.month - 1)


def _next_month(d: date) -> date:
    if d.month == 12:
        return d.replace(year=d.year + 1, month=1)
    return d.replace(month=d.month + 1)


def _pct_change(current: float, prior: float | None) -> float | None:
    if prior is None or prior == 0:
        return None
    return (current - prior) / prior * 100


def _status_for_value(value: float, target: float | None) -> str:
    """Lower is better for every category we roll up today (withdrawal, waste generated)."""
    if target is None or target == 0:
        return "neutral"
    ratio = value / target
    if ratio <= 1.0:
        return "green"
    if ratio <= 1.1:
        return "amber"
    return "red"


def _category_unit(db: Session, tenant_id, category_name: str) -> str:
    dp = (
        db.query(DataPoint)
        .join(Category, Category.id == DataPoint.category_id)
        .filter(Category.tenant_id == tenant_id, Category.name == category_name)
        .first()
    )
    return dp.unit if dp and dp.unit else ""


def _category_total(db: Session, tenant_id, category_name: str, period: date) -> tuple[float | None, float | None]:
    rows = (
        db.query(Rollup)
        .filter(Rollup.tenant_id == tenant_id, Rollup.category == category_name, Rollup.period == period)
        .all()
    )
    if not rows:
        return None, None
    values = [r.aggregated_value for r in rows if r.aggregated_value is not None]
    total = sum(values) if values else None
    targets = [r.target_value for r in rows if r.target_value is not None]
    target = sum(targets) if targets else None
    return total, target


@router.get("/summary", response_model=DashboardSummary)
def get_summary(current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    latest = (
        db.query(func.max(Rollup.period))
        .filter(Rollup.tenant_id == current.tenant_id, Rollup.category.in_(REPORTABLE_CATEGORIES))
        .scalar()
    )
    if latest is None:
        return DashboardSummary(period=None, cards=[])

    prior_period = _prior_month(latest)
    cards: list[DashboardCard] = []

    for category in REPORTABLE_CATEGORIES:
        total, target = _category_total(db, current.tenant_id, category, latest)
        if total is None:
            continue

        unit = _category_unit(db, current.tenant_id, category)
        prior_total, _ = _category_total(db, current.tenant_id, category, prior_period)

        if target is not None and target > 0:
            pct = (total - target) / target * 100
            comparison = f"{abs(pct):.0f}% {'over' if pct > 0 else 'under'} target"
        elif prior_total:
            pct = _pct_change(total, prior_total)
            comparison = (
                f"{abs(pct):.0f}% {'higher' if pct > 0 else 'lower'} than last month"
                if pct is not None
                else "No comparison available"
            )
        else:
            comparison = "No comparison available"

        cards.append(
            DashboardCard(
                category=category,
                metric_type="total",
                label=f"{category} — Total",
                value=round(total, 2),
                unit=unit,
                status=_status_for_value(total, target),
                comparison_label=comparison,
                period=latest,
            )
        )

        prod_total, _ = _category_total(db, current.tenant_id, PRODUCTION_CATEGORY, latest)
        prod_prior, _ = _category_total(db, current.tenant_id, PRODUCTION_CATEGORY, prior_period)

        if prod_total:
            intensity = total / prod_total
            prior_intensity = (prior_total / prod_prior) if (prior_total is not None and prod_prior) else None
            pct = _pct_change(intensity, prior_intensity)

            if pct is not None:
                comparison_i = f"{abs(pct):.0f}% {'higher' if pct > 0 else 'lower'} than last month"
                status_i = "green" if pct <= 0 else ("amber" if pct <= 10 else "red")
            else:
                comparison_i = "No comparison available"
                status_i = "neutral"

            production_unit = _category_unit(db, current.tenant_id, PRODUCTION_CATEGORY)
            cards.append(
                DashboardCard(
                    category=category,
                    metric_type="intensity",
                    label=f"{category} — Intensity",
                    value=round(intensity, 3),
                    unit=f"{unit}/{production_unit}",
                    status=status_i,
                    comparison_label=comparison_i,
                    period=latest,
                )
            )

    return DashboardSummary(period=latest, cards=cards)


def _entries_for_category(db: Session, tenant_id, category_name: str, period: date) -> list[DrilldownEntry]:
    period = month_start(period)
    upper = _next_month(period)
    rows = (
        db.query(Entry, DataPoint.name, DataPoint.unit, Location.name)
        .join(DataPoint, DataPoint.id == Entry.data_point_id)
        .join(Category, Category.id == DataPoint.category_id)
        .join(Location, Location.id == Entry.location_id)
        .filter(
            Category.tenant_id == tenant_id,
            Category.name == category_name,
            Entry.status == "Approved",
            Entry.period >= period,
            Entry.period < upper,
        )
        .order_by(Location.name, DataPoint.name)
        .all()
    )
    return [
        DrilldownEntry(
            location_name=loc_name,
            data_point_name=dp_name,
            value=float(entry.value),
            unit=dp_unit or "",
            period=entry.period,
            method_of_entry=entry.method_of_entry,
        )
        for entry, dp_name, dp_unit, loc_name in rows
    ]


@router.get("/drilldown", response_model=DrilldownResponse)
def get_drilldown(
    category: str,
    period: date,
    metric_type: str = "total",
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    period = month_start(period)
    entries = _entries_for_category(db, current.tenant_id, category, period)
    production_entries: list[DrilldownEntry] = []
    if metric_type == "intensity":
        production_entries = _entries_for_category(db, current.tenant_id, PRODUCTION_CATEGORY, period)

    return DrilldownResponse(
        category=category,
        metric_type=metric_type,
        period=period,
        entries=entries,
        production_entries=production_entries,
    )
