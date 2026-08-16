"""Full reseed of the read-only ipcc_reference table with the verified
dataset from Amara Raja's GHG_Inventory_FY26 workbook cross-check (Prompt
3f) -- replaces the earlier, more generic seed entirely rather than merging
with it, since this dataset supersedes it substance by substance.

PROVENANCE NOTE: two rows don't reproduce cleanly from their own listed
NCV/CO2-EF/oxidation/density components (Diesel's components multiply out
to ~3.33 kg CO2e/kg before density, ~2.77 kg CO2e/L after -- not the listed
2.675; Acetylene's components multiply out to ~5.27 kg CO2e/kg, not the
listed 3.889). The component fields are stored as given for the breakdown
display, and `derived_factor_value` is stored as the literal number
specified, since that's the number meant to actually be used -- but the
mismatch means the on-screen "breakdown" for those two rows won't visibly
re-derive its own total. Also note R-32's AR5 and AR6 (Aug 2024) rows are
listed with the identical GWP (677) -- kept as given, not assumed to be a
copy/paste error.

This script is destructive on ipcc_reference (full delete + reinsert) --
safe because it's read-only reference data with no direct dependents;
emission_factor.ipcc_reference_key is ON DELETE SET NULL.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.models import IpccReference  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402

IPCC_2006_SOURCE = "IPCC 2006 Guidelines for National Greenhouse Gas Inventories, Vol 2, Chapter 2"

# substance_name, aliases, ncv, density, co2_ef_per_tj, oxidation, derived_factor_value, unit
FUEL_ROWS = [
    ("Diesel", ["Automotive Diesel Oil", "ADO", "Diesel Oil"], 45.4, 0.832, 74_100, 0.99, 2.675, "kg CO2e/litre"),
    ("Petrol", ["Gasoline", "Automotive Petrol", "Motor Spirit"], 43.5, 0.755, 69_300, 0.99, 2.075, "kg CO2e/litre"),
    ("Liquefied Petroleum Gas", ["LPG", "Propane", "Butane"], 46.3, 0.54, 63_100, 0.995, 2.955, "kg CO2e/kg"),
    ("Acetylene", ["Ethyne"], 49.5, 0.621, 107_000, 0.995, 3.889, "kg CO2e/kg"),
]

GRID_ELECTRICITY_ROWS = [
    # value, publication, effective_year, source_reference
    (0.820, "CEA_V19", 2023, "CEA CO2 Baseline Database V19.0 (FY2022-23)"),
    (0.727, "CEA_V20", 2024, "CEA CO2 Baseline Database V20.0 (FY2023-24)"),
    (0.710, "CEA_V21", 2025, "CEA CO2 Baseline Database V21.0 (FY2024-25), published Nov 2025"),
]
GRID_ELECTRICITY_NAME = "India Grid Electricity (All-India weighted average)"
GRID_ELECTRICITY_ALIASES = ["Grid Electricity", "Grid Power", "Purchased Electricity", "India Grid Electricity"]

AR5_SOURCE = "IPCC AR5 Climate Change 2013 Physical Science Basis"
AR6_AUG2024_SOURCE = "IPCC AR6 Climate Change 2021 Physical Science Basis, revised August 2024"

# substance_name, aliases, [(gwp, publication, year, source_reference), ...]
REFRIGERANT_ROWS = [
    ("R-134a", ["HFC-134a", "1,1,1,2-Tetrafluoroethane"], [
        (1530, "IPCC_AR6_Aug2024", 2024, AR6_AUG2024_SOURCE),
        (1430, "IPCC_AR5", 2013, AR5_SOURCE),
    ]),
    ("R-32", ["Difluoromethane"], [
        (677, "IPCC_AR6_Aug2024", 2024, AR6_AUG2024_SOURCE),
        (677, "IPCC_AR5", 2013, AR5_SOURCE),
    ]),
    ("R-22", ["HCFC-22", "Chlorodifluoromethane"], [
        (1760, "IPCC_AR6_Aug2024", 2024, AR6_AUG2024_SOURCE),
        (1810, "IPCC_AR5", 2013, AR5_SOURCE),
    ]),
    ("R-404A", ["HFC-404A"], [(3942, "IPCC_AR6_Aug2024", 2024, AR6_AUG2024_SOURCE)]),
    ("R-407C", ["HFC-407C"], [(1774, "IPCC_AR6_Aug2024", 2024, AR6_AUG2024_SOURCE)]),
    ("R-410A", ["HFC-410A"], [(2088, "IPCC_AR6_Aug2024", 2024, AR6_AUG2024_SOURCE)]),
]

MONTREAL_SOURCE = "Montreal Protocol Technology and Economic Assessment Panel (TEAP)"
ODP_ROWS = [
    ("Halon 1211", ["BCF", "Bromochlorodifluoromethane"], 3.0),
    ("Halon 1301", ["BTF", "Bromotrifluoromethane"], 10.0),
]

# substance_name, scope3_category, factor_type, value, unit, publication, year, source_reference
SCOPE3_ROWS = [
    ("Purchased Goods and Services", "Purchased Goods & Services", "spend_based", 0.187, "kg CO2e/USD", "DEFRA_2024", 2024, "DEFRA 2024 Greenhouse Gas Conversion Factors (proxy average)"),
    ("Capital Goods", "Capital Goods", "spend_based", 0.241, "kg CO2e/USD", "DEFRA_2024", 2024, "DEFRA 2024 Greenhouse Gas Conversion Factors (proxy average)"),
    ("Fuel and Energy Related Activities", "Fuel and Energy Related Activities", "specific", 0.024, "kg CO2e/MWh", "IPCC_2006", 2006, "IPCC 2006 Guidelines for National Greenhouse Gas Inventories"),
    ("Upstream Transportation and Distribution", "Upstream Transport", "specific", 0.098, "kg CO2e/ton-km", "DEFRA_2024", 2024, "DEFRA 2024 Heavy Goods Vehicle Transport"),
    ("Waste Generated in Operations", "Waste Incineration", "specific", 0.0012, "kg CO2e/ton", "IPCC_2006", 2006, "IPCC 2006 Guidelines, Waste Chapter"),
    ("Waste Generated in Operations", "Landfill Disposal", "specific", 0.193, "kg CO2e/ton", "IPCC_2006", 2006, "IPCC 2006 Guidelines, Waste Chapter (CH4 emissions)"),
    ("Business Travel", "Air Travel", "specific", 0.245, "kg CO2e/km", "DEFRA_2024", 2024, "DEFRA 2024 Greenhouse Gas Conversion Factors, International flights"),
    ("Business Travel", "Rail Travel", "specific", 0.041, "kg CO2e/km", "DEFRA_2024", 2024, "DEFRA 2024 Greenhouse Gas Conversion Factors, National rail"),
    ("Employee Commuting", "Car Commute", "specific", 0.192, "kg CO2e/km", "DEFRA_2024", 2024, "DEFRA 2024 Greenhouse Gas Conversion Factors, average car"),
    ("Upstream Leased Assets", "Leased Building Energy", "specific", 0.210, "kg CO2e/kWh", "CEA_V21", 2025, "CEA CO2 Baseline Database V21.0 (location-based)"),
    ("Downstream Transportation and Distribution", "Downstream Transport", "specific", 0.098, "kg CO2e/ton-km", "DEFRA_2024", 2024, "DEFRA 2024 Heavy Goods Vehicle Transport"),
    ("Use of Sold Products", "Product Use (electricity)", "specific", 0.710, "t CO2e/MWh", "CEA_V21", 2025, "CEA CO2 Baseline Database V21.0 (India grid)"),
    ("End-of-Life Treatment of Sold Products", "Recycling", "specific", 0.045, "kg CO2e/ton", "IPCC_2006", 2006, "IPCC 2006 Guidelines, Waste Chapter"),
    ("Franchises", "Franchised Operations (avg)", "spend_based", 0.187, "kg CO2e/USD", "DEFRA_2024", 2024, "DEFRA 2024 Greenhouse Gas Conversion Factors (proxy average)"),
]


def main() -> None:
    db = SessionLocal()
    try:
        deleted = db.query(IpccReference).delete()
        print(f"removed {deleted} existing ipcc_reference rows")

        rows: list[IpccReference] = []

        for name, aliases, ncv, density, co2_ef, oxidation, value, unit in FUEL_ROWS:
            rows.append(
                IpccReference(
                    substance_name=name,
                    aliases=aliases,
                    scope=1,
                    factor_type="fuel",
                    publication="IPCC_2006_Vol2",
                    effective_year=2006,
                    ncv_mj_per_unit=ncv,
                    density_kg_per_unit=density,
                    co2_ef_per_tj=co2_ef,
                    oxidation_factor=oxidation,
                    derived_factor_value=value,
                    unit=unit,
                    source_reference=IPCC_2006_SOURCE,
                )
            )

        for value, publication, year, source_ref in GRID_ELECTRICITY_ROWS:
            rows.append(
                IpccReference(
                    substance_name=GRID_ELECTRICITY_NAME,
                    aliases=GRID_ELECTRICITY_ALIASES,
                    scope=2,
                    factor_type="grid_electricity",
                    publication=publication,
                    effective_year=year,
                    derived_factor_value=value,
                    unit="t CO2e/MWh",
                    source_reference=source_ref,
                )
            )

        for name, aliases, versions in REFRIGERANT_ROWS:
            for gwp, publication, year, source_ref in versions:
                rows.append(
                    IpccReference(
                        substance_name=name,
                        aliases=aliases,
                        scope=2,
                        factor_type="gwp",
                        publication=publication,
                        effective_year=year,
                        derived_factor_value=gwp,
                        unit="GWP-100",
                        source_reference=source_ref,
                    )
                )

        for name, aliases, odp in ODP_ROWS:
            rows.append(
                IpccReference(
                    substance_name=name,
                    aliases=aliases,
                    scope=1,
                    factor_type="odp",
                    publication="Montreal_Protocol",
                    effective_year=1987,
                    derived_factor_value=odp,
                    unit="ODP tonnes",
                    source_reference=MONTREAL_SOURCE,
                )
            )

        for name, scope3_category, factor_type, value, unit, publication, year, source_ref in SCOPE3_ROWS:
            rows.append(
                IpccReference(
                    substance_name=name,
                    aliases=[scope3_category],
                    scope=3,
                    factor_type=factor_type,
                    scope3_category=scope3_category,
                    publication=publication,
                    effective_year=year,
                    derived_factor_value=value,
                    unit=unit,
                    source_reference=source_ref,
                )
            )

        db.add_all(rows)
        db.commit()
        print(f"inserted {len(rows)} ipcc_reference rows")
    finally:
        db.close()


if __name__ == "__main__":
    main()
