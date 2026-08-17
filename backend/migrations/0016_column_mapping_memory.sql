-- Per-column bulk-upload mapping memory. Complements mapping_template
-- (which caches a mapping for an EXACT whole header-set fingerprint --
-- any added/renamed/reordered column is a full cache miss) with a
-- per-header cache: once "Grid Power" has been confirmed to mean Grid
-- Electricity Consumed for a tenant+category, it's remembered independent
-- of whatever other columns are in the file. Populated automatically
-- whenever a mapping is confirmed (manual save-template confirmation or
-- an accepted AI mapping suggestion), never written directly by a user.

create table column_mapping_memory (
    id uuid primary key default gen_random_uuid(),
    tenant_id uuid not null references tenant(id) on delete cascade,
    category_id uuid not null references category(id) on delete cascade,
    source_header text not null,   -- normalized header string
    target_type text not null,     -- 'metadata' | 'data_point'
    target text not null,          -- 'period' | 'note' | data_point id (as text)
    confidence real not null,
    source text not null,          -- 'manual_confirm' | 'ai_confirm'
    confirmed_by uuid references app_user(id) on delete set null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),

    unique (tenant_id, category_id, source_header)
);

create index idx_column_mapping_memory_tenant on column_mapping_memory(tenant_id, category_id);
