import { DecimalPipe } from '@angular/common';
import { Component, ElementRef, Input, OnChanges, SimpleChanges, ViewChild, inject, signal } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { CarbonApiService, CarbonOverview, CarbonOverviewSource, EmissionCalculationOut, TargetComparison, TargetStatusOut } from '../../../core/carbon-api.service';
import { PeriodMode, formatBucketLabel, priorPeriodLabel, priorYearLabel, showsPriorPeriod } from '../../../core/intensity-api.service';
import { PieChartComponent, PieSlice } from '../../../shared/pie-chart/pie-chart.component';
import { ChartPoint, ChartSeriesDef, RichTrendChartComponent } from '../../../shared/rich-trend-chart/rich-trend-chart.component';
import { EntryHistoryComponent } from '../../data-entry/entry-history/entry-history.component';

function sourceKey(s: CarbonOverviewSource): string {
  return `${s.data_point_name}:${s.scope}:${s.calculation_method ?? ''}`;
}

const TREND_MONTHS = 6;

export type TargetHealth = 'on' | 'off' | 'pending';
export type TargetFilter = 'all' | TargetHealth;

interface TargetGroupDef {
  id: string;
  title: string;
  keys: string[];
}

/** How the tracker groups targets -- by what a sustainability lead manages,
 * not by the order the API happens to return them in. */
const TARGET_GROUPS: TargetGroupDef[] = [
  { id: 'ghg', title: 'GHG emissions', keys: ['scope1_2_tco2e', 'scope1_tco2e', 'scope2_tco2e', 'scope3_tco2e'] },
  {
    id: 'intensity',
    title: 'Efficiency & intensity',
    keys: [
      'ghg_intensity_production', 'energy_per_production', 'water_per_production', 'waste_per_production',
      'ghg_per_revenue', 'energy_per_revenue', 'water_per_revenue', 'waste_per_revenue'
    ]
  },
  { id: 'resources', title: 'Energy, water & waste', keys: ['energy_absolute', 'water_absolute', 'waste_absolute', 'production_absolute'] },
  { id: 'safety', title: 'Safety', keys: ['safety_fatality', 'safety_ltifr', 'safety_near_miss', 'safety_unsafe', 'safety_training'] }
];

/** Metrics where beating the goal means going ABOVE it (mirrors the
 * backend's HIGHER_IS_BETTER_KEYS). */
const HIGHER_IS_BETTER = new Set(['production_absolute', 'safety_training']);

export interface TrackedTarget {
  target: TargetStatusOut;
  health: TargetHealth;
  sublabel: string | null;
  /** Signed headroom as a % of the goal: positive = better than goal. */
  headroomPct: number | null;
  headroomText: string;
  /** Bullet-bar geometry: actual fill and goal tick, as % of a shared scale. */
  fillPct: number;
  goalPct: number;
}

export interface TrackedGroup {
  id: string;
  title: string;
  items: TrackedTarget[];
  onTrack: number;
  total: number;
}

export interface FootprintSegment {
  key: 'scope1' | 'scope2' | 'scope3';
  label: string;
  value: number;
  pct: number;
}

const GHG_SERIES: ChartSeriesDef[] = [
  { key: 'scope1_2', label: 'Scope 1+2 (location-based)', unit: 'tCO2e', tracked: true },
  { key: 'scope1', label: 'Scope 1', unit: 'tCO2e', tracked: true },
  { key: 'scope2', label: 'Scope 2 (location-based)', unit: 'tCO2e', tracked: true },
  { key: 'scope3', label: 'Scope 3 (value chain)', unit: 'tCO2e', tracked: true },
  { key: 'intensity', label: 'Specific GHG emissions', unit: 'tCO2e/MnAh', tracked: true }
];

/** Which Calculations flow-diagram node(s) a given card's figure is built
 * from -- lets a click jump straight to that node's slice of the diagram
 * instead of leaving the customer to hunt for it themselves. */
