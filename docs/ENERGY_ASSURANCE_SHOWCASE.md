# Energy Assurance showcase

Energy Assurance is an isolated, database-backed demonstration module. It shows how operational energy data can be controlled before a monthly ESG value is published downstream.

## Isolation boundary

The module has its own route, API, services and tables. It does not write to `entry`, `rollup`, `emission_calculation`, targets, dashboards or reports.

The only shared objects are the authenticated tenant and user identifiers. Synthetic showcase data is clearly marked and lives in `energy_assurance_*` tables.

## Demonstration flow

1. Open **Assurance Lab → Energy Assurance**.
2. Load the synthetic demonstration if the tenant has no showcase workspace.
3. Review reporting readiness and deliberate exceptions.
4. Inspect or edit sources, meters and readings.
5. Download the synthetic import workbook and upload it again.
6. Confirm column mapping and validate the rows. The workbook deliberately contains a duplicate and an unknown meter.
7. Open Reconciliation to compare meter totals against independent references.
8. Open Source-to-result to trace the demonstration Scope 2 result back to its factor, meter reading, source row and evidence reference.

## Database deployment

The backend deployment image includes `backend/migrations/0021_energy_assurance.sql` and applies this isolated, idempotent schema automatically at startup under a PostgreSQL advisory lock.

No database credentials are committed to this repository. The migration is additive and can be reviewed independently. It creates only `energy_assurance_*` tables and indexes; it does not alter the existing ESG tables.

## Contractual discovery boundary

The source names, thresholds, demonstration grid factor and workbook are synthetic. Real source-system connectors, customer reconciliation rules, evidence requirements and downstream export mappings must be configured only after contractual discovery.
