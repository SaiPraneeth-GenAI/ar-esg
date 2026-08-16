import { DecimalPipe } from '@angular/common';
import { Component, Input, OnChanges, inject, signal } from '@angular/core';
import { IntensityApiService, IntensityOverview } from '../../../core/intensity-api.service';

interface IntensityMetric {
  label: string;
  current: number | null;
  prior: number | null;
  priorYear: number | null;
  unit: string;
}

interface TrendPoint {
  period: string;
  label: string;
  ghg: number | null;
}

const TREND_MONTHS = 6;

@Component({
  selector: 'app-intensity-view',
  standalone: true,
  imports: [DecimalPipe],
  templateUrl: './intensity-view.component.html',
  styleUrl: './intensity-view.component.css'
})
export class IntensityViewComponent implements OnChanges {
  private api = inject(IntensityApiService);

  @Input({ required: true }) mode!: 'production' | 'revenue';
  @Input({ required: true }) period!: string;
  @Input() locationId: string | null = null;

  loading = signal(true);
  errorMessage = signal('');
  overview = signal<IntensityOverview | null>(null);
  trendPoints = signal<TrendPoint[]>([]);
  trendLoading = signal(true);

  async ngOnChanges(): Promise<void> {
    await Promise.all([this.load(), this.loadTrend()]);
  }

  async load(): Promise<void> {
    this.loading.set(true);
    this.errorMessage.set('');
    try {
      this.overview.set(await this.api.getOverview(`${this.period}-01`, this.locationId ?? undefined));
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
        unit: `tCO2e/${denomUnit}`
      },
      {
        label: 'Energy consumption',
        current: (ov as any)[`energy_${suffix}`],
        prior: (ov as any)[`prior_energy_${suffix}`],
        priorYear: (ov as any)[`prior_year_energy_${suffix}`],
        unit: `GJ/${denomUnit}`
      },
      {
        label: 'Water withdrawal',
        current: (ov as any)[`water_${suffix}`],
        prior: (ov as any)[`prior_water_${suffix}`],
        priorYear: (ov as any)[`prior_year_water_${suffix}`],
        unit: `KL/${denomUnit}`
      },
      {
        label: 'Waste generated',
        current: (ov as any)[`waste_${suffix}`],
        prior: (ov as any)[`prior_waste_${suffix}`],
        priorYear: (ov as any)[`prior_year_waste_${suffix}`],
        unit: `MT/${denomUnit}`
      }
    ];
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
      const points = await this.api.getTrend(`${this.period}-01`, TREND_MONTHS, this.locationId ?? undefined);
      this.trendPoints.set(
        points.map((p) => ({
          period: p.period,
          label: new Date(`${p.period}T00:00:00`).toLocaleDateString('en-US', { month: 'short' }),
          ghg: this.mode === 'production' ? p.ghg_per_production : p.ghg_per_revenue
        }))
      );
    } catch {
      this.trendPoints.set([]);
    } finally {
      this.trendLoading.set(false);
    }
  }

  barHeightPct(value: number | null): number {
    if (value === null) return 0;
    const series = this.trendPoints().map((p) => p.ghg);
    const max = Math.max(...series.filter((v): v is number => v !== null), 0.0001);
    return Math.max((value / max) * 100, 2);
  }
}
