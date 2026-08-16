-- Adds edit/deactivate support to emission_factor (soft delete via
-- is_active, provenance via created_by), and scope3_category to
-- ipcc_reference so a Scope 3 reference row can carry its GHG Protocol
-- category directly rather than only being inferred at import time.

alter table emission_factor
    add column is_active boolean not null default true,
    add column created_by uuid references app_user(id) on delete set null;

alter table ipcc_reference
    add column scope3_category text;

-- The Prompt 3f verified dataset uses factor_type='specific' for most
-- Scope 3 rows (a category-specific published factor, as opposed to a
-- spend-based proxy) -- the original check constraint didn't allow it.
alter table ipcc_reference drop constraint ipcc_reference_factor_type_check;
alter table ipcc_reference add constraint ipcc_reference_factor_type_check
    check (factor_type in ('fuel', 'gwp', 'odp', 'grid_electricity', 'spend_based', 'specific'));
