"""Operator-only demo seeding for the OCEANS Carbon Offset tenant, run by
invoking the backend Lambda directly with IAM (see lambda_handler.py) --
never reachable over HTTP.

Two jobs, both idempotent (re-running only fills what is still missing, so
a run cut short by the Lambda timeout simply resumes):

1. "Live" months: every Scope 1/2, water, waste, safety, production and
   revenue field that a site has been reporting gets a value for the
   requested months (September/October 2026), derived from that same
   site's own recent readings -- recent average, a small drift and
   deterministic noise -- so each site stays consistent with its history.

2. Scope 3 (value chain): the GHG Protocol categories that matter for a
   battery manufacturer are created as Data Entry categories with
   tenant emission factors, and a monthly history is generated. Physical
   drivers come from the site's own data wherever one exists: purchased
   materials, freight and end-of-life scale with that month's battery
   production; upstream energy follows the site's grid electricity and
   diesel; waste-in-operations follows its waste disposal records.

Everything goes through the same bulk-import -> auto-approve ->
calculate -> rollup path a real upload uses, so audit history, emission
calculation snapshots and dashboard rollups are all genuine. Values are
plausible demo figures, not measurements, and every entry note says so.
"""

from __future__ import annotations

import asyncio
import math
import random
import uuid
from datetime import date
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.routes.entries import bulk_import
from app.api.routes.targets import bulk_import_targets
from app.core.auth import CurrentUser
from app.core.carbon_mapping import CARBON_SOURCE_MAPPING, get_carbon_mapping
from app.db.models import Category, DataPoint, EmissionFactor, EmissionTarget, Entry, Location, User
from app.schemas.entries import BulkImportRequest, BulkImportRowIn
from app.schemas.targets import TargetBulkImportRequest, TargetBulkRowIn
from app.services.carbon_calculation import months_in_range, shift_months

DEMO_NOTE = "Demo data — OCEANS live sample"

# ---- Scope 3 catalogue ------------------------------------------------------
# (category name, [(data point, unit, tooltip)])
SCOPE3_CATEGORIES: list[tuple[str, list[tuple[str, str, str]]]] = [
    ("Purchased Goods & Services", [
        ("Primary Lead Purchased", "t", "Virgin (smelted) lead bought for grids and oxide, in tonnes. GHG Protocol Scope 3 Cat 1."),
        ("Secondary (Recycled) Lead Purchased", "t", "Refined lead recovered from spent batteries, in tonnes -- the main lever for cutting Cat 1 emissions."),
        ("Sulphuric Acid Purchased", "t", "Battery-grade sulphuric acid for electrolyte, in tonnes."),
        ("Polypropylene Purchased", "t", "PP granules for containers and lids, in tonnes."),
        ("Lithium-ion Cells Purchased", "kWh", "Purchased Li-ion cell capacity for battery packs, in kWh of nameplate capacity."),
        ("Separators & Plastics Purchased", "t", "PE separators and other engineering plastics, in tonnes."),
    ]),
    ("Capital Goods", [
        ("Capex — Plant & Machinery", "INR lakh", "Capital spend on machinery and equipment this month (spend-based, INR lakh). Scope 3 Cat 2."),
        ("Capex — Buildings & Civil Works", "INR lakh", "Capital spend on buildings and civil works this month (spend-based, INR lakh)."),
    ]),
    ("Fuel & Energy (Upstream)", [
        ("Electricity T&D Losses & Upstream", "kWh", "Grid electricity consumed, used to account for generation upstream and T&D losses. Scope 3 Cat 3."),
        ("Diesel Well-to-Tank", "litres", "Diesel consumed, used to account for extraction, refining and transport of the fuel."),
    ]),
    ("Upstream Transportation", [
        ("Inbound Road Freight", "tkm", "Tonne-kilometres of raw material moved to site by truck. Scope 3 Cat 4."),
        ("Inbound Sea Freight", "tkm", "Tonne-kilometres of imported material (cells, polymer) moved by container ship."),
    ]),
    ("Operational Waste (Third-Party)", [
        ("Waste to Third-Party Landfill", "t", "Waste sent to landfill through an authorised third party. Scope 3 Cat 5."),
        ("Waste to Third-Party Incineration", "t", "Waste sent for incineration / co-processing through a third party."),
        ("Waste to Third-Party Recycling", "t", "Waste sent to third-party recyclers."),
    ]),
    ("Business Travel", [
        ("Air Travel — Domestic", "pkm", "Passenger-kilometres flown on domestic routes. Scope 3 Cat 6."),
        ("Air Travel — International", "pkm", "Passenger-kilometres flown on international routes."),
        ("Rail Travel", "pkm", "Passenger-kilometres travelled by rail."),
        ("Hotel Stays", "room-nights", "Hotel room-nights booked for business travel."),
    ]),
    ("Employee Commuting", [
        ("Commute — Company Bus", "pkm", "Passenger-kilometres on company-run buses. Scope 3 Cat 7."),
        ("Commute — Two-Wheeler", "km", "Kilometres commuted by employees on two-wheelers (survey-based)."),
        ("Commute — Car", "km", "Kilometres commuted by employees by car (survey-based)."),
    ]),
    ("Downstream Transportation", [
        ("Outbound Road Freight", "tkm", "Tonne-kilometres of finished batteries shipped to warehouses and OEMs. Scope 3 Cat 9."),
        ("Dealer Distribution — LCV", "km", "Kilometres driven by light commercial vehicles delivering to dealers."),
    ]),
    ("End-of-Life of Sold Products", [
        ("Spent Batteries Collected for Recycling", "t", "Tonnes of sold batteries reaching end of life and collected for recycling. Scope 3 Cat 12."),
        ("Spent Batteries — Uncollected (Est.)", "t", "Estimated tonnes of sold batteries reaching end of life outside formal collection."),
    ]),
]

