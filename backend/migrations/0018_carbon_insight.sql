-- Persists the AI-generated dashboard insight per tenant/location/period so
-- a repeat dashboard load reads the stored text instead of re-billing
-- OpenAI. input_hash is a hash of the exact figures the text was built
-- from; only a changed hash (the underlying approved data actually moved)
-- triggers a fresh generation. One row per (tenant_id, location_id, period,
-- period_mode), overwritten in place -- no unique constraint here since
-- Postgres treats NULL location_id (company-wide) as distinct on every row,
-- so the lookup/overwrite is done explicitly in application code instead.

create table carbon_insight (
    id uuid primary key default gen_random_uuid(),
    tenant_id uuid not null references tenant(id) on delete cascade,
    location_id uuid references location(id) on delete cascade,
    period date not null,
    period_mode text not null,

    input_hash text not null,
    insight_text text not null,
    model text not null,

    generated_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index idx_carbon_insight_lookup on carbon_insight(tenant_id, location_id, period, period_mode);
