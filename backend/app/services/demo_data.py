"""Generates the three sample .xlsx workbooks behind Settings -> Approval
Settings -> Simulate Sample: entries (a real time series, Aug 2024 - Aug
2026), emission factors (just enough to backfill the years the entries
workbook needs), and targets (one row per targetable metric). Each is
built to upload cleanly through the existing Bulk Upload flows as-is --
no invented substances, no column shapes those flows don't already
understand.

Values in the entries workbook are informed by the real Aug 2026 figures
already in this tenant (production ~35 MnAh, revenue ~125 Cr, water/waste
categories, etc.), interpolated back to a smaller Aug 2024 starting point
with a mild improving trend where a sustainability narrative makes sense
-- waste recycled up, landfill down, renewable % up, safety incidents
down, training up. Not real measurements; a plausible story for a demo.
"""

import io
import math
import random
import uuid
from datetime import date
from typing import Callable

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from sqlalchemy.orm import Session

from app.db.models import Category, DataPoint, EmissionFactor

# ---- Shared month range -------------------------------------------------

DEMO_START = date(2024, 8, 1)
DEMO_END = date(2026, 8, 1)


def _month_range(start: date, end: date) -> list[date]:
    months = []
    cur = start
    while cur <= end:
        months.append(cur)
        y, m = cur.year, cur.month + 1
        if m == 13:
            y, m = y + 1, 1
        cur = date(y, m, 1)
    return months


DEMO_MONTHS = _month_range(DEMO_START, DEMO_END)
_N = len(DEMO_MONTHS)


def _trend(rng: random.Random, start: float, end: float, i: int, seasonal_pct: float = 0.0, noise_pct: float = 0.05, decimals: int = 2, floor: float = 0.0) -> float:
    """Linear interpolation start->end across the demo range, plus a mild
    seasonal wave and small random noise -- a plausible, non-static series
    instead of a flat or purely random one."""
    base = start + (end - start) * (i / (_N - 1))
    seasonal = 1 + seasonal_pct * math.sin(2 * math.pi * (i % 12) / 12)
    noise = 1 + rng.uniform(-noise_pct, noise_pct)
    value = max(base * seasonal * noise, floor)
    return round(value, decimals)