# substance (= carbon_mapping ipcc_substance) -> (factor unit, kgCO2e per unit, source reference)
_IND = "Indicative demo factor"
SCOPE3_FACTORS: dict[str, tuple[str, float, str]] = {
    "Primary lead": ("kgCO2e/t", 2050.0, f"{_IND} -- primary lead production, ILA LCA (2022) range"),
    "Secondary lead": ("kgCO2e/t", 610.0, f"{_IND} -- secondary (recycled) lead refining, ILA LCA (2022) range"),
    "Sulphuric acid": ("kgCO2e/t", 120.0, f"{_IND} -- sulphuric acid production, ecoinvent-style average"),
    "Polypropylene": ("kgCO2e/t", 1860.0, f"{_IND} -- PP granulate, PlasticsEurope eco-profile range"),
    "Lithium-ion cells": ("kgCO2e/kWh", 72.0, f"{_IND} -- Li-ion cell manufacturing, published LCA average"),
    "Separators & engineering plastics": ("kgCO2e/t", 2400.0, f"{_IND} -- PE separators / engineering plastics"),
    "Capex plant & machinery": ("kgCO2e/INR lakh", 410.0, f"{_IND} -- spend-based EEIO, machinery & equipment"),
    "Capex buildings & civil": ("kgCO2e/INR lakh", 520.0, f"{_IND} -- spend-based EEIO, construction"),
    "Grid electricity WTT + T&D": ("kgCO2e/kWh", 0.155, f"{_IND} -- India grid upstream generation + T&D losses"),
    "Diesel WTT": ("kgCO2e/litre", 0.61, f"{_IND} -- DEFRA well-to-tank, diesel"),
    "Road freight (HGV)": ("kgCO2e/tkm", 0.105, f"{_IND} -- DEFRA HGV average laden"),
    "Sea freight (container)": ("kgCO2e/tkm", 0.016, f"{_IND} -- DEFRA container ship average"),
    "Waste to landfill": ("kgCO2e/t", 520.0, f"{_IND} -- DEFRA commercial & industrial waste to landfill"),
    "Waste incineration": ("kgCO2e/t", 21.3, f"{_IND} -- DEFRA combustion / energy recovery"),
    "Waste recycling": ("kgCO2e/t", 21.3, f"{_IND} -- DEFRA open/closed-loop recycling"),
    "Air travel domestic": ("kgCO2e/pkm", 0.246, f"{_IND} -- DEFRA domestic flight, incl. RF"),
    "Air travel international": ("kgCO2e/pkm", 0.185, f"{_IND} -- DEFRA long-haul economy, incl. RF"),
    "Rail travel": ("kgCO2e/pkm", 0.0076, f"{_IND} -- Indian Railways average"),
    "Hotel stay": ("kgCO2e/room-night", 31.0, f"{_IND} -- hotel stay, India average"),
    "Company bus": ("kgCO2e/pkm", 0.028, f"{_IND} -- diesel bus, high occupancy"),
    "Two-wheeler": ("kgCO2e/km", 0.035, f"{_IND} -- motorcycle/scooter, India average"),
    "Car (petrol/diesel avg)": ("kgCO2e/km", 0.168, f"{_IND} -- average car, unknown fuel"),
    "Road freight (HGV) outbound": ("kgCO2e/tkm", 0.105, f"{_IND} -- DEFRA HGV average laden"),
    "Light commercial vehicle": ("kgCO2e/km", 0.24, f"{_IND} -- DEFRA van class III, diesel"),
    "End-of-life battery recycling": ("kgCO2e/t", 230.0, f"{_IND} -- collection + secondary smelting share"),
    "End-of-life battery uncollected": ("kgCO2e/t", 410.0, f"{_IND} -- informal recycling / disposal"),
}