const FLOW_NODES_BY_CARD: Record<string, string[]> = {
  scope1_2: ['scope1-total', 'scope2-total'],
  scope1: ['scope1-total'],
  scope2: ['scope2-total'],
  intensity: ['intensity-production']
};

@Component({
  selector: 'app-carbon-overview',
  standalone: true,
  imports: [DecimalPipe, RouterLink, EntryHistoryComponent, RichTrendChartComponent, PieChartComponent],
  templateUrl: './carbon-overview.component.html',
  styleUrl: './carbon-overview.component.css'
})
export class CarbonOverviewComponent implements OnChanges {
  private api = inject(CarbonApiService);
  private router = inject(Router);

  @Input({ required: true }) period!: string;
  @Input() locationId: string | null = null;
  @Input() periodMode: PeriodMode = 'month';
  @Input() unresolvedRequestId = 0;
  @ViewChild('unresolvedPanel') unresolvedPanelRef?: ElementRef<HTMLElement>;

  loading = signal(true);
  errorMessage = signal('');
  overview = signal<CarbonOverview | null>(null);

  expandedSourceKey = signal<string | null>(null);
  sourceCalculations = signal<EmissionCalculationOut[]>([]);
  sourceLoading = signal(false);
  expandedEntryId = signal<string | null>(null);

  showUnresolved = signal(false);
  unresolvedItems = signal<EmissionCalculationOut[]>([]);
  unresolvedLoading = signal(false);

  trendPoints = signal<ChartPoint[]>([]);
  trendLoading = signal(true);
  ghgSeries = GHG_SERIES;

  scopeFilter = signal<number>(1);
  targetFilter = signal<TargetFilter>('all');

  sourceKey = sourceKey;

  aiInsightTyped = signal('');
  aiInsightBusy = signal(false); // true while fetching AND while the typewriter is still revealing text
  private aiInsightGeneration = 0;
  private typeTimer: ReturnType<typeof setInterval> | null = null;

  async ngOnChanges(changes: SimpleChanges): Promise<void> {
    const dataInputsChanged = !!(changes['period'] || changes['locationId'] || changes['periodMode']);
    const unresolvedTriggered = !!changes['unresolvedRequestId'] && !changes['unresolvedRequestId'].firstChange && this.unresolvedRequestId > 0;

    if (dataInputsChanged) {
      await Promise.all([this.load(), this.loadTrend()]);
      this.loadAiInsight();
    }
    if (unresolvedTriggered) {
      await this.openUnresolved();
    }
  }

  private periodIso(): string {
    return `${this.period}-01`;
  }

  async load(): Promise<void> {
    this.loading.set(true);
    this.errorMessage.set('');
    this.expandedSourceKey.set(null);
    this.showUnresolved.set(false);
    try {
      this.overview.set(await this.api.getOverview(this.periodIso(), this.locationId ?? undefined, this.periodMode));
      const scopes = this.availableScopes();
      if (scopes.length > 0 && !scopes.includes(this.scopeFilter())) {
        this.scopeFilter.set(scopes[0]);
      }
    } catch {
      this.errorMessage.set('Could not load the carbon overview.');
    } finally {
      this.loading.set(false);
    }
  }

  // -- Contributor pies -----------------------------------------------
  // Both read straight from overview().sources, which already reflects
  // the selected period_mode range -- no separate fetch, and the pies
  // update the instant Monthly/Quarterly/YTD or the period changes.
  // Market-based Scope 2 rows are excluded from both so the slices sum to
  // the same location-based total the headline cards show.

  private locationBasedSources(): CarbonOverviewSource[] {
    return (this.overview()?.sources ?? []).filter((s) => s.calculation_method !== 'market_based');
  }

  private groupByDataPoint(sources: CarbonOverviewSource[]): PieSlice[] {
    const byName = new Map<string, number>();
    for (const s of sources) {
      byName.set(s.data_point_name, (byName.get(s.data_point_name) ?? 0) + s.emissions_tco2e);
    }
    return Array.from(byName.entries()).map(([label, value]) => ({ label, value }));
  }

