import { DecimalPipe } from '@angular/common';
import { Component, Input, OnChanges, inject, signal } from '@angular/core';
import { IntensityApiService, IntensityOverview } from '../../../core/intensity-api.service';

interface IntensityMetric {
  label: string;
  current: number | null;
  prior: number | null;
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
        unit: `tCO2e/${denomUnit}`
      },
      {
        label: 'Energy consumption',
        current: (ov as any)[`energy_${suffix}`],
        prior: (ov as any)[`prior_energy_${suffix}`],
        unit: `GJ/${denomUnit}`
      },
      {
        label: 'Water withdrawal',
        current: (ov as any)[`water_${suffix}`],
        prior: (ov as any)[`prior_water_${suffix}`],
        unit: `KL/${denomUnit}`
      },
      {
        label: 'Waste generated',
        current: (ov as any)[`waste_${suffix}`],
        prior: (ov as any)[`prior_waste_${suffix}`],
        unit: `MT/${denomUnit}`
      }
    ];
  }

  comparisonLabel(current: number | null, prior: number | null): string {
    if (current === null) return 'Data required';
    if (prior === null || prior === 0) return 'No prior-period comparison';
    const pct = ((current - prior) / prior) * 100;
    return `${Math.abs(pct).toFixed(0)}% ${pct > 0 ? 'higher' : 'lower'} than last month`;
  }

  comparisonStatus(current: number | null, prior: number | null): 'green' | 'amber' | 'red' | 'neutral' {
    if (current === null || prior === null || prior === 0) return 'neutral';
    const pct = ((current - prior) / prior) * 100;
    if (pct <= 0) return 'green';
    if (pct <= 10) return 'amber';
    return 'red';
  }

  private trendMonths(): { period: string; label: string }[] {
    const [year, month] = this.period.split('-').map(Number);
    const months: { period: string; label: string }[] = [];
    for (let i = TREND_MONTHS - 1; i >= 0; i--) {
      const d = new Date(year, month - 1 - i, 1);
      const period = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-01`;
      const label = d.toLocaleDateString('en-US', { month: 'short' });
      months.push({ period, label });
    }
    return months;
  }

  async loadTrend(): Promise<void> {
    this.trendLoading.set(true);
    try {
      const months = this.trendMonths();
      const overviews = await Promise.all(
        months.map((m) => this.api.getOverview(m.period, this.locationId ?? undefined).catch(() => null))
      );
      const field = this.mode === 'production' ? 'ghg_per_production' : 'ghg_per_revenue';
      this.trendPoints.set(
        months.map((m, i) => ({ period: m.period, label: m.label, ghg: overviews[i] ? (overviews[i] as any)[field] : null }))
      );
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