SCOPE3_TARGET_PCT = 5.0


# ---- helpers ----------------------------------------------------------------


def _rng(*parts) -> random.Random:
    return random.Random("|".join(str(p) for p in parts))


def _lerp(a: float, b: float, p: float) -> float:
    return a + (b - a) * p


def _acting_admin(db: Session, admin_email: str) -> tuple[User, CurrentUser]:
    user = db.query(User).filter(User.email.ilike(admin_email)).first()
    if user is None:
        raise RuntimeError(f"Admin user {admin_email} not found")
    current = CurrentUser(id=str(user.id), email=user.email, roles=list(user.roles or []) or ["Admin"], tenant_id=user.tenant_id)
    if "Admin" not in current.roles:
        raise RuntimeError(f"{admin_email} is not an Admin")
    return user, current


def _apply_scope3_target_migration(db: Session) -> None:
    sql = (Path(__file__).resolve().parents[2] / "migrations" / "0021_scope3_target_metric.sql").read_text(encoding="utf-8")
    body = "\n".join(line for line in sql.splitlines() if not line.lstrip().startswith("--"))
    for statement in (s.strip() for s in body.split(";")):
        if statement:
            db.execute(text(statement))
    db.commit()


def _ensure_scope3_catalogue(db: Session, tenant_id: uuid.UUID, actor_id: uuid.UUID) -> dict[str, int]:
    created = {"categories": 0, "data_points": 0, "factors": 0}
    max_order = db.query(Category.display_order).filter(Category.tenant_id == tenant_id).order_by(Category.display_order.desc().nullslast()).first()
    next_order = ((max_order[0] if max_order and max_order[0] is not None else 10) or 10) + 1

    for cat_name, points in SCOPE3_CATEGORIES:
        cat = db.query(Category).filter(Category.tenant_id == tenant_id, Category.name == cat_name).first()
        if cat is None:
            cat = Category(tenant_id=tenant_id, name=cat_name, industry_pack="battery manufacturing — scope 3", display_order=next_order)
            next_order += 1
            db.add(cat)
            db.flush()
            created["categories"] += 1
        for dp_name, unit, tooltip in points:
            dp = db.query(DataPoint).filter(DataPoint.category_id == cat.id, DataPoint.name == dp_name).first()
            if dp is None:
                db.add(DataPoint(
                    category_id=cat.id, name=dp_name, unit=unit, input_type="number",
                    validation_rules={"tooltip": tooltip}, framework_tags=["GHG Protocol Scope 3"],
                ))
                created["data_points"] += 1

    existing = {
        ((gas or "").strip().lower(), eff)
        for gas, eff in db.query(EmissionFactor.gas_type, EmissionFactor.effective_date)
        .filter(EmissionFactor.tenant_id == tenant_id, EmissionFactor.scope == 3)
        .all()
    }
    category_by_substance = {m.ipcc_substance: m.scope3_category for m in CARBON_SOURCE_MAPPING.values() if m.scope == 3}
    for substance, (unit, value, ref) in SCOPE3_FACTORS.items():
        for year in (2024, 2025, 2026):
            eff = date(year, 1, 1)
            if (substance.lower(), eff) in existing:
                continue
            db.add(EmissionFactor(
                tenant_id=tenant_id, scope=3, gas_type=substance, scope3_category=category_by_substance.get(substance),
                description=substance, unit=unit, factor_value=value, effective_date=eff, version=f"FY{str(year)[2:]}",
                source="OCEANS Scope 3 demo factor set", source_reference=ref, created_by=actor_id,
            ))
            created["factors"] += 1
    db.commit()
    return created


