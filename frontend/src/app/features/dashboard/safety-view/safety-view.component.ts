import { DecimalPipe } from '@angular/common';
import { Component, Input, OnChanges, inject, signal } from '@angular/core';
import { PeriodMode } from '../../../core/intensity-api.service';
import { SafetyApiService, SafetyMetric } from '../../../core/safety-api.service';
import { ChartPoint, ChartSeriesDef, RichTrendChartComponent } from '../../../shared/rich-trend-chart/rich-trend-chart.component';

// A metric is "good down" (fewer incidents is better) except training %,
// which is "good up" -- more people trained is better. Mirrors the
// context-aware trend-arrow coloring the reference report uses.
const GOOD_DOWN = new Set(['Fatality', 'LTIFR', 'Unsafe Conditions', 'Near Miss']);

const METRIC_UNITS: Record<string, string> = {
  Fatality: 'Nos',
  LTIFR: 'Rate',
  'Defensive Driving Training': '%',
  'Unsafe Conditions': 'Nos',
  'Near Miss': 'Nos'
};

const TREND_MONTHS = 6;

@Component({
  selector: 'app-safety-view',
  standalone: true,
  imports: [DecimalPipe, RichTrendChartComponent],
  templateUrl: './safety-view.component.html',
  styleUrl: './safety-view.component.css'
})
export class SafetyViewComponent implements OnChanges {
  private api = inject(SafetyApiService);

  @Input({ required: true }) period!: string;
  @Input() locationId: string | null = null;
  @Input() periodMode: PeriodMode = 'month';

  loading = signal(true);
  errorMessage = signal('');
  metrics = signal<SafetyMetric[]>([]);

  trendPoints = signal<ChartPoint[]>([]);
  trendLoading = signal(true);

  chartSeries(): ChartSeriesDef[] {
    return Object.entries(METRIC_UNITS).map(([name, unit]) => ({
      key: name,
      label: name,
      unit,
      tracked: true
    }));
  }

  async ngOnChanges(): Promise<void> {
    await Promise.all([this.load(), this.loadTrend()]);
  }

  async load(): Promise<void> {
    this.loading.set(true);
    this.errorMessage.set('');
    try {
      const ov = await this.api.getOverview(`${this.period}-01`, this.locationId ?? undefined, this.periodMode);
      this.metrics.set(ov.metrics);
    } catch {
      this.errorMessage.set('Could not load safety data.');
    } finally {
      this.loading.set(false);
    }
  }

  async loadTrend(): Promise<void> {
    this.trendLoading.set(true);
    try {
      const points = await this.api.getTrend(`${this.period}-01`, TREND_MONTHS, this.locationId ?? undefined);
      this.trendPoints.set(
        points.map((p) => ({
          period: p.period,
          label: new Date(`${p.period}T00:00:00`).toLocaleDateString('en-US', { month: 'short' }),
          valuesBySeries: p.values
        }))
      );
    } catch {
      this.trendPoints.set([]);
    } finally {
      this.trendLoading.set(false);
    }
  }

  comparisonLabel(m: SafetyMetric, against: 'month' | 'year' = 'month'): string {
    const prior = against === 'month' ? m.prior_value : m.prior_year_value;
    if (m.value === null) return 'Not yet entered';
    if (prior === null || prior === 0) return `No comparison available`;
    const pct = ((m.value - prior) / prior) * 100;
    return `${Math.abs(pct).toFixed(0)}% ${pct > 0 ? 'higher' : 'lower'} than last ${against}`;
  }

  comparisonStatus(m: SafetyMetric, against: 'month' | 'year' = 'month'): 'green' | 'amber' | 'red' | 'neutral' {
    const prior = against === 'month' ? m.prior_value : m.prior_year_value;
    if (m.value === null || prior === null || prior === 0) return 'neutral';
    const pct = ((m.value - prior) / prior) * 100;
    const goodDown = GOOD_DOWN.has(m.name);
    const favorable = goodDown ? pct <= 0 : pct >= 0;
    if (favorable) return 'green';
    return Math.abs(pct) <= 10 ? 'amber' : 'red';
  }
}
