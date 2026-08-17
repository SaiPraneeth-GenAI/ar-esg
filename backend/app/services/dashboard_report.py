"""Assembles the four dashboard tabs (Absolute Metrics, Intensity by
Production, Intensity by Revenue, Safety & Trends) into report sections for
the PDF/PPTX export. Every number comes from the exact same overview/trend
route functions the live dashboard calls -- called directly as plain
Python functions (not over HTTP) so the export can never show a figure
that disagrees with what's on screen. AI is used only to turn those
already-computed numbers into one short narrative paragraph per section
(see services/dashboard_insight.py's guardrails) -- it never sees raw
entries and never invents a figure."""

import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from app.api.routes.carbon import carbon_overview, carbon_trend
from app.api.routes.intensity import intensity_overview, intensity_trend
from app.api.routes.safety import safety_overview, safety_trend
from app.core.auth import CurrentUser
from app.services.dashboard_insight import generate_dashboard_insight
from app.services.report_charts import render_bar_chart
from app.services.rollups import month_start


@dataclass
class ReportTile:
    label: str
    value: str


@dataclass
class ReportSection:
    title: str
    narrative: str
    tiles: list[ReportTile]
    chart_png: bytes | None
    chart_title: str | None


@dataclass
class ReportMeta:
    title: str
    subtitle: str
    period_slug: str


def _fmt(value: float | None, decimals: int = 2, unit: str = "") -> str:
    if value is None:
        return "Not available"
    return f"{value:,.{decimals}f}{(' ' + unit) if unit else ''}"


def _period_label(period: date, period_mode: str) -> str:
    if period_mode == "quarter":
        quarter = (period.month - 1) // 3 + 1
        return f"Q{quarter} {period.year} to date"
    if period_mode == "ytd":
        return f"Year to date, {period.year}"
    return period.strftime("%B %Y")


def _month_labels(points: list) -> list[str]:
    return [p.period.strftime("%b") for p in points]


def _build_absolute_section(overview, trend) -> ReportSection:
    tiles = [
        ReportTile("Scope 1+2 (location-based)", _fmt(overview.scope1_2_location_based_tco2e, 2, "tCO2e")),
        ReportTile("Specific GHG emissions", _fmt(overview.intensity_tco2e_per_mnah, 3, "tCO2e/MnAh")),
        ReportTile("Scope 1", _fmt(overview.scope1_tco2e, 2, "tCO2e")),
        ReportTile("Scope 2 (location-based)", _fmt(overview.scope2_location_based_tco2e, 2, "tCO2e")),
        ReportTile("Data completeness", _fmt(overview.completeness_pct, 0, "%")),
    ]
    chart = None
    if trend:
        chart = render_bar_chart(
            _month_labels(trend),
            [p.scope1_2_location_based_tco2e for p in trend],
            [p.prior_year_scope1_2_location_based_tco2e for p in trend],
            "Scope 1+2 (location-based) -- trend",
            "tCO2e",
        )

    fallback_parts = [f"Scope 1+2 (location-based) emissions were {_fmt(overview.scope1_2_location_based_tco2e, 2, 'tCO2e')} this period."]
    if overview.sources:
        largest = max(overview.sources, key=lambda s: s.emissions_tco2e)
        fallback_parts.append(f"{largest.data_point_name} was the largest single source.")
    fallback = " ".join(fallback_parts)

    context = {
        "section": "Absolute Metrics",
        "scope1_tco2e": overview.scope1_tco2e,
        "scope2_location_based_tco2e": overview.scope2_location_based_tco2e,
        "scope1_2_location_based_tco2e": overview.scope1_2_location_based_tco2e,
        "prior_scope1_2_location_based_tco2e": overview.prior_scope1_2_location_based_tco2e,
        "prior_year_scope1_2_location_based_tco2e": overview.prior_year_scope1_2_location_based_tco2e,
        "ghg_intensity_tco2e_per_mnah": overview.intensity_tco2e_per_mnah,
        "completeness_pct": overview.completeness_pct,
        "targets": [
            {"metric": t.label, "actual": t.actual, "target_value": t.target_value, "status": t.status} for t in overview.all_targets
        ],
    }
    narrative = generate_dashboard_insight(context, fallback) or fallback

    return ReportSection("Absolute Metrics", narrative, tiles, chart, "Scope 1+2 -- last 6 periods")


