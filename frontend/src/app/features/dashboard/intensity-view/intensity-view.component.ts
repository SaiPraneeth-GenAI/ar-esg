import { DecimalPipe } from '@angular/common';
import { Component, Input, OnChanges, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { TargetComparison } from '../../../core/carbon-api.service';
import {
  IntensityApiService,
  IntensityOverview,
  PeriodMode,
  formatBucketLabel,
  priorPeriodLabel,
  priorYearLabel,
  showsPriorPeriod
} from '../../../core/intensity-api.service';
import { ChartPoint, ChartSeriesDef, RichTrendChartComponent } from '../../../shared/rich-trend-chart/rich-trend-chart.component';

interface IntensityMetric {
  label: string;
  current: number | null;
  prior: number | null;
  priorYear: number | null;
  unit: string;
  target: TargetComparison | null;
}

const TREND_MONTHS = 6;

@Component({
  selector: 'app-intensity-view',
  standalone: true,
  imports: [DecimalPipe, RouterLink, RichTrendChartComponent],
  templateUrl: './intensity-view.component.html',
  styleUrl: './intensity-view.component.css'
})
export class IntensityViewComponent implements OnChanges {
  private api = inject(IntensityApiService);

  @Input({ required: true }) mode!: 'production' | 'revenue';
  @Input({ required: true }) period!: string;
  @Input() locationId: string | null = null;
  @Input() periodMode: PeriodMode = 'month';

  loading = signal(true);
  errorMessage = signal('');
  overview = signal<IntensityOverview | null>(null);
  trendPoints = signal<ChartPoint[]>([]);
  trendLoading = signal(true);

  chartSeries(): ChartSeriesDef[] {
    const denomUnit = this.mode === 'production' ? 'Mn Ah' : 'INR Cr';
    // "per production"/"per revenue" is spelled out in the label itself
    // (not just implied by the unit) -- Production and Revenue tabs
    // otherwise show identically-named series ("GHG emissions") and it's
    // easy to lose track of which tab's chart is on screen.
    const context = this.mode === 'production' ? 'per production' : 'per revenue';
    return [
      { key: 'ghg', label: `GHG emissions (${context})`, unit: `tCO2e/${denomUnit}`, tracked: true },
      { key: 'energy', label: `Energy consumption (${context})`, unit: `GJ/${denomUnit}`, tracked: true },
      { key: 'water', label: `Water withdrawal (${context})`, unit: `KL/${denomUnit}`, tracked: true },
      { key: 'waste', label: `Waste generated (${context})`, unit: `MT/${denomUnit}`, tracked: true }
    ];
  }

  async ngOnChanges(): Promise<void> {
    await Promise.all([this.load(), this.loadTrend()]);
  }

  async load(): Promise<void> {
    this.loading.set(true);
    this.errorMessage.set('');
    try {
      this.overview.set(await this.api.getOverview(`${this.period}-01`, this.locationId ?? undefined, this.periodMode));
    } catch {
      this.errorMessage.set('Could not load intensity data.');
    } finally {
      this.loading.set(false);
    }
  }

  denominatorLabel(): string {
    return this.mode === 'production' ? 'Battery production' : 'Revenue';
  }

  denominatorUnit(): string {
    return this.mode === 'production' ? 'Mn Ah' : 'INR Cr';
  }

  denominatorValue(): number | null {
    const ov = this.overview();
    if (!ov) return null;
    return this.mode === 'production' ? ov.production_mnah : ov.revenue_inr_cr;
  }

  metrics(): IntensityMetric[] {
    const ov = this.overview();
    if (!ov) return [];
    const suffix = this.mode === 'production' ? 'per_production' : 'per_revenue';
    const denomUnit = this.mode === 'production' ? 'Mn Ah' : 'INR Cr';
    return [
      {
        label: 'GHG emissions',
        current: (ov as any)[`ghg_${suffix}`],
        prior: (ov as any)[`prior_ghg_${suffix}`],
        priorYear: (ov as any)[`prior_year_ghg_${suffix}`],
        unit: `tCO2e/${denomUnit}`,
        target: (ov as any)[`ghg_${suffix}_target`]
      },
      {
        label: 'Energy consumption',
        current: (ov as any)[`energy_${suffix}`],
        prior: (ov as any)[`prior_energy_${suffix}`],
        priorYear: (ov as any)[`prior_year_energy_${suffix}`],
        unit: `GJ/${denomUnit}`,
        target: (ov as any)[`energy_${suffix}_target`]
      },
      {
        label: 'Water withdrawal',
        current: (ov as any)[`water_${suffix}`],
        prior: (ov as any)[`prior_water_${suffix}`],
        priorYear: (ov as any)[`prior_year_water_${suffix}`],
        unit: `KL/${denomUnit}`,
        target: (ov as any)[`water_${suffix}_target`]
      },
      {
        label: 'Waste generated',
        current: (ov as any)[`waste_${suffix}`],
        prior: (ov as any)[`prior_waste_${suffix}`],
        priorYear: (ov as any)[`prior_year_waste_${suffix}`],
        unit: `MT/${denomUnit}`,
        target: (ov as any)[`waste_${suffix}_target`]
      }
    ];
  }

  cardTargetClass(target: TargetComparison | null): string {
    if (!target) return '';
    if (target.status === 'On track') return 'card-target-met';
    if (target.status === 'Watch' || target.status === 'Off track') return 'card-target-exceeded';
    return '';
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
    if (current === null) return 'Data required';
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

  async loadTrend(): Promise<void> {
    this.trendLoading.set(true);
    try {
      const points = await this.api.getTrend(`${this.period}-01`, TREND_MONTHS, this.locationId ?? undefined, this.periodMode);
      const suffix = this.mode === 'production' ? '_per_production' : '_per_revenue';
      this.trendPoints.set(
        points.map((p) => ({
          period: p.period,
          label: formatBucketLabel(p.bucket_start ?? p.period, p.bucket_end ?? p.period, this.periodMode),
          valuesBySeries: {
            ghg: (p as any)[`ghg${suffix}`],
            energy: (p as any)[`energy${suffix}`],
            water: (p as any)[`water${suffix}`],
            waste: (p as any)[`waste${suffix}`]
          },
          priorYearValuesBySeries: {
            ghg: (p as any)[`prior_year_ghg${suffix}`],
            energy: (p as any)[`prior_year_energy${suffix}`],
            water: (p as any)[`prior_year_water${suffix}`],
            waste: (p as any)[`prior_year_waste${suffix}`]
          },
          targetValuesBySeries: {
            ghg: (p as any)[`target_ghg${suffix}`],
            energy: (p as any)[`target_energy${suffix}`],
            water: (p as any)[`target_water${suffix}`],
            waste: (p as any)[`target_waste${suffix}`]
          }
        }))
      );
    } catch {
      this.trendPoints.set([]);
    } finally {
      this.trendLoading.set(false);
    }
  }
}
