"""Deterministic alias dictionaries for bulk-upload mapping. No AI/LLM
anywhere in this -- exact alias hits first, then fuzzy string matching
(rapidfuzz) as an explainable, reproducible fallback. Maintained here so
new aliases can be added without touching matching logic.
"""

CATEGORY_ALIASES: dict[str, list[str]] = {
    "Water": ["water", "water withdrawal", "water log", "water register", "water consumption", "water source"],
    "ETP-Water": ["etp water", "effluent treatment plant", "etp", "etp log", "etp register"],
    "STP-Water": ["stp water", "sewage treatment plant", "stp", "stp log", "stp register"],
    "Waste": ["waste", "waste register", "waste log", "waste management", "waste disposal"],
    "Ozone": ["ozone", "ods", "refrigerants", "ozone depleting substances", "refrigerant log"],
    "Effluent Monitoring": ["effluent monitoring", "effluent", "effluent quality", "effluent parameters"],
    "Air Emissions": ["air emissions", "air", "emissions", "ghg", "scope 1", "scope 2", "fuel consumption", "energy"],
    "Production": ["production", "production volume", "output", "battery production"],
}

# Metadata columns that aren't a data point -- period and free-text note.
METADATA_FIELD_ALIASES: dict[str, list[str]] = {
    "period": ["period", "month", "date", "reporting period", "period month", "reporting month"],
    "note": ["note", "notes", "comment", "remarks", "remark"],
}

# Known shorthand/abbreviations customers commonly use for specific fields.
# Matched in addition to the field's own name (which is always tried first).
DATA_POINT_ALIASES: dict[str, list[str]] = {
    "Ground Water Withdrawal": ["gw withdrawal", "groundwater", "bore well water", "borewell water", "ground water"],
    "Surface Water Withdrawal": ["surface water"],
    "Third-Party Water Withdrawal": ["municipal water", "third party water", "purchased water", "third-party water"],
    "Packaging Drinking Water": ["drinking water", "packaged water", "bottled water"],
    "Total Treated Effluent Generated": ["treated effluent", "effluent generated", "total effluent"],
    "Recycled Water Used for Process": ["recycled water process", "process reuse water"],
    "Recycled Water Used for Irrigation": ["recycled water irrigation", "irrigation reuse water"],
    "Grid Electricity Consumed": ["electricity", "power consumption", "grid power", "electricity consumed"],
    "Renewable / PPA-Covered Percentage": ["renewable percentage", "ppa percentage", "renewable %", "green power %"],
    "Diesel Consumed": ["diesel", "hsd", "diesel consumption"],
    "Petrol Consumed": ["petrol", "gasoline", "petrol consumption"],
    "LPG Consumed": ["lpg", "lpg consumption"],
    "Coal Consumed": ["coal", "coal consumption"],
    "R-22": ["r22", "hcfc-22", "hcfc 22"],
    "R-134a": ["r134a", "hfc-134a", "hfc 134a"],
    "R-32": ["r32", "hfc-32", "hfc 32"],
    "Halon": ["halon gas"],
    "pH": ["ph level", "ph value"],
    "BOD": ["biochemical oxygen demand"],
    "COD": ["chemical oxygen demand"],
    "Battery Production Volume": ["production volume", "battery output", "cells produced"],
}