  totalContributionSlices(): PieSlice[] {
    return this.groupByDataPoint(this.locationBasedSources());
  }

  scopeContributionSlices(): PieSlice[] {
    return this.groupByDataPoint(this.locationBasedSources().filter((s) => s.scope === this.scopeFilter()));
  }

  availableScopes(): number[] {
    const scopes = new Set(this.locationBasedSources().map((s) => s.scope));
    return Array.from(scopes).sort();
  }

  // -- Source breakdown, ranked bars ------------------------------------
  // A plain table of numbers doesn't show which source dominates at a
  // glance; a ranked bar makes the magnitude visible while keeping every
  // number (and the click-to-drill-down evidence) the table already had.

  sortedSources(): CarbonOverviewSource[] {
    return [...(this.overview()?.sources ?? [])].sort((a, b) => b.emissions_tco2e - a.emissions_tco2e);
  }

  private maxSourceValue(): number {
    const values = this.sortedSources().map((s) => s.emissions_tco2e);
    return Math.max(...values, 0.0001);
  }

  sourceBarPct(source: CarbonOverviewSource): number {
    return Math.max((source.emissions_tco2e / this.maxSourceValue()) * 100, 2);
  }

  setScopeFilter(scope: number): void {
    this.scopeFilter.set(scope);
  }

  async loadTrend(): Promise<void> {
    this.trendLoading.set(true);
    try {
      const points = await this.api.getTrend(this.periodIso(), TREND_MONTHS, this.locationId ?? undefined, this.periodMode);
      this.trendPoints.set(
        points.map((p) => ({
          period: p.period,
          label: formatBucketLabel(p.bucket_start ?? p.period, p.bucket_end ?? p.period, this.periodMode),
          valuesBySeries: {
            scope1_2: p.scope1_2_location_based_tco2e,
            scope1: p.scope1_tco2e,
            scope2: p.scope2_location_based_tco2e,
            scope3: p.scope3_tco2e,
            intensity: p.intensity_tco2e_per_mnah
          },
          priorYearValuesBySeries: {
            scope1_2: p.prior_year_scope1_2_location_based_tco2e,
            scope1: p.prior_year_scope1_tco2e,
            scope2: p.prior_year_scope2_location_based_tco2e,
            scope3: p.prior_year_scope3_tco2e,
            intensity: p.prior_year_intensity_tco2e_per_mnah
          },
          targetValuesBySeries: {
            scope1_2: p.target_scope1_2_location_based_tco2e,
            scope1: p.target_scope1_tco2e,
            scope2: p.target_scope2_location_based_tco2e,
            scope3: p.target_scope3_tco2e,
            intensity: p.target_intensity_tco2e_per_mnah
          }
        }))
      );
    } catch {
      this.trendPoints.set([]);
    } finally {
      this.trendLoading.set(false);
    }
  }

  // -- AI insight, typed in like a chat reply -----------------------------
  // Fetched separately from the overview (never blocks the main dashboard
  // load, since an OpenAI call can take a few seconds) and revealed with a
  // typewriter effect once it arrives. A generation counter guards against
  // a stale response finishing its typing after the user has already moved
  // to a different period/location.

  async loadAiInsight(): Promise<void> {
    const generation = ++this.aiInsightGeneration;
    if (this.typeTimer) {
      clearInterval(this.typeTimer);
      this.typeTimer = null;
    }
    this.aiInsightTyped.set('');
    this.aiInsightBusy.set(true);
    try {
      const { insight } = await this.api.getAiInsight(this.periodIso(), this.locationId ?? undefined, this.periodMode);
      if (generation !== this.aiInsightGeneration) return;
      if (!insight) {
        this.aiInsightBusy.set(false);
        return;
      }
      this.typeOut(insight);
    } catch {
      // Silent -- the rule-based `overview()!.insight` sentence stays shown.
      if (generation === this.aiInsightGeneration) this.aiInsightBusy.set(false);
    }
  }

