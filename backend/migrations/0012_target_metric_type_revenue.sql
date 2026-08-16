-- Allow intensity_tco2e_per_revenue as a valid target metric_type, alongside
-- the existing absolute_tco2e and intensity_tco2e_per_mnah values.
alter table emission_target drop constraint emission_target_metric_type_check;

alter table emission_target
    add constraint emission_target_metric_type_check
    check (metric_type in ('absolute_tco2e', 'intensity_tco2e_per_mnah', 'intensity_tco2e_per_revenue'));
