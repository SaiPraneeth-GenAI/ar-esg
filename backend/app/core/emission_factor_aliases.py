"""Deterministic alias dictionaries for the Emission Factors bulk upload.
Same approach as app/core/mapping_aliases.py -- exact alias hits first, then
fuzzy string matching (rapidfuzz) as an explainable, reproducible fallback.
No AI/LLM anywhere in this.
"""

# Sheet/tab name -> GHG scope. Matched against the sheet name, falling back
# to the filename, the same way entries bulk-upload matches a sheet to a
# Category.
SCOPE_SHEET_ALIASES: dict[str, list[str]] = {
    "1": ["scope 1", "scope1", "scope-1", "scope i"],
    "2": ["scope 2", "scope2", "scope-2", "scope ii"],
    "3": ["scope 3", "scope3", "scope-3", "scope iii"],
}

# Non-year metadata columns on an emission factor sheet. Checked first,
# before falling back to fuzzy matching against the field's own name.
EMISSION_FACTOR_FIELD_ALIASES: dict[str, list[str]] = {
    "name": [
        "fuel",
        "fuel type",
        "substance",
        "substance name",
        "refrigerant",
        "energy source",
        "grid energy",
        "material",
        "item",
    ],
    "method": [
        "method",
        "calculation method",
        "location based",
        "market based",
        "location-based",
        "market-based",
    ],
    "scope3_category": [
        "protocol category",
        "category",
        "ghg protocol category",
        "scope 3 category",
        "iso 14064-1 category",
        "iso category",
        "iso 14064 category",
    ],
    "description": [
        "description",
        "activity",
        "activity description",
        "description of activity",
        "sub category",
        "subcategory",
        "notes",
        "remarks",
    ],
    "unit": ["uom", "unit", "units", "unit of measure", "unit of measurement"],
    "source": ["source", "standard", "publishing body", "issuing body", "authority"],
    "source_reference": [
        "source reference",
        "reference",
        "citation",
        "source ref",
        "reference source",
        "source/reference",
    ],
    # A single (non-year-suffixed) factor value column -- e.g. the Scope 3
    # sheet's plain "Emission Factor" column, with no separate year columns.
    "value": ["emission factor", "factor", "ef", "emission factor value", "factor value", "gwp", "gwp factor"],
}

# Header keywords that mean a year/version-tagged column is NOT a factor --
# it's the activity data (consumption/quantity) or the calculated output
# (emission) sitting right next to the factor in the same real-world sheet.
# "factor" always wins if present, checked before these.
NON_FACTOR_YEAR_KEYWORDS: list[str] = [
    "consumption",
    "quantity",
    "usage",
    "activity data",
    "emission in",
    "total emission",
    "co2e generated",
    "ghg emission",
    "emission",
]

FACTOR_YEAR_KEYWORDS: list[str] = ["factor", "ef "]

# A column whose header contains any of these is a derived comparison, not
# a factor value in its own right (e.g. "Increase in emission factor" next
# to a real GWP factor table) -- always skip regardless of how strongly it
# otherwise fuzzy-matches "emission factor".
DERIVED_COLUMN_KEYWORDS: list[str] = ["increase", "decrease", "change", "delta", "variance", "% change", "growth"]

# The GHG Protocol's 15 Scope 3 categories -- used to canonicalize whatever
# text a customer's "Protocol Category" column contains.
SCOPE3_CATEGORIES: list[str] = [
    "Purchased Goods & Services",
    "Capital Goods",
    "Fuel- and Energy-Related Activities",
    "Upstream Transportation & Distribution",
    "Waste Generated in Operations",
    "Business Travel",
    "Employee Commuting",
    "Upstream Leased Assets",
    "Downstream Transportation & Distribution",
    "Processing of Sold Products",
    "Use of Sold Products",
    "End-of-Life Treatment of Sold Products",
    "Downstream Leased Assets",
    "Franchises",
    "Investments",
]

SCOPE3_CATEGORY_ALIASES: dict[str, list[str]] = {
    "Purchased Goods & Services": ["purchased goods and services", "purchased goods", "goods and services"],
    "Upstream Transportation & Distribution": ["upstream transport", "upstream transportation", "inbound logistics"],
    "Downstream Transportation & Distribution": ["downstream transport", "downstream transportation", "outbound logistics"],
    "Waste Generated in Operations": ["waste generated", "operational waste"],
    "Business Travel": ["business travel", "employee travel"],
    "Employee Commuting": ["employee commuting", "commuting"],
    "Upstream Leased Assets": ["upstream leased assets", "leased assets upstream"],
    "Downstream Leased Assets": ["downstream leased assets", "leased assets downstream"],
    "Use of Sold Products": ["use of sold products", "product use"],
    "End-of-Life Treatment of Sold Products": ["end of life", "end-of-life", "eol treatment", "eol"],
    "Franchises": ["franchises", "franchise"],
    "Processing of Sold Products": ["processing of sold products"],
    "Capital Goods": ["capital goods"],
    "Fuel- and Energy-Related Activities": ["fuel and energy related activities", "fuel and energy activities"],
    "Investments": ["investments", "investment"],
}