def _build_generators(rng: random.Random) -> dict[tuple[str, str], Callable[[int], float]]:
    """(category, data_point_name) -> generator(i) -> value. Same
    calibration used for this tenant's earlier historical seed, just
    re-anchored to the wider Aug 2024 - Aug 2026 demo range."""
    t = lambda *a, **kw: _trend(rng, *a, **kw)  # noqa: E731
    return {
        ("Water", "Ground Water Withdrawal"): lambda i: t(650, 855, i, 0.08, 0.06, 1),
        ("Water", "Packaging Drinking Water"): lambda i: t(210, 285, i, 0.05, 0.06, 1),
        ("Water", "Surface Water Withdrawal"): lambda i: t(760, 998, i, 0.08, 0.06, 1),
        ("Water", "Third-Party Water Withdrawal"): lambda i: t(540, 713, i, 0.05, 0.06, 1),

        ("Waste", "Battery Waste — Incinerated"): lambda i: t(0.9, 0.4, i, 0.05, 0.15, 2, 0),
        ("Waste", "Battery Waste — Recycled"): lambda i: t(1.2, 2.8, i, 0.05, 0.12, 2, 0),
        ("Waste", "Battery Waste — Sent to Landfill"): lambda i: t(0.6, 0.2, i, 0.05, 0.2, 2, 0),
        ("Waste", "Biomedical Waste — Incinerated"): lambda i: t(0.15, 0.1, i, 0.1, 0.2, 2, 0),
        ("Waste", "Biomedical Waste — Recycled"): lambda i: t(0.02, 0.05, i, 0.1, 0.3, 2, 0),
        ("Waste", "Biomedical Waste — Sent to Landfill"): lambda i: t(0.05, 0.02, i, 0.1, 0.3, 2, 0),
        ("Waste", "Construction & Demolition Waste — Incinerated"): lambda i: t(0.3, 0.15, i, 0.1, 0.2, 2, 0),
        ("Waste", "Construction & Demolition Waste — Recycled"): lambda i: t(0.8, 1.6, i, 0.1, 0.15, 2, 0),
        ("Waste", "Construction & Demolition Waste — Sent to Landfill"): lambda i: t(1.1, 0.5, i, 0.1, 0.2, 2, 0),
        ("Waste", "E-Waste — Incinerated"): lambda i: t(0.05, 0.02, i, 0.1, 0.3, 2, 0),
        ("Waste", "E-Waste — Recycled"): lambda i: t(0.3, 0.7, i, 0.1, 0.15, 2, 0),
        ("Waste", "E-Waste — Sent to Landfill"): lambda i: t(0.1, 0.03, i, 0.1, 0.3, 2, 0),
        ("Waste", "Hazardous Waste Generated"): lambda i: t(2.2, 1.6, i, 0.08, 0.1, 2, 0),
        ("Waste", "Non-Hazardous Waste Generated"): lambda i: t(3.5, 4.8, i, 0.08, 0.1, 2, 0),
        ("Waste", "Other Hazardous Waste — Incinerated"): lambda i: t(0.4, 0.2, i, 0.1, 0.2, 2, 0),
        ("Waste", "Other Hazardous Waste — Recycled"): lambda i: t(0.5, 1.1, i, 0.1, 0.15, 2, 0),
        ("Waste", "Other Hazardous Waste — Sent to Landfill"): lambda i: t(0.7, 0.3, i, 0.1, 0.2, 2, 0),
        ("Waste", "Plastic Waste — Incinerated"): lambda i: t(0.5, 0.25, i, 0.1, 0.2, 2, 0),
        ("Waste", "Plastic Waste — Recycled"): lambda i: t(0.9, 2.0, i, 0.1, 0.15, 2, 0),
        ("Waste", "Plastic Waste — Sent to Landfill"): lambda i: t(0.8, 0.35, i, 0.1, 0.2, 2, 0),

        ("ETP-Water", "Recycled Water Used for Irrigation"): lambda i: t(60, 110, i, 0.1, 0.1, 1, 0),
        ("ETP-Water", "Recycled Water Used for Process"): lambda i: t(90, 160, i, 0.1, 0.1, 1, 0),
        ("ETP-Water", "Total Treated Effluent Generated"): lambda i: t(180, 260, i, 0.08, 0.1, 1, 0),
        ("STP-Water", "Recycled Water Used for Irrigation"): lambda i: t(40, 75, i, 0.1, 0.1, 1, 0),
        ("STP-Water", "Recycled Water Used for Process"): lambda i: t(30, 55, i, 0.1, 0.1, 1, 0),
        ("STP-Water", "Total Treated Effluent Generated"): lambda i: t(90, 140, i, 0.08, 0.1, 1, 0),

        ("Ozone", "Halon"): lambda i: t(0.5, 0.2, i, 0.1, 0.4, 2, 0),
        ("Ozone", "R-134a"): lambda i: t(3.5, 2.8, i, 0.15, 0.25, 2, 0),
        ("Ozone", "R-22"): lambda i: t(2.0, 0.8, i, 0.15, 0.3, 2, 0),
        ("Ozone", "R-32"): lambda i: t(1.5, 2.2, i, 0.15, 0.25, 2, 0),

        ("Air Emissions", "Coal Consumed"): lambda i: t(120, 40, i, 0.1, 0.2, 1, 0),
        ("Air Emissions", "Diesel Consumed"): lambda i: t(420, 300, i, 0.1, 0.15, 1, 0),
        ("Air Emissions", "Grid Electricity Consumed"): lambda i: t(58000, 78000, i, 0.1, 0.08, 0, 0),
        ("Air Emissions", "LPG Consumed"): lambda i: t(180, 140, i, 0.1, 0.15, 1, 0),
        ("Air Emissions", "Petrol Consumed"): lambda i: t(90, 65, i, 0.1, 0.2, 1, 0),
        ("Air Emissions", "Refrigerant Leakage — Halon"): lambda i: t(0.3, 0.1, i, 0.1, 0.4, 2, 0),
        ("Air Emissions", "Refrigerant Leakage — R-134a"): lambda i: t(3.0, 2.5, i, 0.15, 0.25, 2, 0),
        ("Air Emissions", "Refrigerant Leakage — R-22"): lambda i: t(1.8, 0.7, i, 0.15, 0.3, 2, 0),
        ("Air Emissions", "Refrigerant Leakage — R-32"): lambda i: t(1.0, 1.5, i, 0.15, 0.25, 2, 0),
        ("Air Emissions", "Renewable / PPA-Covered Percentage"): lambda i: min(t(8, 38, i, 0.05, 0.1, 1, 0), 100),

        ("Business Performance", "Revenue"): lambda i: t(88, 125, i, 0.06, 0.05, 2, 1),

        ("Safety", "Defensive Driving Training"): lambda i: min(t(58, 92, i, 0.03, 0.06, 1, 0), 100),
        ("Safety", "Fatality"): lambda i: 0,
        ("Safety", "LTIFR"): lambda i: t(0.85, 0.35, i, 0.1, 0.2, 4, 0),
        ("Safety", "Near Miss"): lambda i: round(t(9, 4, i, 0.1, 0.3, 0, 0)),
        ("Safety", "Unsafe Conditions"): lambda i: round(t(7, 2, i, 0.1, 0.3, 0, 0)),

        ("Production", "Battery Production Volume"): lambda i: t(27, 35, i, 0.06, 0.05, 1, 1),
    }


