"""Seeds the read-only ipcc_reference table with published emission
factors: IPCC 2006 Guidelines Vol 2 fuel defaults, IPCC AR4/AR5/AR6
refrigerant GWPs, CEA grid-electricity baselines, and a representative
(not exhaustive) set of DEFRA Scope 3 proxy factors.

IMPORTANT PROVENANCE NOTE: these are standard, widely-published figures
reconstructed from general domain knowledge, not fetched from a live
document in this session. Fuel factors are computed here from their
published NCV / CO2-emission-factor / oxidation-factor components (visible
in the derivation below, matching the IPCC Vol 2 Tier 1 formula), so those
are reproducible and auditable. The refrigerant GWP, CEA, and DEFRA rows
are literal lookups from published tables, entered directly. Have the
sustainability team spot-check the seeded values -- especially the
refrigerant blend GWPs and the DEFRA Scope 3 proxies -- against the primary
documents before relying on them for a regulatory submission. Re-running
this script is safe: it skips any (substance_name, publication,
effective_year) combination that already exists.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.models import IpccReference  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402


def fuel_factor(ncv: float, co2_ef_per_tj: float, oxidation: float, density: float | None = None) -> float:
    """IPCC 2006 Vol 2 Tier 1: EF = NCV x CO2_EF / 1e6 x oxidation, in
    kg CO2 per kg fuel; multiplied by density when the target unit is a
    volume unit (kg CO2 per litre) rather than a mass unit."""
    value = ncv * co2_ef_per_tj / 1_000_000 * oxidation
    if density is not None:
        value *= density
    return round(value, 4)


FUEL_ROWS = [
    # substance, unit, ncv (MJ/kg), co2_ef (kg/TJ), oxidation, density (kg/L or None for mass-basis unit)
    ("Diesel", "kg CO2/L", 43.0, 74_100, 0.99, 0.85, ["HSD", "High Speed Diesel", "Automotive Diesel Oil", "Gas/Diesel Oil"]),
    ("Petrol", "kg CO2/L", 44.3, 69_300, 0.99, 0.76, ["Gasoline", "Motor Gasoline", "Motor Spirit"]),
    ("LPG", "kg CO2/kg", 47.3, 63_100, 0.99, None, ["Liquefied Petroleum Gas", "Propane", "Butane"]),
    ("Coal", "kg CO2/kg", 25.8, 94_600, 0.98, None, ["Other Bituminous Coal", "Bituminous Coal"]),
    ("Natural Gas", "kg CO2/kg", 48.0, 56_100, 1.0, None, ["Piped Natural Gas", "PNG", "CNG"]),
    ("Furnace Oil", "kg CO2/kg", 40.4, 77_400, 0.99, None, ["Residual Fuel Oil", "Heavy Fuel Oil", "FO"]),
]

# Acetylene has no IPCC Vol 2 stationary-combustion default -- derived here
# from combustion stoichiometry (C2H2 + 5/2 O2 -> 2 CO2 + H2O), not looked
# up from a published table. Flagged distinctly via `publication`.
ACETYLENE_FACTOR = round(2 * 44.01 / 26.04, 4)  # kg CO2 per kg acetylene

# (substance, unit, {publication: (gwp, effective_year)}, aliases)
REFRIGERANT_ROWS = [
    ("R-134a", "GWP-100 (kg CO2e/kg)", {"IPCC AR4 (2007)": (1430, 2007), "IPCC AR5 (2013)": (1300, 2013), "IPCC AR6 (2021)": (1530, 2021)}, ["HFC-134a", "R134a"]),
    ("R-32", "GWP-100 (kg CO2e/kg)", {"IPCC AR4 (2007)": (675, 2007), "IPCC AR5 (2013)": (677, 2013), "IPCC AR6 (2021)": (771, 2021)}, ["HFC-32", "R32"]),
    ("R-22", "GWP-100 (kg CO2e/kg)", {"IPCC AR4 (2007)": (1810, 2007), "IPCC AR5 (2013)": (1760, 2013), "IPCC AR6 (2021)": (1960, 2021)}, ["HCFC-22", "R22"]),
    ("R-404A", "GWP-100 (kg CO2e/kg)", {"IPCC AR4 (2007)": (3922, 2007), "IPCC AR5 (2013)": (3943, 2013), "IPCC AR6 (2021)": (4728, 2021)}, ["R404A"]),
    ("R-407C", "GWP-100 (kg CO2e/kg)", {"IPCC AR4 (2007)": (1774, 2007), "IPCC AR5 (2013)": (1774, 2013), "IPCC AR6 (2021)": (1624, 2021)}, ["R407C"]),
    ("R-410A", "GWP-100 (kg CO2e/kg)", {"IPCC AR4 (2007)": (2088, 2007), "IPCC AR5 (2013)": (1924, 2013), "IPCC AR6 (2021)": (2256, 2021)}, ["R410A"]),
    ("Halon 1211", "GWP-100 (kg CO2e/kg)", {"IPCC AR4 (2007)": (1890, 2007), "IPCC AR5 (2013)": (1750, 2013), "IPCC AR6 (2021)": (1930, 2021)}, ["Halon-1211", "Bromochlorodifluoromethane"]),
    ("Halon 1301", "GWP-100 (kg CO2e/kg)", {"IPCC AR4 (2007)": (7140, 2007), "IPCC AR5 (2013)": (6290, 2013), "IPCC AR6 (2021)": (6290, 2021)}, ["Halon-1301", "Bromotrifluoromethane"]),
]

GRID_ELECTRICITY_ROWS = [
    ("Grid Electricity (India, all-India average)", 0.820, 2023, "CEA_V19", "CEA CO2 Baseline Database, Version 19 (FY2022-23)"),
    ("Grid Electricity (India, all-India average)", 0.727, 2024, "CEA_V20", "CEA CO2 Baseline Database, Version 20 (FY2023-24)"),
    ("Grid Electricity (India, all-India average)", 0.710, 2025, "CEA_V21", "CEA CO2 Baseline Database, Version 21 (FY2024-25)"),
]

# Representative subset, not the full DEFRA workbook -- confidence on
# these is lower than the fuel/refrigerant rows above; verify before use.
DEFRA_SCOPE3_ROWS = [
    ("Business Travel - Car (average, petrol)", "kg CO2e/km", 0.1687, "Business Travel", 2025, "DEFRA 2025 Conversion Factors -- Business travel: land"),
    ("Business Travel - Domestic Flight", "kg CO2e/passenger.km", 0.2440, "Business Travel", 2025, "DEFRA 2025 Conversion Factors -- Business travel: air"),
    ("Employee Commuting - Car (average)", "kg CO2e/km", 0.1687, "Employee Commuting", 2025, "DEFRA 2025 Conversion Factors -- Employee commuting"),
    ("Employee Commuting - Rail (national)", "kg CO2e/km", 0.0357, "Employee Commuting", 2025, "DEFRA 2025 Conversion Factors -- Employee commuting"),
    ("Upstream/Downstream Transport - HGV (articulated, >33t)", "g CO2e/tonne.km", 62.5, "Upstream Transportation & Distribution", 2025, "DEFRA 2025 Conversion Factors -- Freight transport"),
    ("Waste Generated - Landfill (mixed municipal waste)", "tCO2e/tonne", 0.4869, "Waste Generated in Operations", 2025, "DEFRA 2025 Conversion Factors -- Waste disposal"),
    ("Waste Generated - Recycling (mixed materials)", "tCO2e/tonne", 0.0212, "Waste Generated in Operations", 2025, "DEFRA 2025 Conversion Factors -- Waste disposal"),
]


def upsert(db, **kwargs) -> bool:
    exists = (
        db.query(IpccReference)
        .filter(
            IpccReference.substance_name == kwargs["substance_name"],
            IpccReference.publication == kwargs["publication"],
            IpccReference.effective_year == kwargs["effective_year"],
        )
        .first()
    )
    if exists:
        return False
    db.add(IpccReference(**kwargs))
    return True


def main() -> None:
    db = SessionLocal()
    created = 0
    try:
        for substance, unit, ncv, co2_ef, oxidation, density, aliases in FUEL_ROWS:
            value = fuel_factor(ncv, co2_ef, oxidation, density)
            if upsert(
                db,
                substance_name=substance,
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
                source_reference="IPCC 2006 Guidelines for National GHG Inventories, Vol 2 (Energy), Tables 1.4 & 2.2",
            ):
                created += 1

        if upsert(
            db,
            substance_name="Acetylene",
            aliases=["C2H2", "Ethyne"],
            scope=1,
            factor_type="fuel",
            publication="Stoichiometric",
            effective_year=2006,
            ncv_mj_per_unit=None,
            density_kg_per_unit=None,
            co2_ef_per_tj=None,
            oxidation_factor=None,
            derived_factor_value=ACETYLENE_FACTOR,
            unit="kg CO2/kg",
            source_reference="Stoichiometric calculation (C2H2 complete combustion) -- no IPCC Vol 2 default exists for acetylene; verify before regulatory use",
        ):
            created += 1

        for substance, unit, versions, aliases in REFRIGERANT_ROWS:
            for publication, (gwp, year) in versions.items():
                if upsert(
                    db,
                    substance_name=substance,
                    aliases=aliases,
                    scope=1,
                    factor_type="gwp",
                    publication=publication.replace(" ", "_").replace("(", "").replace(")", ""),
                    effective_year=year,
                    ncv_mj_per_unit=None,
                    density_kg_per_unit=None,
                    co2_ef_per_tj=None,
                    oxidation_factor=None,
                    derived_factor_value=gwp,
                    unit=unit,
                    source_reference=f"{publication}, GWP-100 for {substance}",
                ):
                    created += 1

        for substance, value, year, publication, source_ref in GRID_ELECTRICITY_ROWS:
            if upsert(
                db,
                substance_name=substance,
                aliases=["Grid Electricity", "Grid Power", "Purchased Electricity"],
                scope=2,
                factor_type="grid_electricity",
                publication=publication,
                effective_year=year,
                ncv_mj_per_unit=None,
                density_kg_per_unit=None,
                co2_ef_per_tj=None,
                oxidation_factor=None,
                derived_factor_value=value,
                unit="tCO2/MWh",
                source_reference=source_ref,
            ):
                created += 1

        for name, unit, value, category, year, source_ref in DEFRA_SCOPE3_ROWS:
            if upsert(
                db,
                substance_name=name,
                aliases=[category],
                scope=3,
                factor_type="spend_based",
                publication="DEFRA_2025",
                effective_year=year,
                ncv_mj_per_unit=None,
                density_kg_per_unit=None,
                co2_ef_per_tj=None,
                oxidation_factor=None,
                derived_factor_value=value,
                unit=unit,
                source_reference=source_ref,
            ):
                created += 1

        db.commit()
        print(f"seeded {created} new ipcc_reference rows")
    finally:
        db.close()


if __name__ == "__main__":
    main()
