"""Energy/Water/Waste/GHG intensity by production volume and by revenue --
the four "Sp X per battery production" / "Sp X per revenue" rows the
reference ESG report tracks. Reuses compute_period_totals_batch for GHG and
production (same approved-snapshot totals the carbon dashboard shows, so
these numbers never drift out of sync with it) and adds three new
Decimal-safe, None-propagating readers: energy (derived from the same
approved fuel/electricity activity data GHG already uses, via IPCC NCV --
never a separately-entered, independently-driftable number), water/waste
(approved entries for those categories), and revenue (config-mapped, same
shape as ProductionVolumeMapping).

Every reader has a *_batch(periods) form computing N periods in a fixed
number of queries, with the single-period form as a thin wrapper -- the
same pattern as compute_period_totals/compute_period_totals_batch. This
matters here specifically: a dashboard load calls this for the current
period, the prior month, and the prior year, and the trend chart calls it
for 6+ periods at once, so an unbatched per-period query cost multiplies
fast.
"""

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.carbon_mapping import CARBON_SOURCE_MAPPING
from app.db.models import Category, DataPoint, Entry, IpccReference, RevenueMapping
from app.services.carbon_calculation import compute_period_totals_batch, to_decimal

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
    return compute_energy_gj_batch(db, tenant_id, location_id, [period])[period]


def compute_energy_gj_batch(
    db: Session, tenant_id: uuid.UUID, location_id: uuid.UUID | None, periods: list[date]
) -> dict[date, Decimal | None]:
    """Total energy consumption per period, derived from the same approved
    fuel and grid-electricity activity entries the GHG calculation already
    reads. None for a period with no approved fuel/electricity activity at
    all (never a fabricated zero). Three fixed queries regardless of how
    many periods -- not one DataPoint/Entry/IpccReference lookup per source
    per period."""
    if not periods:
        return {}

    energy_dp_names = [name for name, m in CARBON_SOURCE_MAPPING.items() if m.source_type in ("fuel", "grid_electricity")]

    data_points = (
        db.query(DataPoint)
        .join(Category, Category.id == DataPoint.category_id)
        .filter(Category.tenant_id == tenant_id, DataPoint.name.in_(energy_dp_names))
        .all()
    )
    dp_by_name = {dp.name: dp for dp in data_points}
    if not dp_by_name:
        return {p: None for p in periods}

    entry_q = db.query(Entry).filter(
        Entry.data_point_id.in_([dp.id for dp in data_points]), Entry.status == "Approved", Entry.period.in_(periods)
    )
    if location_id is not None:
        entry_q = entry_q.filter(Entry.location_id == location_id)
    entries_by_dp_period: dict[tuple, list] = {}
    for e in entry_q.all():
        entries_by_dp_period.setdefault((e.data_point_id, e.period), []).append(e)

    fuel_substances = [m.ipcc_substance for m in CARBON_SOURCE_MAPPING.values() if m.source_type == "fuel"]
    fuel_refs = (
        db.query(IpccReference)
        .filter(IpccReference.substance_name.in_(fuel_substances), IpccReference.factor_type == "fuel")
        .all()
    )
    ref_by_substance = {r.substance_name: r for r in fuel_refs}

    result: dict[date, Decimal | None] = {}
    for period in periods:
        total_mj = Decimal("0")
        has_any = False

        for dp_name, mapping in CARBON_SOURCE_MAPPING.items():
            if mapping.source_type not in ("fuel", "grid_electricity"):
                continue
            dp = dp_by_name.get(dp_name)
            if dp is None:
                continue
            entries = entries_by_dp_period.get((dp.id, period))
            if not entries:
                continue

            activity_sum = sum((to_decimal(e.value) for e in entries if e.value is not None), Decimal("0"))

            if mapping.source_type == "grid_electricity":
                total_mj += activity_sum * MJ_PER_KWH
                has_any = True
                continue

            ref = ref_by_substance.get(mapping.ipcc_substance)
            if ref is None or ref.ncv_mj_per_unit is None:
                # e.g. Coal -- no NCV on file. Excluded from the energy
                # total, same as it's excluded from GHG (stays unresolved
                # there too).
                continue

            density = to_decimal(ref.density_kg_per_unit) if ref.density_kg_per_unit is not None else None
            mj = fuel_energy_mj(activity_sum, dp.unit or mapping.expected_unit, to_decimal(ref.ncv_mj_per_unit), density)
            if mj is not None:
                total_mj += mj
                has_any = True

        result[period] = (total_mj / Decimal("1000")) if has_any else None
    return result


def compute_category_total(
    db: Session, tenant_id: uuid.UUID, location_id: uuid.UUID | None, period: date, category_name: str
) -> Decimal | None:
    return compute_category_total_batch(db, tenant_id, location_id, [period], category_name)[period]


def compute_category_total_batch(
    db: Session, tenant_id: uuid.UUID, location_id: uuid.UUID | None, periods: list[date], category_name: str
) -> dict[date, Decimal | None]:
    """Decimal-safe sum of approved activity for every data point under one
    category (e.g. all four Water data points), per period. None for a
    period with no approved entries in this category -- not a fabricated
    zero. Two fixed queries regardless of period count."""
    if not periods:
        return {}

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
        return {p: None for p in periods}

    q = db.query(Entry).filter(Entry.data_point_id.in_(dp_ids), Entry.status == "Approved", Entry.period.in_(periods))
    if location_id is not None:
        q = q.filter(Entry.location_id == location_id)
    entries_by_period: dict[date, list] = {}
    for e in q.all():
        entries_by_period.setdefault(e.period, []).append(e)

    return {
        p: (
            sum((to_decimal(e.value) for e in entries_by_period[p] if e.value is not None), Decimal("0"))
            if p in entries_by_period
            else None
        )
        for p in periods
    }