SKIP_DATA_POINTS = {("Effluent Monitoring", "pH"), ("Effluent Monitoring", "BOD"), ("Effluent Monitoring", "COD")}

_HEADER_FONT = Font(bold=True, color="FFFFFF")
_HEADER_FILL = PatternFill("solid", fgColor="0E2C21")


def _style_header(ws, ncols: int) -> None:
    for col in range(1, ncols + 1):
        cell = ws.cell(row=1, column=col)
        cell.font = _HEADER_FONT
        cell.fill = _HEADER_FILL


def build_entries_workbook(db: Session, tenant_id) -> bytes:
    """One row per (month, category, data point) -- a real time series,
    matching how the portal itself thinks about periods, not one wide row
    per month. Year and Month are separate columns, same shape the
    downloadable template now uses."""
    categories = db.query(Category).filter(Category.tenant_id == tenant_id).order_by(Category.display_order, Category.name).all()
    rng = random.Random(42)
    generators = _build_generators(rng)

    wb = Workbook()
    ws = wb.active
    ws.title = "Entries"
    headers = ["category", "data_point_name", "value", "unit", "note", "year", "month"]
    ws.append(headers)
    _style_header(ws, len(headers))

    for i, month in enumerate(DEMO_MONTHS):
        for cat in categories:
            for dp in cat.data_points:
                key = (cat.name, dp.name)
                if key in SKIP_DATA_POINTS:
                    continue
                gen = generators.get(key)
                if gen is None:
                    continue
                value = gen(i)
                ws.append([cat.name, dp.name, value, dp.unit or "", "Demo data — sample workbook", month.year, month.month])

    for col, width in zip("ABCDEFG", [16, 34, 12, 10, 26, 8, 8]):
        ws.column_dimensions[col].width = width

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def demo_entry_rows(db: Session, tenant_id) -> list[dict]:
    """Same rows as build_entries_workbook(), as plain dicts instead of an
    xlsx sheet -- feeds the one-click "populate all" endpoint directly
    instead of a download-then-reupload round trip. Deliberately not
    factored to share code with build_entries_workbook() (some duplication
    of the same simple loop) so the already-verified xlsx path stays
    untouched by this."""
    categories = db.query(Category).filter(Category.tenant_id == tenant_id).order_by(Category.display_order, Category.name).all()
    rng = random.Random(42)
    generators = _build_generators(rng)
    rows: list[dict] = []
    for i, month in enumerate(DEMO_MONTHS):
        for cat in categories:
            for dp in cat.data_points:
                key = (cat.name, dp.name)
                if key in SKIP_DATA_POINTS:
                    continue
                gen = generators.get(key)
                if gen is None:
                    continue
                rows.append(
                    {
                        "category": cat.name,
                        "data_point_name": dp.name,
                        "value": gen(i),
                        "unit": dp.unit or "",
                        "note": "Demo data — sample workbook",
                        "year": month.year,
                        "month": month.month,
                    }
                )
    return rows


# ---- Emission factors ---------------------------------------------------

