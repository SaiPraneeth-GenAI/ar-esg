-- Envigo initial schema
-- Matches docs/data_model_and_dictionary.md exactly (Config & Tenancy -> Transactional -> Reference -> Output)

create extension if not exists pgcrypto;

-- ============ Config & Tenancy ============

create table tenant (
    id uuid primary key default gen_random_uuid(),
    name text not null,
    industry_vertical text,
    branding_config jsonb,
    schema_mode text,
    created_at timestamptz not null default now()
);

create table location (
    id uuid primary key default gen_random_uuid(),
    tenant_id uuid not null references tenant(id) on delete cascade,
    name text not null,
    address text,
    plant_type text,
    parent_location_id uuid references location(id) on delete set null
);

create table app_user (
    id uuid primary key default gen_random_uuid(),
    tenant_id uuid not null references tenant(id) on delete cascade,
    email text not null unique,
    role text not null check (role in ('Preparer', 'Approver', 'Admin', 'Viewer')),
    location_scope uuid[],
    auth_provider text
);

create table category (
    id uuid primary key default gen_random_uuid(),
    tenant_id uuid not null references tenant(id) on delete cascade,
    name text not null,
    industry_pack text,
    display_order integer
);

create table data_point (
    id uuid primary key default gen_random_uuid(),
    category_id uuid not null references category(id) on delete cascade,
    name text not null,
    unit text,
    input_type text,
    validation_rules jsonb,
    conditional_on uuid references data_point(id) on delete set null,
    framework_tags text[]
);

-- ============ Transactional ============

create table entry (
    id uuid primary key default gen_random_uuid(),
    data_point_id uuid not null references data_point(id) on delete cascade,
    location_id uuid not null references location(id) on delete cascade,
    period date not null,
    value numeric,
    method_of_entry text not null default 'Manual' check (method_of_entry in ('Manual', 'CSV', 'API', 'DB_SYNC')),
    status text not null default 'Draft' check (status in ('Draft', 'Submitted', 'Approved', 'Rejected')),
    submitted_by uuid references app_user(id) on delete set null,
    note text,
    meter_id text,
    severity text check (severity in ('green', 'amber', 'red'))
);

create table approval (
    id uuid primary key default gen_random_uuid(),
    entry_id uuid not null references entry(id) on delete cascade,
    approver_id uuid references app_user(id) on delete set null,
    action text not null check (action in ('approve', 'reject')),
    reject_note text,
    "timestamp" timestamptz not null default now()
);

create table audit_log (
    id uuid primary key default gen_random_uuid(),
    entry_id uuid not null references entry(id) on delete cascade,
    actor text,
    action text not null,
    old_value text,
    new_value text,
    "timestamp" timestamptz not null default now()
);

create table attachment (
    id uuid primary key default gen_random_uuid(),
    entry_id uuid not null references entry(id) on delete cascade,
    file_url text not null,
    file_type text,
    uploaded_by uuid references app_user(id) on delete set null,
    uploaded_at timestamptz not null default now()
);

create table db_connection (
    id uuid primary key default gen_random_uuid(),
    tenant_id uuid not null references tenant(id) on delete cascade,
    db_type text not null,
    host text not null,
    encrypted_credentials text not null,
    schema_mapping jsonb,
    sync_schedule text,
    last_synced_at timestamptz
);

-- ============ Reference ============

create table emission_factor (
    id uuid primary key default gen_random_uuid(),
    source text not null,
    gas_type text not null,
    factor_value numeric not null,
    unit text not null,
    effective_date date not null,
    version text not null
);

create table compliance_framework (
    id uuid primary key default gen_random_uuid(),
    name text not null,
    field_mapping jsonb
);

create table threshold (
    id uuid primary key default gen_random_uuid(),
    data_point_id uuid not null references data_point(id) on delete cascade,
    jurisdiction text,
    min_value numeric,
    max_value numeric,
    target_value numeric
);

-- ============ Output ============

create table rollup (
    id uuid primary key default gen_random_uuid(),
    tenant_id uuid not null references tenant(id) on delete cascade,
    location_id uuid not null references location(id) on delete cascade,
    period date not null,
    category text not null,
    aggregated_value numeric,
    target_value numeric,
    benchmark_value numeric
);

create table compliance_report (
    id uuid primary key default gen_random_uuid(),
    tenant_id uuid not null references tenant(id) on delete cascade,
    framework text not null,
    period date not null,
    generated_file_url text,
    generated_at timestamptz not null default now()
);

create table report_request (
    id uuid primary key default gen_random_uuid(),
    tenant_id uuid not null references tenant(id) on delete cascade,
    report_type text not null,
    requested_by uuid references app_user(id) on delete set null,
    parameters jsonb,
    status text not null default 'Pending',
    generated_file_url text,
    source_rollup_ids uuid[],
    reviewed_by uuid references app_user(id) on delete set null,
    reviewed_at timestamptz
);

create table mailing_list (
    id uuid primary key default gen_random_uuid(),
    tenant_id uuid not null references tenant(id) on delete cascade,
    alert_type text not null,
    recipients text[] not null,
    schedule text
);

create table email_log (
    id uuid primary key default gen_random_uuid(),
    recipient text not null,
    subject text not null,
    sent_at timestamptz not null default now(),
    related_id uuid,
    status text not null
);

-- ============ Indexes ============

create index idx_location_tenant on location(tenant_id);
create index idx_app_user_tenant on app_user(tenant_id);
create index idx_category_tenant on category(tenant_id);
create index idx_data_point_category on data_point(category_id);
create index idx_entry_data_point on entry(data_point_id);
create index idx_entry_location_period on entry(location_id, period);
create index idx_approval_entry on approval(entry_id);
create index idx_audit_log_entry on audit_log(entry_id);
create index idx_attachment_entry on attachment(entry_id);
create index idx_threshold_data_point on threshold(data_point_id);
create index idx_rollup_tenant_period on rollup(tenant_id, period);
create index idx_report_request_tenant on report_request(tenant_id);
create index idx_mailing_list_tenant on mailing_list(tenant_id);
