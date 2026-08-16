import { Component } from '@angular/core';
import { RouterLink } from '@angular/router';
import { FlowDiagramComponent } from './flow-diagram/flow-diagram.component';

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
  imports: [RouterLink, FlowDiagramComponent],
  templateUrl: './methodology.component.html',
  styleUrl: './methodology.component.css'
})
export class MethodologyComponent {
  scopeRows: ScopeRow[] = [
    { scope: 'Scope 1', source: 'Diesel, petrol, LPG', method: 'Fuel combustion — activity × fuel factor', live: true },
    { scope: 'Scope 1', source: 'Coal', method: 'Mapped, but no factor is loaded yet — stays unresolved rather than estimated', live: false, note: 'Add a factor on the Emission Factors screen to activate' },
    { scope: 'Scope 1', source: 'Refrigerant leakage (R-22, R-134a, R-32)', method: 'Fugitive — leaked mass × GWP factor', live: true },
    { scope: 'Scope 2', source: 'Grid electricity', method: 'Location-based (grid average)', live: true, note: 'Market-based (supplier-specific) is planned -- every grid entry resolves location-based today' },
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