# Backfills FY2024 so the entries workbook's Aug-Dec 2024 rows have a
# factor to resolve against -- this tenant's real factor library starts
# at FY2025/FY2026 (see resolve_factor()'s "latest at-or-before" rule),
# so without this, only the 2025-2026 portion of the demo would calculate.
# gas_type strings match carbon_mapping.py's ipcc_substance exactly, and
# the values themselves are simply carried back from the tenant's own
# existing FY26 factors -- not invented.
_SCOPE1_FACTORS = [
    # (substance, unit, source, source_reference, fy24, fy25, fy26)
    ("Diesel", "kg CO2e/litre", "Amara Raja GHG Inventory", "GHG_Inventory_FY26_AREM, Scope-1 tab", 2.697, 2.697, 2.697),
    ("Petrol", "litre", "Amara Raja GHG Inventory", "GHG_Inventory_FY26_AREM, Scope-1 tab", 2.3099, 2.3099, 2.3099),
    ("Liquefied Petroleum Gas", "kg CO2e/kg", "Amara Raja GHG Inventory", "GHG_Inventory_FY26_AREM, Scope-1 tab", 2.94, 2.94, 2.94),
    ("Coal", "tCO2e/t", "Manual", "Manual", 0.25, 0.25, 0.25),
    ("R-134a", "GWP-100", "Amara Raja GHG Inventory", "GHG_Inventory_FY26_AREM, Scope-1 tab, IPCC AR6 Aug 2024 revision", 1530, 1530, 1530),
    ("R-22", "GWP-100", "Amara Raja GHG Inventory", "GHG_Inventory_FY26_AREM, Scope-1 tab, IPCC AR6 Aug 2024 revision", 1760, 1760, 1760),
    ("R-32", "GWP-100", "Amara Raja GHG Inventory", "GHG_Inventory_FY26_AREM, Scope-1 tab, IPCC AR6 Aug 2024 revision", 677, 677, 677),
]

_SCOPE2_FACTORS = [
    # (substance, method, unit, source, source_reference, fy24, fy25, fy26)
    ("Grid Electricity", "location-based", "t CO2e/MWh", "Amara Raja GHG Inventory", "GHG_Inventory_FY26_AREM, Scope-2 tab, CEA V21 (FY2024-25)", 0.727, 0.727, 0.71),
]


