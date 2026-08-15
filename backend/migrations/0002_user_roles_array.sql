-- Roles become a list: a user can hold more than one role at once (e.g. Admin + Approver).
-- Valid roles: Admin, Manager, Approver.

alter table app_user drop constraint if exists app_user_role_check;

alter table app_user rename column role to roles;
alter table app_user alter column roles type text[] using array[roles];
alter table app_user alter column roles set default '{}'::text[];

alter table app_user add constraint app_user_roles_check
    check (roles <@ array['Admin', 'Manager', 'Approver']::text[]);
