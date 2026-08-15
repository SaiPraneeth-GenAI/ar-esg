-- One rollup row per tenant/location/category/month.
alter table rollup add constraint rollup_unique_period unique (tenant_id, location_id, category, period);
