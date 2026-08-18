-- In-app notifications (bell icon): a row per recipient per event, so the
-- header can show an unread count without polling email. Paired with the
-- existing approval-queue/bulk-decision emails -- same trigger points,
-- just a second, in-app delivery channel that can be marked read.

create table notification (
    id uuid primary key default gen_random_uuid(),
    tenant_id uuid not null references tenant(id) on delete cascade,
    user_id uuid not null references app_user(id) on delete cascade,
    kind text not null,
    title text not null,
    body text,
    link text,
    read_at timestamptz,
    created_at timestamptz not null default now()
);

create index notification_user_unread_idx on notification (user_id, read_at);
create index notification_user_created_idx on notification (user_id, created_at desc);
