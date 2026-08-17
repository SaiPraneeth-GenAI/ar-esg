-- Chart Builder v1 (scoped to the existing stack -- see
-- docs/CHART_BRAINSTORM_QA.md for the original, larger spec this
-- descends from). A saved chart is just a small config pointing at one of
-- the platform's existing computed metrics (the same ones the dashboard
-- trend charts already compute) plus the display settings a user picked
-- -- no custom SQL, no arbitrary joins, nothing beyond what the app
-- already calculates. Charts always query live data; there is no
-- snapshot, so a chart reflects whatever the underlying approved data
-- says at view time.

create table saved_chart (
    id uuid primary key default gen_random_uuid(),
    tenant_id uuid not null references tenant(id) on delete cascade,
    owner_id uuid not null references app_user(id) on delete cascade,

    name text not null,
    description text,

    -- {metric, chart_kind, period_mode, months, location_id} -- validated
    -- against the fixed CHARTABLE_METRICS registry server-side, never
    -- passed through to a query as raw SQL.
    config jsonb not null default '{}'::jsonb,

    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),

    unique (tenant_id, owner_id, name)
);

create index idx_saved_chart_tenant_owner on saved_chart(tenant_id, owner_id);