  private typeOut(text: string): void {
    const generation = this.aiInsightGeneration;
    let i = 0;
    this.typeTimer = setInterval(() => {
      if (generation !== this.aiInsightGeneration) {
        clearInterval(this.typeTimer!);
        return;
      }
      i += 2;
      this.aiInsightTyped.set(text.slice(0, i));
      if (i >= text.length) {
        clearInterval(this.typeTimer!);
        this.typeTimer = null;
        this.aiInsightBusy.set(false);
      }
    }, 18);
  }

  async toggleSource(source: CarbonOverviewSource): Promise<void> {
    const key = sourceKey(source);
    if (this.expandedSourceKey() === key) {
      this.expandedSourceKey.set(null);
      return;
    }
    this.expandedSourceKey.set(key);
    this.expandedEntryId.set(null);
    this.sourceLoading.set(true);
    try {
      this.sourceCalculations.set(
        await this.api.getCalculations(this.periodIso(), {
          scope: source.scope,
          calculationMethod: source.calculation_method ?? undefined,
          dataPointName: source.data_point_name,
          locationId: this.locationId ?? undefined,
          periodMode: this.periodMode
        })
      );
    } finally {
      this.sourceLoading.set(false);
    }
  }

  toggleEntryHistory(entryId: string): void {
    this.expandedEntryId.set(this.expandedEntryId() === entryId ? null : entryId);
  }

  async toggleUnresolved(): Promise<void> {
    if (this.showUnresolved()) {
      this.showUnresolved.set(false);
      return;
    }
    await this.openUnresolved();
  }

  /** Forces the panel open (vs. toggleUnresolved(), which flips it) and
   * scrolls it into view -- used by the dashboard header's unresolved
   * badge, which can be clicked from anywhere on the page, including
   * while the panel is already open and off-screen. */
  async openUnresolved(): Promise<void> {
    this.showUnresolved.set(true);
    this.expandedSourceKey.set(null);
    this.unresolvedLoading.set(true);
    try {
      this.unresolvedItems.set(await this.api.getUnresolved(this.locationId ?? undefined));
    } finally {
      this.unresolvedLoading.set(false);
    }
    setTimeout(() => this.unresolvedPanelRef?.nativeElement.scrollIntoView({ behavior: 'smooth', block: 'start' }), 50);
  }

  formatMonth(period: string | null): string {
    if (!period) return '';
    return new Date(`${period}T00:00:00`).toLocaleDateString('en-US', { month: 'long', year: 'numeric' });
  }

  formatRangeLabel(ov: CarbonOverview): string {
    if (ov.period_mode === 'month' || !ov.period_start || !ov.period_end) return this.formatMonth(ov.period);
    const start = new Date(`${ov.period_start}T00:00:00`);
    const end = new Date(`${ov.period_end}T00:00:00`);
    const startLabel = start.toLocaleDateString('en-US', { month: 'short' });
    const endLabel = end.toLocaleDateString('en-US', { month: 'short', year: 'numeric' });
    const prefix = ov.period_mode === 'ytd' ? 'YTD' : 'Quarter-to-date';
    return `${prefix}: ${startLabel} – ${endLabel}`;
  }

  priorLabel(): string {
    return priorPeriodLabel(this.periodMode);
  }

  priorYearLabelText(): string {
    return priorYearLabel(this.periodMode);
  }

  showPrior(): boolean {
    return showsPriorPeriod(this.periodMode);
  }

  comparisonLabel(current: number | null, prior: number | null, against = 'last month', unit = 'tCO2e'): string {
    if (current === null) return 'No data yet';
    if (prior === null) return `No comparison available`;
    const fractionDigits = unit.includes('/') ? 3 : 2;
    return `${prior.toFixed(fractionDigits)} ${unit} during ${against}`;
  }

