-- Read-only, seeded-at-migration-time reference table of published IPCC /
-- CEA / DEFRA emission factors -- never user-editable. Powers the
-- autocomplete + version history + calculation breakdown in the "Add
-- Factor" panel, and the IPCC cross-reference shown during bulk upload.
-- A tenant's own emission_factor rows are separate and only created when a
-- user explicitly adds or uploads one.

create table ipcc_reference (
    id uuid primary key default gen_random_uuid(),
    substance_name text not null,
    aliases jsonb not null default '[]'::jsonb,
    scope smallint not null check (scope in (1, 2, 3)),
    factor_type text not null check (factor_type in ('fuel', 'gwp', 'odp', 'grid_electricity', 'spend_based')),
    publication text not null,
    effective_year integer not null,
    ncv_mj_per_unit numeric,
    density_kg_per_unit numeric,
    co2_ef_per_tj numeric,
    oxidation_factor numeric,
    derived_factor_value numeric not null,
    unit text not null,
    source_reference text not null,
    created_at timestamptz not null default now()
);

create index idx_ipcc_reference_substance on ipcc_reference(substance_name);
create index idx_ipcc_reference_scope on ipcc_reference(scope);

-- Links a tenant's own emission_factor row back to the specific
-- ipcc_reference row it was derived from (via the IPCC-assisted panel).
-- Null for manually entered or bulk-uploaded factors.
alter table emission_factor add column ipcc_reference_key uuid references ipcc_reference(id) on delete set null;
