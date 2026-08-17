-- Peer benchmarking v1 (scoped from docs/CHART_SIMPLIFICATION_AND_PEER_ANALYSIS.md
-- Part 2 -- that spec's Excel-with-locked-cells template + granularity-aware
-- import pipeline is deferred; v1 is manual entry, one period at a time, since
-- a handful of peer companies with a few periods each doesn't need a file
-- upload pipeline to be useful). Peer figures are stored keyed by the SAME
-- metric keys the Chart Builder's CHARTABLE_METRICS registry uses, so peer
-- data slots directly into the existing comparison-chart machinery instead
-- of needing its own fixed columns per metric.

create table peer_company (
    id uuid primary key default gen_random_uuid(),
    tenant_id uuid not null references tenant(id) on delete cascade,
    name text not null,
    industry text,
    country text,
    created_by uuid references app_user(id) on delete set null,
    created_at timestamptz not null default now(),

    unique (tenant_id, name)
);

create table peer_data (
    id uuid primary key default gen_random_uuid(),
    tenant_id uuid not null references tenant(id) on delete cascade,
    peer_company_id uuid not null references peer_company(id) on delete cascade,
    period date not null,  -- month-start, same convention as Entry.period

    -- {metric_key: value}, keys drawn from the Chart Builder's
    -- CHARTABLE_METRICS registry -- validated against it server-side,
    -- never arbitrary keys.
    metrics jsonb not null default '{}'::jsonb,

    data_source text,       -- e.g. "BRSR 2026", "Annual Report 2026"
    source_link text,
    data_confidence text,   -- verified | self_reported | estimated
    notes text,

    uploaded_by uuid references app_user(id) on delete set null,
    uploaded_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),

    unique (tenant_id, peer_company_id, period)
);

create index idx_peer_data_tenant_company on peer_data(tenant_id, peer_company_id);
create index idx_peer_data_period on peer_data(tenant_id, period);