  comparisonStatus(current: number | null, prior: number | null): 'green' | 'amber' | 'red' | 'neutral' {
    if (current === null || prior === null || prior === 0) return 'neutral';
    const pct = ((current - prior) / prior) * 100;
    if (pct <= 0) return 'green';
    if (pct <= 10) return 'amber';
    return 'red';
  }

  /** Jumps to the Calculations page with the exact node(s) this card's
   * figure comes from highlighted, and the same period/site carried over --
   * so "how was this number built" is one click, not a hunt through the
   * whole diagram. */
  goToFlowDiagram(cardKey: keyof typeof FLOW_NODES_BY_CARD): void {
    const nodes = FLOW_NODES_BY_CARD[cardKey];
    if (!nodes) return;
    this.router.navigate(['/admin/methodology'], {
      queryParams: {
        nodes: nodes.join(','),
        period: this.periodIso(),
        periodMode: this.periodMode,
        locationId: this.locationId || undefined
      }
    });
  }

  targetStatusClass(status: string): string {
    switch (status) {
      case 'Within safe limits':
        return 'status-green';
      case 'Exceeded':
        return 'status-red';
      default:
        return 'status-neutral';
    }
  }

  /** The whole card is colored by target status, not a small dot. A target
   * is either within its limit or exceeded; unavailable target states stay
   * neutral because there is nothing to judge yet. */
  cardTargetClass(target: TargetComparison | null | undefined): string {
    if (!target) return '';
    if (target.status === 'Within safe limits') return 'card-target-met';
    if (target.status === 'Exceeded') return 'card-target-exceeded';
    return '';
  }

  // -- Total footprint band ------------------------------------------------

  footprintSegments(): FootprintSegment[] {
    const ov = this.overview();
    if (!ov) return [];
    const parts = [
      { key: 'scope1' as const, label: 'Scope 1 · Direct', value: ov.scope1_tco2e ?? 0 },
      { key: 'scope2' as const, label: 'Scope 2 · Purchased energy', value: ov.scope2_location_based_tco2e ?? 0 },
      { key: 'scope3' as const, label: 'Scope 3 · Value chain', value: ov.scope3_tco2e ?? 0 }
    ];
    const total = parts.reduce((sum, p) => sum + p.value, 0);
    if (total <= 0) return [];
    return parts.map((p) => ({ ...p, pct: (p.value / total) * 100 }));
  }

  private priorFootprint(): number | null {
    const ov = this.overview();
    if (!ov) return null;
    const parts = [ov.prior_scope1_2_location_based_tco2e, ov.prior_scope3_tco2e].filter((v): v is number => v !== null);
    return parts.length ? parts.reduce((a, b) => a + b, 0) : null;
  }

  footprintDeltaPct(): number | null {
    const current = this.overview()?.total_scope1_2_3_tco2e ?? null;
    const prior = this.priorFootprint();
    if (current === null || prior === null || prior === 0) return null;
    return ((current - prior) / prior) * 100;
  }

  scope3SourceCount(): number {
    return (this.overview()?.sources ?? []).filter((src) => src.scope === 3).length;
  }

  absPct(value: number): number {
    return Math.abs(value);
  }

  // -- Target tracker ---------------------------------------------------------

  private targetHealth(t: TargetStatusOut): TargetHealth {
    if (t.status === 'Within safe limits') return 'on';
    if (t.status === 'Exceeded') return 'off';
    return 'pending';
  }

