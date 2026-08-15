-- Add "Bulk Upload" as a valid method_of_entry (the wizard replaces the
-- earlier single-shot CSV upload, which used "CSV").
alter table entry drop constraint if exists entry_method_of_entry_check;
alter table entry add constraint entry_method_of_entry_check
    check (method_of_entry in ('Manual', 'CSV', 'Bulk Upload', 'API', 'DB_SYNC'));
