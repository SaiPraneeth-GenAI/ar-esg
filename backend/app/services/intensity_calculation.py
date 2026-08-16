"""Energy/Water/Waste/GHG intensity by production volume and by revenue --
the four "Sp X per battery production" / "Sp X per revenue" rows the
reference ESG report tracks. Reuses compute_period_totals for GHG and
production (same approved-snapshot totals the carbon dashboard shows, so
these numbers never drift out of sync with it) and adds three new
Decimal-safe, None-propagating readers: energy (derived from the same
approved fuel/electricity activity data GHG already uses, via IPCC NCV --
never a separately-entered, independently-driftable number), water/waste
(approved entries for those categories), and revenue (config-mapped, same
shape as ProductionVolumeMapping).
"""

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.carbon_mapping import CARBON_SOURCE_MAPPING
from app.db.models import Category, DataPoint, Entry, IpccReference, RevenueMapping
from app.services.carbon_calculation import compute_period_totals, to_decimal

MJ_PER_KWH = Decimal("3.6")


def _entry_unit_basis(unit: str) -> str | None:
    u = unit.strip().lower()
    if u in ("litre", "litres", "l"):
        return "litre"
    if u == "kg":
        return "kg"
    return None


def fuel_energy_mj(
    activity_value: Decimal, activity_unit: str, ncv_mj_per_unit: Decimal, density_kg_per_unit: Decimal | None
) -> Decimal | None:
    """NCV is defined per kg (mass basis). A litre-recorded fuel needs its
    density on file to convert; without one, this fuel's contribution is
    left out of the energy total rather than guessed (same discipline as
    the GHG engine's unit_mismatch handling)."""
    basis = _entry_unit_basis(activity_unit)
    if basis is None:
        return None
    if basis == "kg":
        kg = activity_value
    else:
        if density_kg_per_unit is None:
            return None
        kg = activity_value * density_kg_per_unit
    return kg * ncv_mj_per_unit


def compute_energy_gj(db: Session, tenant_id: uuid.UUID, location_id: uuid.UUID | None, period: date) -> Decimal | None:
    """Total energy consumption, derived from the same approved fuel and
    grid-electricity activity entries the GHG calculation already reads --
    not a separately entered number that could drift from what Scope 1/2
    actually saw. Returns None when there is no approved fuel/electricity
    activity at all this period (never a fabricated zero)."""
    total_mj = Decimal("0")
    has_any = False

    for dp_name, mapping in CARBON_SOURCE_MAPPING.items():
        if mapping.source_type not in ("fuel", "grid_electricity"):
            continue

        dp = (
            db.query(DataPoint)
            .join(Category, Category.id == DataPoint.category_id)
            .filter(Category.tenant_id == tenant_id, DataPoint.name == dp_name)
            .first()
        )
        if dp is None:
            continue

        q = db.query(Entry).filter(Entry.data_point_id == dp.id, Entry.status == "Approved", Entry.period == period)
        if location_id is not None:
            q = q.filter(Entry.location_id == location_id)
        entries = q.all()
        if not entries:
            continue

        activity_sum = sum((to_decimal(e.value) for e in entries if e.value is not None), Decimal("0"))

        if mapping.source_type == "grid_electricity":
            total_mj += activity_sum * MJ_PER_KWH
            has_any = True
            continue

        ref = (
            db.query(IpccReference)
            .filter(IpccReference.substance_name == mapping.ipcc_substance, IpccReference.factor_type == "fuel")
            .first()
        )
        if ref is None or ref.ncv_mj_per_unit is None:
            # e.g. Coal -- no NCV on file. Excluded from the energy total,
            # same as it's excluded from GHG (stays unresolved there too).
            continue

        density = to_decimal(ref.density_kg_per_unit) if ref.density_kg_per_unit is not None else None
        mj = fuel_energy_mj(activity_sum, dp.unit or mapping.expected_unit, to_decimal(ref.ncv_mj_per_unit), density)
        if mj is not None:
            total_mj += mj
            has_any = True

    if not has_any:
        return None
    return total_mj / Decimal("1000")


