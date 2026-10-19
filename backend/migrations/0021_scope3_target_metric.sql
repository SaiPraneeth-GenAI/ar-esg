-- Scope 3 (value chain) becomes a calculated, targetable GHG metric: the
-- carbon engine now resolves activity-based Scope 3 sources (purchased
-- materials, freight, travel, commuting, waste, end-of-life) the same way
-- it resolves Scope 1/2, so a reduction target can be set against it.

alter table emission_target drop constraint emission_target_metric_key_check;

alter table emission_target add constraint emission_target_metric_key_check check (metric_key in (
    'energy_absolute', 'water_absolute', 'waste_absolute', 'production_absolute',
    'scope1_tco2e', 'scope2_tco2e', 'scope1_2_tco2e', 'scope3_tco2e',
    'ghg_intensity_production', 'energy_per_production', 'water_per_production', 'waste_per_production',
    'ghg_per_revenue', 'energy_per_revenue', 'water_per_revenue', 'waste_per_revenue',
    'safety_fatality', 'safety_ltifr', 'safety_training', 'safety_unsafe', 'safety_near_miss'
));
