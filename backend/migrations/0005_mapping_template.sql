-- Remembers a confirmed bulk-upload column mapping so a repeat upload of
-- the same file format can skip the mapping step. Not part of the original
-- data dictionary -- added to support "remembered mapping templates".
create table mapping_template (
    id uuid primary key default gen_random_uuid(),
    tenant_id uuid not null references tenant(id) on delete cascade,
    category_id uuid not null references category(id) on delete cascade,
    header_fingerprint text not null,
    column_mapping jsonb not null,
    created_by uuid references app_user(id) on delete set null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (tenant_id, category_id, header_fingerprint)
);