def compute_category_total(
    db: Session, tenant_id: uuid.UUID, location_id: uuid.UUID | None, period: date, category_name: str
) -> Decimal | None:
    """Decimal-safe sum of approved activity for every data point under one
    category (e.g. all four Water data points). None when the category has
    no approved entries this period -- not a fabricated zero."""
    dp_ids = [
        dp.id
        for dp in (
            db.query(DataPoint)
            .join(Category, Category.id == DataPoint.category_id)
            .filter(Category.tenant_id == tenant_id, Category.name == category_name)
            .all()
        )
    ]
    if not dp_ids:
        return None

    q = db.query(Entry).filter(Entry.data_point_id.in_(dp_ids), Entry.status == "Approved", Entry.period == period)
    if location_id is not None:
        q = q.filter(Entry.location_id == location_id)
    entries = q.all()
    if not entries:
        return None
    return sum((to_decimal(e.value) for e in entries if e.value is not None), Decimal("0"))


def get_active_revenue_mapping(db: Session, tenant_id: uuid.UUID, location_id: uuid.UUID | None) -> RevenueMapping | None:
    q = db.query(RevenueMapping).filter(RevenueMapping.tenant_id == tenant_id, RevenueMapping.is_active.is_(True))
    if location_id is not None:
        q = q.filter((RevenueMapping.location_id == location_id) | (RevenueMapping.location_id.is_(None)))
    return q.first()


def compute_revenue(db: Session, tenant_id: uuid.UUID, location_id: uuid.UUID | None, period: date) -> Decimal | None:
    mapping = get_active_revenue_mapping(db, tenant_id, location_id)
    if mapping is None:
        return None
    q = db.query(Entry).filter(Entry.data_point_id == mapping.data_point_id, Entry.status == "Approved", Entry.period == period)
    if location_id is not None:
        q = q.filter(Entry.location_id == location_id)
    entries = q.all()
    if not entries:
        return None
    total_native = sum((to_decimal(e.value) for e in entries if e.value is not None), Decimal("0"))
    return total_native * to_decimal(mapping.conversion_multiplier)


def ratio(numerator, denominator) -> float | None:
    """Never divides when either side is missing or the denominator is
    zero -- an actionable 'data required' state instead of a fabricated
    number (rule against invented numbers, applied to every intensity
    metric, not just GHG)."""
    if numerator is None or denominator is None:
        return None
    d = to_decimal(denominator)
    if d == 0:
        return None
    return float(to_decimal(numerator) / d)


@dataclass
class IntensityOverview:
    period: date
    energy_gj: float | None
    ghg_tco2e: float | None
    water_kl: float | None
    waste_mt: float | None
    production_mnah: float | None
    revenue_inr_cr: float | None
    energy_per_production: float | None
    ghg_per_production: float | None
    water_per_production: float | None
    waste_per_production: float | None
    energy_per_revenue: float | None
    ghg_per_revenue: float | None
    water_per_revenue: float | None
    waste_per_revenue: float | None


def compute_intensity_overview(
    db: Session, tenant_id: uuid.UUID, location_id: uuid.UUID | None, period: date
) -> IntensityOverview:
    ghg_totals = compute_period_totals(db, tenant_id, location_id, period)
    ghg_tco2e = ghg_totals["scope1_2_loc_tco2e"]
    production_mnah = ghg_totals["production_value"]

    energy_gj = compute_energy_gj(db, tenant_id, location_id, period)
    water_kl = compute_category_total(db, tenant_id, location_id, period, "Water")
    waste_mt = compute_category_total(db, tenant_id, location_id, period, "Waste")
    revenue_cr = compute_revenue(db, tenant_id, location_id, period)

    return IntensityOverview(
        period=period,
        energy_gj=float(energy_gj) if energy_gj is not None else None,
        ghg_tco2e=ghg_tco2e,
        water_kl=float(water_kl) if water_kl is not None else None,
        waste_mt=float(waste_mt) if waste_mt is not None else None,
        production_mnah=production_mnah,
        revenue_inr_cr=float(revenue_cr) if revenue_cr is not None else None,
        energy_per_production=ratio(energy_gj, production_mnah),
        ghg_per_production=ratio(ghg_tco2e, production_mnah),
        water_per_production=ratio(water_kl, production_mnah),
        waste_per_production=ratio(waste_mt, production_mnah),
        energy_per_revenue=ratio(energy_gj, revenue_cr),
        ghg_per_revenue=ratio(ghg_tco2e, revenue_cr),
        water_per_revenue=ratio(water_kl, revenue_cr),
        waste_per_revenue=ratio(waste_mt, revenue_cr),
    )