def _approved_series(db: Session, location_id: uuid.UUID, dp_ids: list[uuid.UUID]) -> dict[uuid.UUID, dict[date, float]]:
    out: dict[uuid.UUID, dict[date, float]] = {}
    if not dp_ids:
        return out
    for e in db.query(Entry).filter(Entry.location_id == location_id, Entry.data_point_id.in_(dp_ids), Entry.status == "Approved").all():
        if e.value is not None:
            out.setdefault(e.data_point_id, {})[e.period] = float(e.value)
    return out


def _import(db: Session, current: CurrentUser, location_id: uuid.UUID, rows: list[dict]) -> dict:
    if not rows:
        return {"created": 0, "errors": 0, "first_error": None}
    payload = BulkImportRequest(
        location_id=location_id, category=None, commit=True,
        rows=[
            BulkImportRowIn(
                row_index=i, category=r["category"], data_point_name=r["data_point_name"], year=r["period"].year,
                month=r["period"].month, value_raw=str(r["value"]), unit_raw=r["unit"], note=DEMO_NOTE,
            )
            for i, r in enumerate(rows)
        ],
    )
    result = asyncio.run(bulk_import(payload, current, db))
    first_error = next((r.message for r in result.rows if r.status == "error"), None)
    return {"created": result.created_count, "errors": result.error_count, "first_error": first_error}


# ---- 1. live months for the existing (non-Scope 3) fields ---------------------


def _live_rows_for_location(db: Session, tenant_id: uuid.UUID, location: Location, live_months: list[date]) -> list[dict]:
    first_live = live_months[0]
    lookback = months_in_range(shift_months(first_live, -6), shift_months(first_live, -1))
    dps = (
        db.query(DataPoint, Category.name)
        .join(Category, Category.id == DataPoint.category_id)
        .filter(Category.tenant_id == tenant_id)
        .all()
    )
    dps = [(dp, cat) for dp, cat in dps if not ((m := get_carbon_mapping(dp.name)) and m.scope == 3)]
    series = _approved_series(db, location.id, [dp.id for dp, _ in dps])
    existing = {
        (e.data_point_id, e.period)
        for e in db.query(Entry.data_point_id, Entry.period).filter(Entry.location_id == location.id, Entry.period.in_(live_months)).all()
    }

    rows = []
    for dp, cat_name in dps:
        history = series.get(dp.id, {})
        recent = [history[m] for m in lookback if m in history][-3:]
        if not recent:
            continue  # this site doesn't report this field -- don't invent it
        base = sum(recent) / len(recent)
        integer = all(float(v).is_integer() for v in recent)
        for k, month in enumerate(live_months, start=1):
            if (dp.id, month) in existing:
                continue
            if base == 0:
                value = 0
            else:
                r = _rng(location.id, dp.id, month)
                value = base * (1 + 0.006 * k) * (1 + r.uniform(-0.05, 0.05))
                if (dp.unit or "").strip() == "%":
                    value = min(value, 100.0)
                value = round(value) if integer else round(value, 4 if abs(base) < 1 else 2)
            rows.append({"category": cat_name, "data_point_name": dp.name, "period": month, "value": value, "unit": dp.unit or ""})
    return rows


# ---- 2. Scope 3 history -------------------------------------------------------


