import { Component } from '@angular/core';
import { RouterLink } from '@angular/router';

interface FlowNode {
  title: string;
  detail: string;
  live: boolean;
}

interface ScopeRow {
  scope: string;
  source: string;
  method: string;
  live: boolean;
  note?: string;
}

@Component({
  selector: 'app-methodology',
  standalone: true,
  imports: [RouterLink],
  templateUrl: './methodology.component.html',
  styleUrl: './methodology.component.css'
})
export class MethodologyComponent {
  mainFlow: FlowNode[] = [
    { title: 'Activity input', detail: 'A preparer enters or bulk-uploads a value, e.g. litres of diesel or MWh of grid electricity.', live: true },
    { title: 'Unit conversion', detail: 'The activity value is normalized into the unit the matching emission factor expects.', live: true },
    { title: 'Factor resolution', detail: 'The platform picks the tenant’s own factor if one exists, otherwise the IPCC default — always the latest version effective on or before the activity period.', live: true },
    { title: 'Calculation snapshot', detail: 'Activity × factor is computed in exact decimal math and saved as an immutable, versioned record — never a live formula.', live: true },
    { title: 'Approval gate', detail: 'A Manager or Approver reviews and approves the entry before it can appear anywhere.', live: true },
    { title: 'Scope classification', detail: 'The approved calculation is tagged Scope 1 (fuel, fugitive) or Scope 2 (grid electricity, location- and market-based).', live: true },
    { title: 'Aggregation', detail: 'Approved calculations are summed by scope, period and tenant — the numbers behind every dashboard card.', live: true }
  ];

  branchFlow: FlowNode[] = [
    { title: 'Production volume', detail: 'Approved battery production (MnAh) for the same period and tenant.', live: true },
    { title: 'Intensity per production', detail: 'Scope 1+2 ÷ production volume — shown as “Specific GHG emissions” on the dashboard.', live: true }
  ];

  revenueBranch: FlowNode[] = [
    { title: 'Revenue', detail: 'Not yet wired up. Will need its own configurable-currency source, same as production.', live: false },
    { title: 'Intensity per revenue', detail: 'tCO2e per ₹ crore of revenue — planned, not calculated yet.', live: false }
  ];

  targetFlow: FlowNode[] = [
    { title: 'Target comparison', detail: 'Actual vs. declared target for the period. Planned — no targets are declared in the platform yet.', live: false },
    { title: 'Carbon dashboard', detail: 'Cards, trend charts and drill-down evidence for every number shown, all traceable back to an approved snapshot.', live: true }
  ];

  unresolvedFlow: FlowNode[] = [
    { title: 'Missing or ambiguous factor', detail: 'No matching factor, or two factors tie for the same period — the platform will not guess.', live: true },
    { title: 'Unresolved state', detail: 'The entry is marked unresolved and excluded from every total, so nothing silently under- or over-counts.', live: true },
    { title: 'Resolution queue', detail: 'Visible on the dashboard’s “unresolved” panel until an Admin adds or fixes the factor.', live: true },
    { title: 'Re-enters the flow', detail: 'Once resolved, the entry is recalculated through the same steps above — no special-casing.', live: true }
  ];

  scopeRows: ScopeRow[] = [
    { scope: 'Scope 1', source: 'Diesel, petrol, LPG', method: 'Fuel combustion — activity × fuel factor', live: true },
    { scope: 'Scope 1', source: 'Coal', method: 'Mapped, but no factor is loaded yet — stays unresolved rather than estimated', live: false, note: 'Add a factor on the Emission Factors screen to activate' },
    { scope: 'Scope 1', source: 'Refrigerant leakage (R-22, R-134a, R-32)', method: 'Fugitive — leaked mass × GWP factor', live: true },
    { scope: 'Scope 2', source: 'Grid electricity', method: 'Location-based (grid average) and market-based (supplier-specific) calculated in parallel', live: true },
    { scope: 'Scope 3', source: 'Value chain (purchased goods, logistics, business travel, …)', method: 'Deliberately deferred — no categories are collected or calculated yet', live: false }
  ];

  rules = [
    {
      title: 'Decimal math only',
      body: 'Every calculation uses exact decimal arithmetic, never binary floating point — so numbers that look exact stay exact.'
    },
    {
      title: 'Immutable snapshots',
      body: 'A calculated number is never edited in place. Recalculating a period supersedes the old row but keeps it on record, so a report you pulled last month still reproduces exactly.'
    },
    {
      title: 'Deterministic factor precedence',
      body: 'Tenant-specific factor first, IPCC default second. Among versions, the one effective on or before the activity period wins. A genuine tie is flagged as ambiguous, never picked arbitrarily.'
    },
    {
      title: 'Tenant isolation',
      body: 'A calculation only ever reads data and factors that belong to its own tenant.'
    },
    {
      title: 'No invented numbers',
      body: 'If a factor, unit mapping, or denominator (production, revenue) is missing, unapproved, or from the wrong period, the platform shows an explicit “data required” or “unresolved” state — it never fills the gap with an estimate.'
    }
  ];
}
