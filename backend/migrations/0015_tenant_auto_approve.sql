-- Admin-controlled auto-approval: when on, an entry a Manager submits is
-- approved immediately (still recording an Approval row and audit trail,
-- just with no separate human approval step) instead of sitting in the
-- Approver's queue. Off by default -- existing tenants keep the manual
-- review workflow unless an Admin explicitly turns this on.

alter table tenant add column auto_approve_entries boolean not null default false;