def build_emission_factors_workbook() -> bytes:
    """Scope 1 and Scope 2 tabs, wide FY columns -- the exact shape the
    existing bulk-detect classifier already recognizes (sheet name ->
    scope, "FY2024"/"FY2025"/"FY2026" headers -> one factor row pivoted
    into three effective-year versions)."""
    wb = Workbook()

    ws1 = wb.active
    ws1.title = "Scope 1"
    headers1 = ["Substance", "Unit", "Source", "Source Reference", "FY2024", "FY2025", "FY2026"]
    ws1.append(headers1)
    _style_header(ws1, len(headers1))
    for name, unit, source, ref, fy24, fy25, fy26 in _SCOPE1_FACTORS:
        ws1.append([name, unit, source, ref, fy24, fy25, fy26])
    for col, width in zip("ABCDEFG", [22, 16, 26, 46, 10, 10, 10]):
        ws1.column_dimensions[col].width = width

    ws2 = wb.create_sheet("Scope 2")
    headers2 = ["Substance", "Method", "Unit", "Source", "Source Reference", "FY2024", "FY2025", "FY2026"]
    ws2.append(headers2)
    _style_header(ws2, len(headers2))
    for name, method, unit, source, ref, fy24, fy25, fy26 in _SCOPE2_FACTORS:
        ws2.append([name, method, unit, source, ref, fy24, fy25, fy26])
    for col, width in zip("ABCDEFGH", [18, 16, 12, 26, 46, 10, 10, 10]):
        ws2.column_dimensions[col].width = width

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def ensure_demo_emission_factors(db: Session, tenant_id: uuid.UUID, actor_id: uuid.UUID | None) -> int:
    """Idempotently upserts the same Scope 1/2 factors as
    build_emission_factors_workbook() directly into the tenant's factor
    table (FY2024/2025/2026 rows), instead of relying on a human to
    remember to download that workbook and run it through the Emission
    Factors bulk-upload before uploading demo entries.

    Without this, a Coal/Diesel/Petrol/... entry uploaded directly (e.g.
    via Data Entry -> Bulk Upload, skipping the Simulate Sample ordering)
    has nothing to resolve against and lands "unresolved: missing_factor"
    -- this was a real, repeated support issue, not a hypothetical. Called
    from both /admin/demo/clear and /admin/demo/entries-workbook so the
    factors exist no matter which step a demo run starts from. Matches
    existing rows by (scope, gas_type or method, effective_date) so
    re-running never duplicates a tenant's own factor library.

    Returns the number of rows created."""
    existing = (
        db.query(EmissionFactor.scope, EmissionFactor.gas_type, EmissionFactor.method, EmissionFactor.effective_date)
        .filter(EmissionFactor.tenant_id == tenant_id, EmissionFactor.scope.in_([1, 2]))
        .all()
    )
    existing_keys = {(scope, (gas_type or method or "").strip().lower(), eff_date) for scope, gas_type, method, eff_date in existing}

    created = 0
    for name, unit, source, ref, fy24, fy25, fy26 in _SCOPE1_FACTORS:
        for year, value in ((2024, fy24), (2025, fy25), (2026, fy26)):
            eff_date = date(year, 1, 1)
            key = (1, name.strip().lower(), eff_date)
            if key in existing_keys:
                continue
            db.add(
                EmissionFactor(
                    tenant_id=tenant_id,
                    scope=1,
                    gas_type=name,
                    unit=unit,
                    factor_value=value,
                    effective_date=eff_date,
                    version=f"FY{str(year)[2:]}",
                    source=source,
                    source_reference=ref,
                    created_by=actor_id,
                )
            )
            created += 1

    for name, method, unit, source, ref, fy24, fy25, fy26 in _SCOPE2_FACTORS:
        for year, value in ((2024, fy24), (2025, fy25), (2026, fy26)):
            eff_date = date(year, 1, 1)
            key = (2, method.strip().lower(), eff_date)
            if key in existing_keys:
                continue
            db.add(
                EmissionFactor(
                    tenant_id=tenant_id,
                    scope=2,
                    method=method,
                    description=name,
                    unit=unit,
                    factor_value=value,
                    effective_date=eff_date,
                    version=f"FY{str(year)[2:]}",
                    source=source,
                    source_reference=ref,
                    created_by=actor_id,
                )
            )
            created += 1

    return created


# ---- Targets --------------------------------------------------------

_TARGET_METRIC_ORDER = [
    "scope1_tco2e", "scope2_tco2e", "scope1_2_tco2e",
    "ghg_intensity_production", "energy_per_production", "water_per_production", "waste_per_production",
    "ghg_per_revenue", "energy_per_revenue", "water_per_revenue", "waste_per_revenue",
]


def build_targets_workbook() -> bytes:
    """One row per targetable metric, org-wide, baseline = calendar 2025
    (fully inside the entries demo range) and target = calendar 2026 at a
    flat 10% reduction -- uploads straight into the new /targets/bulk-import
    endpoint."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Targets"
    headers = [
        "metric_key", "location_name", "baseline_period_start", "baseline_period_end",
        "target_period_start", "target_period_end", "reduction_percentage", "rationale",
    ]
    ws.append(headers)
    _style_header(ws, len(headers))

    for metric_key in _TARGET_METRIC_ORDER:
        ws.append([
            metric_key, "", "2025-01-01", "2025-12-01", "2026-01-01", "2026-12-01",
            10.0, "Demo target — 10% reduction from the FY25 baseline.",
        ])

    for col, width in zip("ABCDEFGH", [26, 16, 18, 18, 18, 18, 18, 42]):
        ws.column_dimensions[col].width = width

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def demo_target_rows() -> list[dict]:
    """Same rows as build_targets_workbook(), as plain dicts -- see
    demo_entry_rows() for why this isn't factored to share code with the
    xlsx builder."""
    return [
        {
            "metric_key": metric_key,
            "location_name": None,
            "baseline_period_start": "2025-01-01",
            "baseline_period_end": "2025-12-01",
            "target_period_start": "2026-01-01",
            "target_period_end": "2026-12-01",
            "reduction_percentage": 10.0,
            "rationale": "Demo target — 10% reduction from the FY25 baseline.",
        }
        for metric_key in _TARGET_METRIC_ORDER
    ]