  private trackTarget(t: TargetStatusOut): TrackedTarget {
    const health = this.targetHealth(t);
    const higherIsBetter = HIGHER_IS_BETTER.has(t.metric_key);
    let headroomPct: number | null = null;
    let headroomText = "Awaiting this period's data";
    if (t.actual !== null) {
      if (t.target_value === 0) {
        headroomPct = t.actual === 0 ? 0 : -100;
        headroomText = t.actual === 0 ? 'Held at zero' : `${t.actual} recorded vs a zero goal`;
      } else {
        const raw = ((t.target_value - t.actual) / Math.abs(t.target_value)) * 100;
        headroomPct = higherIsBetter ? -raw : raw;
        const size = Math.abs(headroomPct);
        const magnitude = size.toFixed(size < 10 ? 1 : 0);
        if (higherIsBetter) {
          headroomText = headroomPct >= 0 ? `${magnitude}% ahead of goal` : `${magnitude}% short of goal`;
        } else {
          headroomText = headroomPct >= 0 ? `${magnitude}% under target` : `${magnitude}% over target`;
        }
      }
    }
    let sublabel: string | null = null;
    if (t.unit.endsWith('/MnAh')) sublabel = 'per Mn Ah produced';
    else if (t.unit.endsWith('/Cr')) sublabel = 'per ₹ crore revenue';
    // Shared scale with headroom so neither the fill nor the goal tick sits
    // flush against the end of the track.
    const scale = Math.max(t.target_value, t.actual ?? 0, 0.0001) * 1.2;
    const fillPct = t.actual === null ? 0 : Math.min((t.actual / scale) * 100, 100);
    const goalPct = Math.min((t.target_value / scale) * 100, 100);
    return { target: t, health, sublabel, headroomPct, headroomText, fillPct, goalPct };
  }

  private trackedTargets(): TrackedTarget[] {
    return (this.overview()?.all_targets ?? []).map((t) => this.trackTarget(t));
  }

  targetCounts(): Record<TargetHealth, number> {
    const counts: Record<TargetHealth, number> = { on: 0, off: 0, pending: 0 };
    for (const t of this.trackedTargets()) counts[t.health] += 1;
    return counts;
  }

  /** Share of targets with data this period that are on track. */
  targetScore(): number | null {
    const c = this.targetCounts();
    const judged = c.on + c.off;
    return judged > 0 ? Math.round((c.on / judged) * 100) : null;
  }

  /** stroke-dasharray for the score ring (r = 26). */
  scoreDash(): string {
    const circumference = 2 * Math.PI * 26;
    return `${((this.targetScore() ?? 0) / 100) * circumference} ${circumference}`;
  }

  setTargetFilter(filter: TargetFilter): void {
    this.targetFilter.set(this.targetFilter() === filter ? 'all' : filter);
  }

  trackedGroups(): TrackedGroup[] {
    const filter = this.targetFilter();
    const all = this.trackedTargets();
    const placed = new Set<string>();
    const groups: TrackedGroup[] = [];
    const build = (id: string, title: string, items: TrackedTarget[]) => {
      const visible = items
        .filter((i) => filter === 'all' || i.health === filter)
        // Furthest from goal first, so what needs attention leads each group.
        .sort((a, b) => (a.headroomPct ?? Infinity) - (b.headroomPct ?? Infinity));
      if (visible.length) {
        groups.push({ id, title, items: visible, onTrack: items.filter((i) => i.health === 'on').length, total: items.length });
      }
    };
    for (const def of TARGET_GROUPS) {
      const items = all.filter((i) => def.keys.includes(i.target.metric_key));
      items.forEach((i) => placed.add(i.target.target_id));
      build(def.id, def.title, items);
    }
    build('other', 'Other', all.filter((i) => !placed.has(i.target.target_id)));
    return groups;
  }

  formatTargetValue(value: number | null, unit: string): string {
    if (value === null) return '—';
    const digits = unit.includes('/') ? 3 : Math.abs(value) >= 100 ? 0 : 2;
    return value.toLocaleString('en-IN', { minimumFractionDigits: digits, maximumFractionDigits: digits });
  }

  completenessStatus(pct: number | null): 'green' | 'amber' | 'red' | 'neutral' {
    if (pct === null) return 'neutral';
    if (pct >= 95) return 'green';
    if (pct >= 75) return 'amber';
    return 'red';
  }
}
