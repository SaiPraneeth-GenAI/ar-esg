-- Collapses scope + calculation_method + metric_type into a single
-- metric_key drawn from the Chart Builder's CHARTABLE_METRICS registry --
-- "which parameter is this target for" is now the exact same flat list of
-- metrics the dashboards already show (Scope 1/2/1+2 and GHG/Energy/
-- Water/Waste intensity by production or revenue), instead of a boundary
-- the user had to assemble from three separate scope/method/type choices.
-- Safety metrics aren't included yet -- they need a reduce-vs-increase
-- direction concept the target engine doesn't have (Defensive Driving
-- Training is a "higher is better" metric, unlike everything else here).

alter table emission_target add column metric_key text;

update emission_target set metric_key = case
    when metric_type = 'intensity_tco2e_per_mnah' then 'ghg_intensity_production'
    when metric_type = 'intensity_tco2e_per_revenue' then 'ghg_per_revenue'
    when metric_type = 'absolute_tco2e' and scope = '1' then 'scope1_tco2e'
    when metric_type = 'absolute_tco2e' and scope = '2' and coalesce(calculation_method, 'location_based') = 'location_based' then 'scope2_tco2e'
    when metric_type = 'absolute_tco2e' and scope = '1_2_combined' then 'scope1_2_tco2e'
end;

-- Deliberately no fallback/default in the CASE above -- if any row didn't
-- match (e.g. a market-based Scope 2 target, which has no equivalent in
-- CHARTABLE_METRICS), this NOT NULL constraint fails loudly instead of
-- silently mis-mapping or dropping data.
alter table emission_target alter column metric_key set not null;

alter table emission_target add constraint emission_target_metric_key_check check (metric_key in (
    'scope1_tco2e', 'scope2_tco2e', 'scope1_2_tco2e',
    'ghg_intensity_production', 'energy_per_production', 'water_per_production', 'waste_per_production',
    'ghg_per_revenue', 'energy_per_revenue', 'water_per_revenue', 'waste_per_revenue'
));

drop index uq_emission_target_active_boundary;
create unique index uq_emission_target_active_boundary
    on emission_target(tenant_id, coalesce(location_id, '00000000-0000-0000-0000-000000000000'::uuid), metric_key)
    where status = 'active';

alter table emission_target drop constraint emission_target_scope_check;
alter table emission_target drop constraint emission_target_calculation_method_check;
alter table emission_target drop constraint emission_target_metric_type_check;
alter table emission_target drop column scope;
alter table emission_target drop column calculation_method;
alter table emission_target drop column metric_type;
