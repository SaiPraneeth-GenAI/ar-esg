-- Revenue's twin of production_volume_mapping (0009): maps a tenant's
-- chosen "Revenue" data point to the canonical unit the revenue-intensity
-- KPIs are defined in. Kept as its own table rather than folding into
-- production_volume_mapping so the already-live production intensity path
-- stays untouched -- same shape, same conventions, separate blast radius.

create table revenue_mapping (
    id uuid primary key default gen_random_uuid(),
    tenant_id uuid not null references tenant(id) on delete cascade,
    location_id uuid references location(id) on delete cascade,
    data_point_id uuid not null references data_point(id) on delete cascade,
    native_unit text not null,
    canonical_unit text not null default 'INR Cr',
    conversion_multiplier numeric not null default 1,
    is_active boolean not null default true,
    created_at timestamptz not null default now()
);

create index idx_revenue_mapping_tenant on revenue_mapping(tenant_id, location_id);
