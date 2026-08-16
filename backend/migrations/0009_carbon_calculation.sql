-- Carbon calculation engine (Prompt 4, step 2/6): an immutable, append-only
-- record per approved entry x factor-resolution, plus the production-volume
-- mapping the intensity KPI needs. Deliberately does NOT touch the existing
-- rollup/threshold tables -- those remain the Water/Waste dashboard's own
-- concern; this is a parallel system for GHG-specific results, since
-- rollup.aggregated_value is a plain float sum and blending tCO2e into it
-- would violate the Decimal-only rule below.

create table emission_calculation (
    id uuid primary key default gen_random_uuid(),
    tenant_id uuid not null references tenant(id) on delete cascade,
    location_id uuid not null references location(id) on delete cascade,
    entry_id uuid not null references entry(id) on delete cascade,
    data_point_id uuid not null references data_point(id) on delete cascade,
    reporting_period date not null,

    scope smallint not null check (scope in (1, 2, 3)),
    calculation_method text check (calculation_method is null or calculation_method in ('location_based', 'market_based')),
    status text not null check (status in ('calculated', 'unresolved', 'superseded', 'void')),

    activity_value numeric not null,
    activity_unit text not null,
    normalized_activity_value numeric,
    normalized_activity_unit text,

    -- Exactly one of these two is set when status = 'calculated' -- the
    -- factor may come from the tenant's own approved emission_factor row
    -- or, when the tenant hasn't set one, the seeded ipcc_reference row.
    -- Both are captured as a snapshot (version/value/unit/source), never a
    -- live join, so a later factor edit never rewrites this row.
    factor_id uuid references emission_factor(id) on delete set null,
    ipcc_reference_id uuid references ipcc_reference(id) on delete set null,
    factor_version text,
    factor_value numeric,
    factor_unit text,
    factor_source text,
    factor_effective_year integer,

    emissions_kgco2e numeric,
    formula text,
    resolution_reason text,

    calculated_at timestamptz not null default now(),
    calculated_by uuid references app_user(id) on delete set null,

    -- Append-only supersession chain -- a recalculation never updates a
    -- row in place, it inserts a new one and points back at what it
    -- replaced, marking the old row 'superseded'.
    supersedes_calculation_id uuid references emission_calculation(id) on delete set null,

    created_at timestamptz not null default now()
);

create index idx_emission_calc_tenant_period_status on emission_calculation(tenant_id, reporting_period, status);
create index idx_emission_calc_location_period on emission_calculation(location_id, reporting_period);
create index idx_emission_calc_entry on emission_calculation(entry_id);
create index idx_emission_calc_data_point_period on emission_calculation(data_point_id, reporting_period);

-- Only one row per entry may be the "current" (non-superseded, non-void)
-- calculation at a time -- enforced with a partial unique index rather
-- than a status-blind unique constraint, since the whole point of this
-- table is to keep every prior version around.
create unique index uq_emission_calc_current_per_entry
    on emission_calculation(entry_id)
    where status in ('calculated', 'unresolved');

-- Maps an approved production data point to the canonical MnAh unit the
-- battery-manufacturing intensity KPI is defined in. A config row, not a
-- hard-coded category name -- if a tenant records production in Ah or
-- MWh, native_unit/conversion_multiplier make that conversion explicit
-- and auditable instead of assuming a unit match.
create table production_volume_mapping (
    id uuid primary key default gen_random_uuid(),
    tenant_id uuid not null references tenant(id) on delete cascade,
    location_id uuid references location(id) on delete cascade,
    data_point_id uuid not null references data_point(id) on delete cascade,
    native_unit text not null,
    canonical_unit text not null default 'MnAh',
    conversion_multiplier numeric not null default 1,
    is_active boolean not null default true,
    created_at timestamptz not null default now()
);

create index idx_production_volume_mapping_tenant on production_volume_mapping(tenant_id, location_id);
