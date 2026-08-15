# Data Model & Full Data Dictionary

Companion reference to the two diagrams (end-to-end data flow, entity-relationship model). This document lists every table and every field, grouped exactly as the ER diagram groups them: Config & Tenancy → Transactional → Reference → Output.

---

## Config & Tenancy (set up once per customer)

**Tenant** — one row per customer organization
- `id`, `name`, `industry_vertical` (e.g. battery manufacturing), `branding_config` (logo/colors — powers the multi-tenant branding toggle), `schema_mode` (dedicated schema for enterprise, shared+RLS for smaller customers), `created_at`

**Location** — one row per plant/site
- `id`, `tenant_id`, `name` (e.g. ARE&M), `address`, `plant_type`, `parent_location_id` (supports Corporate → Business Unit → Plant hierarchy)

**User**
- `id`, `tenant_id`, `email`, `role` (Preparer / Approver / Admin / Viewer), `location_scope` (which locations this user can act on), `auth_provider` (email/password or Azure AD SSO)

**Category** — metadata-driven, not hardcoded
- `id`, `tenant_id`, `name` (Water, Waste, Effluent Monitoring...), `industry_pack` (which vertical this belongs to), `display_order`

**DataPoint** — the individual field definitions within a category
- `id`, `category_id`, `name` (e.g. "Ground Water Withdrawal"), `unit`, `input_type` (number/select/repeatable), `validation_rules` (min/max, derived from location history), `conditional_on` (parent field that must be true/set for this to show), `framework_tags` (array — which disclosures this satisfies: BRSR, GRI, CPCB-EPR)

---

## Transactional (the actual monthly data)

**Entry** — one row per submitted reading
- `id`, `data_point_id`, `location_id`, `period` (month/year), `value`, `method_of_entry` (Manual / CSV / API), `status` (Draft / Submitted / Approved / Rejected), `submitted_by`, `note`, `meter_id` (supports multi-meter, matching the Meter ID column already present in Amara Raja's current tool)

**Approval**
- `id`, `entry_id`, `approver_id`, `action` (approve/reject), `reject_note`, `timestamp`

**AuditLog** — append-only, never updated or deleted
- `id`, `entry_id`, `actor`, `action`, `old_value`, `new_value`, `timestamp`

**Attachment**
- `id`, `entry_id`, `file_url` (points to object storage, not stored in Postgres), `file_type`, `uploaded_by`, `uploaded_at`

---

## Reference (versioned, rarely changes)

**EmissionFactor**
- `id`, `source` (IPCC/EPA/India GHG Program), `gas_type`, `factor_value`, `unit`, `effective_date`, `version` — versioned so a factor update never silently rewrites a historical calculation

**ComplianceFramework**
- `id`, `name` (BRSR / GRI / ISSB / CPCB-EPR), `field_mapping` (which DataPoints satisfy which disclosure line item)

---

## Output (derived — nothing here is typed by a person)

**Rollup** — materialized view, refreshed the moment an entry is approved
- `id`, `tenant_id`, `location_id`, `period`, `category`, `aggregated_value`, `target_value`, `benchmark_value`

**ComplianceReport**
- `id`, `tenant_id`, `framework`, `period`, `generated_file_url`, `generated_at`

---

## Every type of data entering the system, summarized

| Data type | Enters via | Lands in |
|---|---|---|
| Monthly ESG readings (Water, Waste, Effluent, Air, Ozone) | Manual guided form, bulk CSV, future IoT/ERP feed | `Entry` |
| Supporting evidence files | File attachment on any entry | `Attachment` (object storage) |
| User identity & permissions | Supabase Auth login (email/password or Azure AD) | `User` |
| Organizational structure | Admin setup (onboarding) | `Tenant`, `Location` |
| Field definitions per industry | Platform config (metadata-driven, not code) | `Category`, `DataPoint` |
| Approval decisions | Approver action in the workflow UI | `Approval` |
| Every change ever made | Automatic, on every write | `AuditLog` |
| Emission factors | Maintained by sustainability team, versioned | `EmissionFactor` |
| Disclosure framework mappings | Platform config | `ComplianceFramework` |
| Aggregated dashboard numbers | Computed automatically from approved `Entry` rows | `Rollup` |
| Generated compliance documents | Computed on demand from `Rollup` + `ComplianceFramework` | `ComplianceReport` |

This is the complete inventory — every box in the flow diagram and every entity in the ER diagram maps to a row in this table.

---

## Addendum — 3 corrections added after review

**Correction 1 — External DB connector.** A new input path alongside manual/CSV/IoT: `DBConnection` (`id`, `tenant_id`, `db_type`, `host`, `encrypted_credentials`, `schema_mapping`, `sync_schedule`, `last_synced_at`). A scheduled sync job pulls from a customer's own database and maps their columns to our `DataPoint` fields, then writes into `Entry` with `method_of_entry = DB_SYNC` — it goes through the exact same validation/approval pipeline as everything else, no special-casing.

**Correction 2 — Agentic reporting engine.** A `ReportRequest` entity (`id`, `tenant_id`, `report_type`, `requested_by`, `prompt/parameters`, `status`, `generated_file_url`, `source_rollup_ids[]`, `reviewed_by`, `reviewed_at`). An agent orchestrator queries `Rollup`/`Entry`/`ComplianceFramework` through defined read-only tools, drafts narrative + assembles charts/tables into the report, and every generated document stores exactly which rows it drew from — for traceability if a number is ever questioned.

**Correction 3 — Mailing engine + exceedance color grading.** `Threshold` (`id`, `data_point_id`, `jurisdiction`, `min_value`, `max_value`, `target_value`) holds real regulatory/internal limits per field. Every new `Entry` is evaluated against its `Threshold` at validation time and stamped with a stored severity (`green`/`amber`/`red`) — not just a UI color, a queryable field. `MailingList` (`tenant_id`, `alert_type`, `recipients[]`, `schedule`) and `EmailLog` (`recipient`, `subject`, `sent_at`, `related_id`, `status`) drive scheduled report distribution and real-time exceedance alerts.
