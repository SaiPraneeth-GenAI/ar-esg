import { DecimalPipe } from '@angular/common';
import { Component, Input, OnChanges, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { CarbonApiService, CarbonOverview, CarbonOverviewSource, EmissionCalculationOut } from '../../../core/carbon-api.service';
import { PeriodMode, formatBucketLabel, priorPeriodLabel, priorYearLabel, showsPriorPeriod } from '../../../core/intensity-api.service';
import { PieChartComponent, PieSlice } from '../../../shared/pie-chart/pie-chart.component';
import { ChartPoint, ChartSeriesDef, RichTrendChartComponent } from '../../../shared/rich-trend-chart/rich-trend-chart.component';
import { EntryHistoryComponent } from '../../data-entry/entry-history/entry-history.component';

function sourceKey(s: CarbonOverviewSource): string {
  return `${s.data_point_name}:${s.scope}:${s.calculation_method ?? ''}`;
}

const TREND_MONTHS = 6;

const GHG_SERIES: ChartSeriesDef[] = [
  { key: 'scope1_2', label: 'Scope 1+2 (location-based)', unit: 'tCO2e', tracked: true },
  { key: 'scope1', label: 'Scope 1', unit: 'tCO2e', tracked: true },
  { key: 'scope2', label: 'Scope 2 (location-based)', unit: 'tCO2e', tracked: true },
  { key: 'scope3', label: 'Scope 3', unit: 'tCO2e', tracked: false },
  { key: 'intensity', label: 'Specific GHG emissions', unit: 'tCO2e/MnAh', tracked: true }
];

@Component({
  selector: 'app-carbon-overview',
  standalone: true,
  imports: [DecimalPipe, RouterLink, EntryHistoryComponent, RichTrendChartComponent, PieChartComponent],
  templateUrl: './carbon-overview.component.html',
  styleUrl: './carbon-overview.component.css'
})
export class CarbonOverviewComponent implements OnChanges {
  private api = inject(CarbonApiService);

  @Input({ required: true }) period!: string;
  @Input() locationId: string | null = null;
  @Input() periodMode: PeriodMode = 'month';

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

  sourceKey = sourceKey;

  async ngOnChanges(): Promise<void> {
    await Promise.all([this.load(), this.loadTrend()]);
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
            scope3: null,
            intensity: p.prior_year_intensity_tco2e_per_mnah
          }
        }))
      );
    } catch {
      this.trendPoints.set([]);
    } finally {
      this.trendLoading.set(false);
    }
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
    this.showUnresolved.set(!this.showUnresolved());
    this.expandedSourceKey.set(null);
    if (!this.showUnresolved()) return;
    this.unresolvedLoading.set(true);
    try {
      this.unresolvedItems.set(await this.api.getUnresolved(this.locationId ?? undefined));
    } finally {
      this.unresolvedLoading.set(false);
    }
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

  comparisonLabel(current: number | null, prior: number | null, against = 'last month'): string {
    if (current === null) return 'No data yet';
    if (prior === null || prior === 0) return `No comparison available`;
    const pct = ((current - prior) / prior) * 100;
    return `${Math.abs(pct).toFixed(0)}% ${pct > 0 ? 'higher' : 'lower'} than ${against}`;
  }

  comparisonStatus(current: number | null, prior: number | null): 'green' | 'amber' | 'red' | 'neutral' {
    if (current === null || prior === null || prior === 0) return 'neutral';
    const pct = ((current - prior) / prior) * 100;
    if (pct <= 0) return 'green';
    if (pct <= 10) return 'amber';
    return 'red';
  }

  targetStatusClass(status: string): string {
    switch (status) {
      case 'On track':
        return 'status-green';
      case 'Watch':
        return 'status-amber';
      case 'Off track':
        return 'status-red';
      default:
        return 'status-neutral';
    }
  }

  completenessStatus(pct: number | null): 'green' | 'amber' | 'red' | 'neutral' {
    if (pct === null) return 'neutral';
    if (pct >= 95) return 'green';
    if (pct >= 75) return 'amber';
    return 'red';
  }
}
