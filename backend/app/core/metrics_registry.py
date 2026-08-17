"""The single source of truth for which metrics this platform can chart --
each entry maps a key to {label, unit, group, source, field, prior_field}
where `source` picks which trend endpoint (carbon/intensity/safety) the
field lives on. Deliberately dependency-free (no imports from
app.api.routes.*) so both charts.py (which dispatches on `source` to the
carbon/intensity/safety trend functions) and services like
target_calculation.py (which only needs the label/unit/group) can import
it without a circular import -- charts.py already imports FROM
carbon.py/intensity.py/safety.py, and carbon.py imports FROM
target_calculation.py for its dashboard target-comparison card, so this
registry can't live inside any route module those two might import."""

CHARTABLE_METRICS: dict[str, dict] = {
    "scope1_tco2e": {
        "label": "Scope 1", "unit": "tCO2e", "group": "GHG",
        "source": "carbon", "field": "scope1_tco2e", "prior_field": "prior_year_scope1_tco2e",
        "target_field": "target_scope1_tco2e",
    },
    "scope2_tco2e": {
        "label": "Scope 2 (location-based)", "unit": "tCO2e", "group": "GHG",
        "source": "carbon", "field": "scope2_location_based_tco2e", "prior_field": "prior_year_scope2_location_based_tco2e",
        "target_field": "target_scope2_location_based_tco2e",
    },
    "scope1_2_tco2e": {
        "label": "Scope 1+2 (location-based)", "unit": "tCO2e", "group": "GHG",
        "source": "carbon", "field": "scope1_2_location_based_tco2e", "prior_field": "prior_year_scope1_2_location_based_tco2e",
        "target_field": "target_scope1_2_location_based_tco2e",
    },
    "ghg_intensity_production": {
        "label": "GHG intensity", "unit": "tCO2e/MnAh", "group": "Intensity by production",
        "source": "carbon", "field": "intensity_tco2e_per_mnah", "prior_field": "prior_year_intensity_tco2e_per_mnah",
        "target_field": "target_intensity_tco2e_per_mnah",
    },
    "energy_per_production": {
        "label": "Energy intensity", "unit": "GJ/MnAh", "group": "Intensity by production",
        "source": "intensity", "field": "energy_per_production", "prior_field": "prior_year_energy_per_production",
        "target_field": "target_energy_per_production",
    },
    "water_per_production": {
        "label": "Water intensity", "unit": "KL/MnAh", "group": "Intensity by production",
        "source": "intensity", "field": "water_per_production", "prior_field": "prior_year_water_per_production",
        "target_field": "target_water_per_production",
    },
    "waste_per_production": {
        "label": "Waste intensity", "unit": "MT/MnAh", "group": "Intensity by production",
        "source": "intensity", "field": "waste_per_production", "prior_field": "prior_year_waste_per_production",
        "target_field": "target_waste_per_production",
    },
    "ghg_per_revenue": {
        "label": "GHG intensity", "unit": "tCO2e/Cr", "group": "Intensity by revenue",
        "source": "intensity", "field": "ghg_per_revenue", "prior_field": "prior_year_ghg_per_revenue",
        "target_field": "target_ghg_per_revenue",
    },
    "energy_per_revenue": {
        "label": "Energy intensity", "unit": "GJ/Cr", "group": "Intensity by revenue",
        "source": "intensity", "field": "energy_per_revenue", "prior_field": "prior_year_energy_per_revenue",
        "target_field": "target_energy_per_revenue",
    },
    "water_per_revenue": {
        "label": "Water intensity", "unit": "KL/Cr", "group": "Intensity by revenue",
        "source": "intensity", "field": "water_per_revenue", "prior_field": "prior_year_water_per_revenue",
        "target_field": "target_water_per_revenue",
    },
    "waste_per_revenue": {
        "label": "Waste intensity", "unit": "MT/Cr", "group": "Intensity by revenue",
        "source": "intensity", "field": "waste_per_revenue", "prior_field": "prior_year_waste_per_revenue",
        "target_field": "target_waste_per_revenue",
    },
    "safety_fatality": {"label": "Fatalities", "unit": "Nos", "group": "Safety", "source": "safety", "field": "Fatality"},
    "safety_ltifr": {"label": "LTIFR", "unit": "Rate", "group": "Safety", "source": "safety", "field": "LTIFR"},
    "safety_training": {
        "label": "Defensive Driving Training", "unit": "%", "group": "Safety",
        "source": "safety", "field": "Defensive Driving Training",
    },
    "safety_unsafe": {"label": "Unsafe Conditions", "unit": "Nos", "group": "Safety", "source": "safety", "field": "Unsafe Conditions"},
    "safety_near_miss": {"label": "Near Miss", "unit": "Nos", "group": "Safety", "source": "safety", "field": "Near Miss"},
}