def _scope3_rows_for_location(
    db: Session, tenant_id: uuid.UUID, location: Location, months: list[date], production_scale: float
) -> list[dict]:
    dp_by_name = {
        dp.name: (dp, cat)
        for dp, cat in db.query(DataPoint, Category.name)
        .join(Category, Category.id == DataPoint.category_id)
        .filter(Category.tenant_id == tenant_id)
        .all()
    }
    production = dp_by_name.get("Battery Production Volume")
    grid = dp_by_name.get("Grid Electricity Consumed")
    diesel = dp_by_name.get("Diesel Consumed")
    waste_dps = {name: dp for name, (dp, cat) in dp_by_name.items() if cat == "Waste"}
    driver_ids = [d[0].id for d in (production, grid, diesel) if d] + [dp.id for dp in waste_dps.values()]
    series = _approved_series(db, location.id, driver_ids)
    prod_series = series.get(production[0].id, {}) if production else {}
    if not prod_series:
        return []

    scope3_dp_ids = [dp_by_name[n][0].id for _, pts in SCOPE3_CATEGORIES for n, _, _ in pts if n in dp_by_name]
    existing = {
        (e.data_point_id, e.period)
        for e in db.query(Entry.data_point_id, Entry.period).filter(Entry.location_id == location.id, Entry.data_point_id.in_(scope3_dp_ids)).all()
    }

    def waste_total(month: date, suffix: str) -> float | None:
        vals = [series.get(dp.id, {}).get(month) for name, dp in waste_dps.items() if name.endswith(suffix)]
        vals = [v for v in vals if v is not None]
        return round(sum(vals), 3) if vals else None

    n = len(months)
    rows = []
    for i, month in enumerate(months):
        p_mnah = prod_series.get(month)
        if p_mnah is None:
            continue
        p = i / max(n - 1, 1)
        r = _rng(location.id, "scope3", month)
        jitter = lambda pct: 1 + r.uniform(-pct, pct)  # noqa: E731
        season = 1 + 0.06 * math.sin(2 * math.pi * (month.month - 3) / 12)

        lead_primary = p_mnah * _lerp(1.20, 0.65, p) * jitter(0.04)
        lead_secondary = p_mnah * _lerp(2.20, 2.75, p) * jitter(0.04)
        acid = p_mnah * 1.35 * jitter(0.05)
        pp = p_mnah * 0.55 * jitter(0.05)
        li_kwh = p_mnah * _lerp(30, 34, p) * jitter(0.08)
        separators = p_mnah * 0.085 * jitter(0.06)
        inbound_t = lead_primary + lead_secondary + acid + pp + separators
        values = {
            "Primary Lead Purchased": round(lead_primary, 2),
            "Secondary (Recycled) Lead Purchased": round(lead_secondary, 2),
            "Sulphuric Acid Purchased": round(acid, 2),
            "Polypropylene Purchased": round(pp, 2),
            "Lithium-ion Cells Purchased": round(li_kwh, 0),
            "Separators & Plastics Purchased": round(separators, 3),
            "Capex — Plant & Machinery": round(16 * production_scale * (2.4 if month.month % 6 == 3 else 1) * jitter(0.35), 1),
            "Capex — Buildings & Civil Works": round(6 * production_scale * jitter(0.4), 1),
            "Inbound Road Freight": round(inbound_t * _lerp(640, 590, p) * jitter(0.05), 0),
            "Inbound Sea Freight": round((pp * 0.4 + li_kwh * 0.006) * 7800 * jitter(0.1), 0),
            "Air Travel — Domestic": round(42000 * production_scale * season * jitter(0.15), 0),
            "Air Travel — International": round(55000 * production_scale * jitter(0.25), 0),
            "Rail Travel": round(7500 * production_scale * jitter(0.2), 0),
            "Hotel Stays": round(130 * production_scale * season * jitter(0.15), 0),
            "Commute — Company Bus": round(250000 * production_scale * _lerp(0.92, 1.10, p) * jitter(0.05), 0),
            "Commute — Two-Wheeler": round(185000 * production_scale * _lerp(1.05, 0.88, p) * jitter(0.05), 0),
            "Commute — Car": round(42000 * production_scale * _lerp(1.05, 0.85, p) * jitter(0.06), 0),
            "Outbound Road Freight": round(p_mnah * 3.1 * 420 * season * jitter(0.06), 0),
            "Dealer Distribution — LCV": round(p_mnah * 520 * jitter(0.08), 0),
            "Spent Batteries Collected for Recycling": round(p_mnah * _lerp(2.6, 3.0, p) * jitter(0.05), 2),
            "Spent Batteries — Uncollected (Est.)": round(p_mnah * _lerp(0.55, 0.32, p) * jitter(0.06), 2),
        }
        if grid and (g := series.get(grid[0].id, {}).get(month)) is not None:
            values["Electricity T&D Losses & Upstream"] = round(g, 0)
        if diesel and (d := series.get(diesel[0].id, {}).get(month)) is not None:
            values["Diesel Well-to-Tank"] = round(d, 1)
        for name, suffix in (
            ("Waste to Third-Party Landfill", "Sent to Landfill"),
            ("Waste to Third-Party Incineration", "Incinerated"),
            ("Waste to Third-Party Recycling", "Recycled"),
        ):
            total = waste_total(month, suffix)
            if total is not None:
                values[name] = total

        for name, value in values.items():
            if name not in dp_by_name:
                continue
            dp, cat = dp_by_name[name]
            if (dp.id, month) in existing:
                continue
            rows.append({"category": cat, "data_point_name": name, "period": month, "value": value, "unit": dp.unit or ""})
    return rows


