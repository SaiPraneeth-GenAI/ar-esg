-- Extends emission_factor to be usable by the Emission Factors screen:
-- tenant-scoped, tagged by GHG scope (1/2/3), with the Scope 2 method,
-- Scope 3 category, free-text description, and a required source_reference
-- (a factor with no traceable citation shouldn't be allowed to save).
-- gas_type and source are relaxed to nullable since they're not meaningful
-- for every scope (e.g. Scope 2 has no "gas type", it has a method).

alter table emission_factor
    add column tenant_id uuid references tenant(id) on delete cascade,
    add column scope smallint,
    add column method text,
    add column scope3_category text,
    add column description text,
    add column source_reference text;

alter table emission_factor alter column source drop not null;
alter table emission_factor alter column gas_type drop not null;

update emission_factor set scope = 1 where scope is null;
update emission_factor set tenant_id = (select id from tenant order by created_at limit 1) where tenant_id is null;

alter table emission_factor alter column tenant_id set not null;
alter table emission_factor alter column scope set not null;

alter table emission_factor add constraint emission_factor_scope_check check (scope in (1, 2, 3));
alter table emission_factor add constraint emission_factor_method_check
    check (method is null or method in ('location-based', 'market-based'));

create index idx_emission_factor_tenant_scope on emission_factor(tenant_id, scope);
