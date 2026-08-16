import { DecimalPipe } from '@angular/common';
import { Component, Input, OnChanges, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { CarbonApiService, CarbonOverview, CarbonOverviewSource, EmissionCalculationOut } from '../../../core/carbon-api.service';
import { EntryHistoryComponent } from '../../data-entry/entry-history/entry-history.component';

function sourceKey(s: CarbonOverviewSource): string {
  return `${s.data_point_name}:${s.scope}:${s.calculation_method ?? ''}`;
}

export interface TrendPoint {
  period: string;
  label: string;
  scope12: number | null;
  intensity: number | null;
}

const TREND_MONTHS = 6;

@Component({
  selector: 'app-carbon-overview',
  standalone: true,
  imports: [DecimalPipe, RouterLink, EntryHistoryComponent],
  templateUrl: './carbon-overview.component.html',
  styleUrl: './carbon-overview.component.css'
})
export class CarbonOverviewComponent implements OnChanges {
  private api = inject(CarbonApiService);

  @Input({ required: true }) period!: string;
  @Input() locationId: string | null = null;

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

  trendPoints = signal<TrendPoint[]>([]);
  trendLoading = signal(true);

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
      this.overview.set(await this.api.getOverview(this.periodIso(), this.locationId ?? undefined));
    } catch {
      this.errorMessage.set('Could not load the carbon overview.');
    } finally {
      this.loading.set(false);
    }
  }

  async loadTrend(): Promise<void> {
    this.trendLoading.set(true);
    try {
      const points = await this.api.getTrend(this.periodIso(), TREND_MONTHS, this.locationId ?? undefined);
      this.trendPoints.set(
        points.map((p) => ({
          period: p.period,
          label: new Date(`${p.period}T00:00:00`).toLocaleDateString('en-US', { month: 'short' }),
          scope12: p.scope1_2_location_based_tco2e,
          intensity: p.intensity_tco2e_per_mnah
        }))
      );
    } catch {
      this.trendPoints.set([]);
    } finally {
      this.trendLoading.set(false);
    }
  }

  barHeightPct(value: number | null, series: (number | null)[]): number {
    if (value === null) return 0;
    const max = Math.max(...series.filter((v): v is number => v !== null), 0.0001);
    return Math.max((value / max) * 100, 2);
  }

  scope12Series(): (number | null)[] {
    return this.trendPoints().map((p) => p.scope12);
  }

  intensitySeries(): (number | null)[] {
    return this.trendPoints().map((p) => p.intensity);
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
          locationId: this.locationId ?? undefined
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