def _build_intensity_section(title: str, overview, trend, mode: str) -> ReportSection:
    suffix = "per_production" if mode == "production" else "per_revenue"
    denom_unit = "tCO2e/MnAh" if mode == "production" else "tCO2e/Cr"
    energy_unit = "GJ/MnAh" if mode == "production" else "GJ/Cr"
    water_unit = "KL/MnAh" if mode == "production" else "KL/Cr"
    waste_unit = "MT/MnAh" if mode == "production" else "MT/Cr"

    ghg = getattr(overview, f"ghg_{suffix}")
    energy = getattr(overview, f"energy_{suffix}")
    water = getattr(overview, f"water_{suffix}")
    waste = getattr(overview, f"waste_{suffix}")

    denom_label = "Battery production" if mode == "production" else "Revenue"
    denom_value = overview.production_mnah if mode == "production" else overview.revenue_inr_cr
    denom_unit_label = "MnAh" if mode == "production" else "INR Cr"

    tiles = [
        ReportTile(f"{denom_label} this period", _fmt(denom_value, 1, denom_unit_label)),
        ReportTile("GHG emissions", _fmt(ghg, 4, denom_unit)),
        ReportTile("Energy consumption", _fmt(energy, 4, energy_unit)),
        ReportTile("Water withdrawal", _fmt(water, 4, water_unit)),
        ReportTile("Waste generated", _fmt(waste, 4, waste_unit)),
    ]

    trend_key = f"ghg_{suffix}"
    prior_key = f"prior_year_ghg_{suffix}"
    chart = None
    if trend:
        chart = render_bar_chart(
            _month_labels(trend),
            [getattr(p, trend_key) for p in trend],
            [getattr(p, prior_key) for p in trend],
            f"GHG emissions ({mode}) -- trend",
            denom_unit,
        )

    fallback = f"GHG emissions were {_fmt(ghg, 4, denom_unit)} this period, against {denom_label.lower()} of {_fmt(denom_value, 1, denom_unit_label)}."

    context = {
        "section": title,
        "denominator_label": denom_label,
        "denominator_value": denom_value,
        "ghg": ghg,
        "energy": energy,
        "water": water,
        "waste": waste,
        "targets": [
            {"metric": key, "actual": getattr(overview, f"{key}_{suffix}"), **_target_dict(getattr(overview, f"{key}_{suffix}_target"))}
            for key in ("ghg", "energy", "water", "waste")
            if getattr(overview, f"{key}_{suffix}_target") is not None
        ],
    }
    narrative = generate_dashboard_insight(context, fallback) or fallback

    return ReportSection(title, narrative, tiles, chart, f"GHG emissions ({mode}) -- last 6 periods")


def _target_dict(target) -> dict:
    if target is None:
        return {}
    return {"target_value": target.target_value, "status": target.status}


def _build_safety_section(overview, trend) -> ReportSection:
    tiles = [ReportTile(m.name, _fmt(m.value, 2, m.unit) if m.value is not None else "Not entered") for m in overview.metrics]

    chart = None
    ltifr = next((m for m in overview.metrics if m.name == "LTIFR"), None)
    if trend:
        chart = render_bar_chart(
            _month_labels(trend),
            [p.values.get("LTIFR") for p in trend],
            [p.prior_year_values.get("LTIFR") for p in trend],
            "LTIFR -- trend",
            "Rate",
        )

    fallback_parts = []
    for m in overview.metrics:
        if m.value is not None:
            fallback_parts.append(f"{m.name}: {_fmt(m.value, 2, m.unit)}")
    fallback = "This period's safety metrics -- " + ", ".join(fallback_parts) + "." if fallback_parts else "No safety data entered for this period yet."

    context = {
        "section": "Safety & Trends",
        "metrics": [
            {"name": m.name, "value": m.value, "unit": m.unit, "prior_value": m.prior_value, "prior_year_value": m.prior_year_value}
            for m in overview.metrics
        ],
    }
    narrative = generate_dashboard_insight(context, fallback) or fallback

    return ReportSection("Safety & Trends", narrative, tiles, chart, "LTIFR -- last 6 periods")


def build_report_sections(
    db: Session, current: CurrentUser, period: date, period_mode: str, location_id: uuid.UUID | None
) -> tuple[list[ReportSection], ReportMeta]:
    period = month_start(period)

    overview = carbon_overview(period=period, location_id=location_id, period_mode=period_mode, current=current, db=db)
    trend = carbon_trend(period=period, months=6, location_id=location_id, period_mode=period_mode, current=current, db=db)
    absolute_section = _build_absolute_section(overview, trend)

    intensity_ov = intensity_overview(period=period, location_id=location_id, period_mode=period_mode, current=current, db=db)
    intensity_tr = intensity_trend(period=period, months=6, location_id=location_id, period_mode=period_mode, current=current, db=db)
    production_section = _build_intensity_section("Intensity by Production", intensity_ov, intensity_tr, "production")
    revenue_section = _build_intensity_section("Intensity by Revenue", intensity_ov, intensity_tr, "revenue")

    safety_ov = safety_overview(period=period, location_id=location_id, period_mode=period_mode, current=current, db=db)
    safety_tr = safety_trend(period=period, months=6, location_id=location_id, period_mode=period_mode, current=current, db=db)
    safety_section = _build_safety_section(safety_ov, safety_tr)

    meta = ReportMeta(
        title="Amara Raja ESG Dashboard",
        subtitle=f"{_period_label(period, period_mode)} -- {'Company-wide' if location_id is None else 'Selected site'}",
        period_slug=period.isoformat()[:7],
    )
    return [absolute_section, production_section, revenue_section, safety_section], meta