def get_active_revenue_mapping(db: Session, tenant_id: uuid.UUID, location_id: uuid.UUID | None) -> RevenueMapping | None:
    q = db.query(RevenueMapping).filter(RevenueMapping.tenant_id == tenant_id, RevenueMapping.is_active.is_(True))
    if location_id is not None:
        q = q.filter((RevenueMapping.location_id == location_id) | (RevenueMapping.location_id.is_(None)))
    return q.first()


def compute_revenue(db: Session, tenant_id: uuid.UUID, location_id: uuid.UUID | None, period: date) -> Decimal | None:
    return compute_revenue_batch(db, tenant_id, location_id, [period])[period]


def compute_revenue_batch(
    db: Session, tenant_id: uuid.UUID, location_id: uuid.UUID | None, periods: list[date]
) -> dict[date, Decimal | None]:
    if not periods:
        return {}

    mapping = get_active_revenue_mapping(db, tenant_id, location_id)
    if mapping is None:
        return {p: None for p in periods}

    q = db.query(Entry).filter(
        Entry.data_point_id == mapping.data_point_id, Entry.status == "Approved", Entry.period.in_(periods)
    )
    if location_id is not None:
        q = q.filter(Entry.location_id == location_id)
    entries_by_period: dict[date, list] = {}
    for e in q.all():
        entries_by_period.setdefault(e.period, []).append(e)

    result: dict[date, Decimal | None] = {}
    for p in periods:
        entries = entries_by_period.get(p)
        if not entries:
            result[p] = None
            continue
        total_native = sum((to_decimal(e.value) for e in entries if e.value is not None), Decimal("0"))
        result[p] = total_native * to_decimal(mapping.conversion_multiplier)
    return result


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
    return compute_intensity_overview_batch(db, tenant_id, location_id, [period])[period]


def compute_intensity_overview_batch(
    db: Session, tenant_id: uuid.UUID, location_id: uuid.UUID | None, periods: list[date]
) -> dict[date, IntensityOverview]:
    """N periods (e.g. current/prior-month/prior-year, or a 6-month trend)
    in one fixed set of batched queries -- 4 (GHG+production) + 3 (energy)
    + 2 (water) + 2 (waste) + 2 (revenue) = 13 queries total, regardless of
    how many periods are requested, versus 13*N unbatched."""
    if not periods:
        return {}

    ghg_totals = compute_period_totals_batch(db, tenant_id, location_id, periods)
    energy_by_period = compute_energy_gj_batch(db, tenant_id, location_id, periods)
    water_by_period = compute_category_total_batch(db, tenant_id, location_id, periods, "Water")
    waste_by_period = compute_category_total_batch(db, tenant_id, location_id, periods, "Waste")
    revenue_by_period = compute_revenue_batch(db, tenant_id, location_id, periods)

    result: dict[date, IntensityOverview] = {}
    for period in periods:
        ghg_tco2e = ghg_totals[period]["scope1_2_loc_tco2e"]
        production_mnah = ghg_totals[period]["production_value"]
        energy_gj = energy_by_period[period]
        water_kl = water_by_period[period]
        waste_mt = waste_by_period[period]
        revenue_cr = revenue_by_period[period]

        result[period] = IntensityOverview(
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
    return result


def _sum_optional(values: list[float | None]) -> float | None:
    present = [v for v in values if v is not None]
    return sum(present) if present else None


def compute_intensity_overview_range(
    db: Session,
    tenant_id: uuid.UUID,
    location_id: uuid.UUID | None,
    months: list[date],
    by_month: dict[date, "IntensityOverview"] | None = None,
) -> IntensityOverview:
    """Aggregates compute_intensity_overview_batch's per-month results
    across a range (quarter-to-date / year-to-date): every absolute sums
    across the months present, and every ratio is recomputed from those
    summed absolutes -- never averaged from the monthly ratios, which
    would misweight months with different production/revenue volume. Pass
    an already-fetched by_month to skip the internal query, the same way
    compute_range_totals does -- a trend chart computing several buckets
    shares one batched fetch instead of one round trip per bucket."""
    if by_month is None:
        by_month = compute_intensity_overview_batch(db, tenant_id, location_id, months)

    energy_gj = _sum_optional([by_month[m].energy_gj for m in months])
    ghg_tco2e = _sum_optional([by_month[m].ghg_tco2e for m in months])
    water_kl = _sum_optional([by_month[m].water_kl for m in months])
    waste_mt = _sum_optional([by_month[m].waste_mt for m in months])
    production_mnah = _sum_optional([by_month[m].production_mnah for m in months])
    revenue_inr_cr = _sum_optional([by_month[m].revenue_inr_cr for m in months])

    return IntensityOverview(
        period=months[-1],
        energy_gj=energy_gj,
        ghg_tco2e=ghg_tco2e,
        water_kl=water_kl,
        waste_mt=waste_mt,
        production_mnah=production_mnah,
        revenue_inr_cr=revenue_inr_cr,
        energy_per_production=ratio(energy_gj, production_mnah),
        ghg_per_production=ratio(ghg_tco2e, production_mnah),
        water_per_production=ratio(water_kl, production_mnah),
        waste_per_production=ratio(waste_mt, production_mnah),
        energy_per_revenue=ratio(energy_gj, revenue_inr_cr),
        ghg_per_revenue=ratio(ghg_tco2e, revenue_inr_cr),
        water_per_revenue=ratio(water_kl, revenue_inr_cr),
        waste_per_revenue=ratio(waste_mt, revenue_inr_cr),
    )
