"""Deterministic mapping from a DataPoint (by name) to how it's calculated
into GHG emissions. Deliberately an explicit table, not a name-similarity
match -- rule #3 in Prompt 4 forbids picking a factor because its name
happens to partially match. If a data point isn't listed here, it's simply
not a GHG source in this release (Water/Waste/ODS/air-pollutant values
stay excluded from tCO2e totals, per the same prompt).
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class CarbonSourceMapping:
    scope: int
    source_type: str  # "fuel" | "gwp" | "grid_electricity"
    ipcc_substance: str  # substance_name to look up in emission_factor/ipcc_reference
    expected_unit: str  # the activity unit this data point must be recorded in


CARBON_SOURCE_MAPPING: dict[str, CarbonSourceMapping] = {
    "Diesel Consumed": CarbonSourceMapping(scope=1, source_type="fuel", ipcc_substance="Diesel", expected_unit="litres"),
    "Petrol Consumed": CarbonSourceMapping(scope=1, source_type="fuel", ipcc_substance="Petrol", expected_unit="litres"),
    "LPG Consumed": CarbonSourceMapping(scope=1, source_type="fuel", ipcc_substance="Liquefied Petroleum Gas", expected_unit="kg"),
    "Coal Consumed": CarbonSourceMapping(scope=1, source_type="fuel", ipcc_substance="Coal", expected_unit="kg"),
    "Grid Electricity Consumed": CarbonSourceMapping(
        scope=2, source_type="grid_electricity", ipcc_substance="India Grid Electricity (All-India weighted average)", expected_unit="kWh"
    ),
    "Refrigerant Leakage — R-22": CarbonSourceMapping(scope=1, source_type="gwp", ipcc_substance="R-22", expected_unit="kg"),
    "Refrigerant Leakage — R-134a": CarbonSourceMapping(scope=1, source_type="gwp", ipcc_substance="R-134a", expected_unit="kg"),
    "Refrigerant Leakage — R-32": CarbonSourceMapping(scope=1, source_type="gwp", ipcc_substance="R-32", expected_unit="kg"),
    # "Refrigerant Leakage — Halon" is intentionally NOT mapped: the seeded
    # reference table only carries Halon's ODP value (Montreal Protocol),
    # not a GWP-100 value -- ODP is not CO2e (see Prompt 4), so there is no
    # correct factor to calculate this against yet. Entries against it
    # correctly resolve to "missing_factor", not a guess.
}


def get_carbon_mapping(data_point_name: str) -> CarbonSourceMapping | None:
    return CARBON_SOURCE_MAPPING.get(data_point_name)
