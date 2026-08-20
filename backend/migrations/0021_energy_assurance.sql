-- Isolated Energy Assurance showcase.
-- These tables intentionally do not write to entry/rollup/emission_calculation.

create table if not exists energy_assurance_site (
    id uuid primary key default gen_random_uuid(),
    tenant_id uuid not null references tenant(id) on delete cascade,
    name text not null,
    description text,
    is_synthetic boolean not null default true,
    created_at timestamptz not null default now(),
    unique (tenant_id, name)
);

create table if not exists energy_assurance_source (
    id uuid primary key default gen_random_uuid(),
    tenant_id uuid not null references tenant(id) on delete cascade,
    site_id uuid not null references energy_assurance_site(id) on delete cascade,
    name text not null,
    source_type text not null check (source_type in ('grid', 'onsite_renewable', 'offsite_renewable', 'captive', 'generator', 'other')),
    supplier text,
    renewable boolean not null default false,
    active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (tenant_id, site_id, name)
);

create table if not exists energy_assurance_meter (
    id uuid primary key default gen_random_uuid(),
    tenant_id uuid not null references tenant(id) on delete cascade,
    site_id uuid not null references energy_assurance_site(id) on delete cascade,
    source_id uuid not null references energy_assurance_source(id) on delete cascade,
    meter_code text not null,
    name text not null,
    unit text not null default 'kWh',
    direction text not null default 'import' check (direction in ('import', 'export', 'generation', 'consumption')),
    active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (tenant_id, meter_code)
);

create table if not exists energy_assurance_import_batch (
    id uuid primary key default gen_random_uuid(),
    tenant_id uuid not null references tenant(id) on delete cascade,
    site_id uuid not null references energy_assurance_site(id) on delete cascade,
    filename text not null,
    status text not null default 'imported',
    row_count integer not null default 0,
    imported_by uuid references app_user(id) on delete set null,
    created_at timestamptz not null default now()
);

create table if not exists energy_assurance_reading (
    id uuid primary key default gen_random_uuid(),
    tenant_id uuid not null references tenant(id) on delete cascade,
    site_id uuid not null references energy_assurance_site(id) on delete cascade,
    source_id uuid not null references energy_assurance_source(id) on delete cascade,
    meter_id uuid not null references energy_assurance_meter(id) on delete cascade,
    import_batch_id uuid references energy_assurance_import_batch(id) on delete set null,
    period date not null,
    value numeric not null,
    unit text not null default 'kWh',
    evidence_reference text,
    source_row integer,
    status text not null default 'review' check (status in ('review', 'approved', 'rejected')),
    quality_flags jsonb not null default '[]'::jsonb,
    created_by uuid references app_user(id) on delete set null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (tenant_id, meter_id, period)
);

create table if not exists energy_assurance_reference (
    id uuid primary key default gen_random_uuid(),
    tenant_id uuid not null references tenant(id) on delete cascade,
    site_id uuid not null references energy_assurance_site(id) on delete cascade,
    source_id uuid not null references energy_assurance_source(id) on delete cascade,
    period date not null,
    reference_type text not null check (reference_type in ('utility_bill', 'renewable_claim', 'generation_statement', 'other')),
    reference_value numeric not null,
    unit text not null default 'kWh',
    evidence_reference text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (tenant_id, source_id, period, reference_type)
);

create index if not exists idx_ea_site_tenant on energy_assurance_site(tenant_id);
create index if not exists idx_ea_source_site on energy_assurance_source(tenant_id, site_id);
create index if not exists idx_ea_meter_site on energy_assurance_meter(tenant_id, site_id);
create index if not exists idx_ea_reading_period on energy_assurance_reading(tenant_id, site_id, period);
create index if not exists idx_ea_reference_period on energy_assurance_reference(tenant_id, site_id, period);
