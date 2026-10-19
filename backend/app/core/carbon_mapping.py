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
    source_type: str  # "fuel" | "gwp" | "grid_electricity" | "activity"
    ipcc_substance: str  # substance_name to look up in emission_factor/ipcc_reference
    expected_unit: str  # the activity unit this data point must be recorded in
    # GHG Protocol Scope 3 category ("1 Purchased goods & services", ...) --
    # None for Scope 1/2 sources.
    scope3_category: str | None = None


def _s3(category: str, substance: str, unit: str) -> CarbonSourceMapping:
    """Scope 3 sources are all activity-based: activity x a tenant factor
    expressed per that same activity unit (kgCO2e/t, kgCO2e/tkm, ...)."""
    return CarbonSourceMapping(scope=3, source_type="activity", ipcc_substance=substance, expected_unit=unit, scope3_category=category)


SCOPE3_CATEGORY_LABELS = {
    "1": "Cat 1 · Purchased goods & services",
    "2": "Cat 2 · Capital goods",
    "3": "Cat 3 · Fuel- & energy-related activities",
    "4": "Cat 4 · Upstream transportation",
    "5": "Cat 5 · Waste generated in operations",
    "6": "Cat 6 · Business travel",
    "7": "Cat 7 · Employee commuting",
    "9": "Cat 9 · Downstream transportation",
    "12": "Cat 12 · End-of-life of sold products",
}


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
    # ---- Scope 3 (value chain) -- battery manufacturing boundary ----------
    "Primary Lead Purchased": _s3("1", "Primary lead", "t"),
    "Secondary (Recycled) Lead Purchased": _s3("1", "Secondary lead", "t"),
    "Sulphuric Acid Purchased": _s3("1", "Sulphuric acid", "t"),
    "Polypropylene Purchased": _s3("1", "Polypropylene", "t"),
    "Lithium-ion Cells Purchased": _s3("1", "Lithium-ion cells", "kWh"),
    "Separators & Plastics Purchased": _s3("1", "Separators & engineering plastics", "t"),
    "Capex — Plant & Machinery": _s3("2", "Capex plant & machinery", "INR lakh"),
    "Capex — Buildings & Civil Works": _s3("2", "Capex buildings & civil", "INR lakh"),
    "Electricity T&D Losses & Upstream": _s3("3", "Grid electricity WTT + T&D", "kWh"),
    "Diesel Well-to-Tank": _s3("3", "Diesel WTT", "litres"),
    "Inbound Road Freight": _s3("4", "Road freight (HGV)", "tkm"),
    "Inbound Sea Freight": _s3("4", "Sea freight (container)", "tkm"),
    "Waste to Third-Party Landfill": _s3("5", "Waste to landfill", "t"),
    "Waste to Third-Party Incineration": _s3("5", "Waste incineration", "t"),
    "Waste to Third-Party Recycling": _s3("5", "Waste recycling", "t"),
    "Air Travel — Domestic": _s3("6", "Air travel domestic", "pkm"),
    "Air Travel — International": _s3("6", "Air travel international", "pkm"),
    "Rail Travel": _s3("6", "Rail travel", "pkm"),
    "Hotel Stays": _s3("6", "Hotel stay", "room-nights"),
    "Commute — Company Bus": _s3("7", "Company bus", "pkm"),
    "Commute — Two-Wheeler": _s3("7", "Two-wheeler", "km"),
    "Commute — Car": _s3("7", "Car (petrol/diesel avg)", "km"),
    "Outbound Road Freight": _s3("9", "Road freight (HGV) outbound", "tkm"),
    "Dealer Distribution — LCV": _s3("9", "Light commercial vehicle", "km"),
    "Spent Batteries Collected for Recycling": _s3("12", "End-of-life battery recycling", "t"),
    "Spent Batteries — Uncollected (Est.)": _s3("12", "End-of-life battery uncollected", "t"),
}


def get_carbon_mapping(data_point_name: str) -> CarbonSourceMapping | None:
    return CARBON_SOURCE_MAPPING.get(data_point_name)