def _ensure_scope3_target(db: Session, current: CurrentUser) -> dict:
    active = (
        db.query(EmissionTarget)
        .filter(EmissionTarget.tenant_id == current.tenant_id, EmissionTarget.metric_key == "scope3_tco2e", EmissionTarget.status == "active")
        .first()
    )
    if active is not None:
        return {"activated": 0, "status": "already active"}
    payload = TargetBulkImportRequest(commit=True, rows=[TargetBulkRowIn(
        row_index=0, metric_key="scope3_tco2e", location_name=None,
        baseline_period_start=date(2025, 1, 1), baseline_period_end=date(2025, 12, 1),
        target_period_start=date(2026, 1, 1), target_period_end=date(2026, 12, 1),
        reduction_percentage=SCOPE3_TARGET_PCT,
        rationale="Cut value-chain (Scope 3) emissions 5% vs 2025 -- mainly by shifting to recycled lead.",
    )])
    result = bulk_import_targets(payload, current, db)
    return {"activated": result.activated_count, "errors": result.error_count, "detail": [r.message for r in result.rows if r.message]}


# ---- entry points -----------------------------------------------------------


def inspect(db: Session, admin_email: str) -> dict:
    _, current = _acting_admin(db, admin_email)
    locs = db.query(Location).filter(Location.tenant_id == current.tenant_id).all()
    by_month = db.execute(text(
        "select to_char(e.period,'YYYY-MM') m, e.status, count(*) from entry e join location l on l.id=e.location_id "
        "where l.tenant_id=:t and e.period >= date '2026-01-01' group by 1,2 order by 1,2"
    ), {"t": current.tenant_id}).all()
    per_loc = db.execute(text(
        "select l.name, to_char(max(e.period),'YYYY-MM'), count(*) from entry e join location l on l.id=e.location_id "
        "where l.tenant_id=:t group by 1 order by 1"
    ), {"t": current.tenant_id}).all()
    cats = db.query(Category).filter(Category.tenant_id == current.tenant_id).order_by(Category.display_order).all()
    targets = db.query(EmissionTarget.metric_key, EmissionTarget.status).filter(EmissionTarget.tenant_id == current.tenant_id).all()
    return {
        "locations": [loc.name for loc in locs],
        "entries_2026_by_month_status": [list(r) for r in by_month],
        "entries_per_location_latest": [list(r) for r in per_loc],
        "categories": [f"{c.name} ({len(c.data_points)})" for c in cats],
        "targets": sorted(f"{k}:{s}" for k, s in targets),
    }


def seed(db: Session, admin_email: str, live_months: list[date], scope3_start: date, max_rows: int = 900) -> dict:
    user, current = _acting_admin(db, admin_email)
    tenant_id = current.tenant_id
    report: dict = {"steps": []}

    _apply_scope3_target_migration(db)
    report["catalogue"] = _ensure_scope3_catalogue(db, tenant_id, user.id)

    locations = db.query(Location).filter(Location.tenant_id == tenant_id).order_by(Location.name).all()
    budget = max_rows

    for loc in locations:
        if budget <= 0:
            break
        rows = _live_rows_for_location(db, tenant_id, loc, live_months)[:budget]
        res = _import(db, current, loc.id, rows)
        budget -= len(rows)
        report["steps"].append({"location": loc.name, "job": "live months", "rows": len(rows), **res})

    # Scope 3 runs after the live months so September/October production,
    # electricity and waste exist to drive it.
    prod_avgs: dict[uuid.UUID, float] = {}
    prod_dp = (
        db.query(DataPoint).join(Category, Category.id == DataPoint.category_id)
        .filter(Category.tenant_id == tenant_id, DataPoint.name == "Battery Production Volume").first()
    )
    if prod_dp is not None:
        for loc in locations:
            vals = _approved_series(db, loc.id, [prod_dp.id]).get(prod_dp.id, {})
            if vals:
                prod_avgs[loc.id] = sum(vals.values()) / len(vals)
    reference = max(prod_avgs.values(), default=0) or 1
    scope3_months = months_in_range(scope3_start, live_months[-1])
    for loc in locations:
        if budget <= 0:
            break
        if loc.id not in prod_avgs:
            continue
        rows = _scope3_rows_for_location(db, tenant_id, loc, scope3_months, prod_avgs[loc.id] / reference)[:budget]
        res = _import(db, current, loc.id, rows)
        budget -= len(rows)
        report["steps"].append({"location": loc.name, "job": "scope 3", "rows": len(rows), **res})

    report["complete"] = budget > 0
    if report["complete"]:
        report["scope3_target"] = _ensure_scope3_target(db, current)
    return report
