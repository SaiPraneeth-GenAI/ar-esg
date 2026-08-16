-- Carbon targets (Prompt 4, target-setting workflow). A target is created
-- as a draft, its baseline is computed read-only from approved calculation
-- snapshots, and only locks in place when an authorised user activates it
-- -- at which point the exact calculation rows behind the baseline are
-- recorded so a later factor change or recalculation can never silently
-- move the goalposts.

create table emission_target (
    id uuid primary key default gen_random_uuid(),
    tenant_id uuid not null references tenant(id) on delete cascade,
    location_id uuid references location(id) on delete cascade,  -- null = org-wide boundary

    scope text not null check (scope in ('1', '2', '1_2_combined')),
    calculation_method text check (calculation_method is null or calculation_method in ('location_based', 'market_based')),
    metric_type text not null check (metric_type in ('absolute_tco2e', 'intensity_tco2e_per_mnah')),

    baseline_period_start date not null,
    baseline_period_end date not null,
    baseline_value numeric,
    baseline_completeness_pct numeric,
    -- The emission_calculation ids that were summed into baseline_value,
    -- captured at activation time -- the baseline stays reproducible even
    -- if those rows are later superseded by a recalculation.
    baseline_calculation_ids jsonb not null default '[]'::jsonb,
    baseline_locked_at timestamptz,

    reduction_percentage numeric check (reduction_percentage is null or (reduction_percentage >= 0 and reduction_percentage <= 100)),
    target_period_start date not null,
    target_period_end date not null,
    target_value numeric,
    -- [{period: "2026-01-01", value: 123.4}, ...] -- validated server-side
    -- to sum to target_value before a target can be activated.
    monthly_phasing jsonb not null default '[]'::jsonb,

    status text not null check (status in ('draft', 'active', 'archived')) default 'draft',
    owner_id uuid references app_user(id) on delete set null,
    rationale text,
    approved_by uuid references app_user(id) on delete set null,
    approved_at timestamptz,

    -- Hash of tenant/location/scope/method/metric/production-mapping at
    -- activation time, so a later boundary or denominator change is
    -- detectable instead of silently comparing against a moved target.
    boundary_config_hash text,

    created_by uuid references app_user(id) on delete set null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index idx_emission_target_tenant_status on emission_target(tenant_id, status);
create index idx_emission_target_location on emission_target(location_id);

-- At most one active target per tenant/location/scope/metric boundary --
-- otherwise "the" target for a given metric would be ambiguous.
create unique index uq_emission_target_active_boundary
    on emission_target(tenant_id, coalesce(location_id, '00000000-0000-0000-0000-000000000000'::uuid), scope, metric_type)
    where status = 'active';
