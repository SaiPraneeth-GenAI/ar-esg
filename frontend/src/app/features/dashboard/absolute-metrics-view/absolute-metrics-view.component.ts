import { DecimalPipe } from '@angular/common';
import { Component, Input, OnChanges, inject, signal } from '@angular/core';
import { IntensityApiService, IntensityOverview } from '../../../core/intensity-api.service';
import { CarbonOverviewComponent } from '../carbon-overview/carbon-overview.component';

interface AbsoluteMetric {
  label: string;
  current: number | null;
  prior: number | null;
  unit: string;
  goodDown: boolean;
}

@Component({
  selector: 'app-absolute-metrics-view',
  standalone: true,
  imports: [DecimalPipe, CarbonOverviewComponent],
  templateUrl: './absolute-metrics-view.component.html',
  styleUrl: './absolute-metrics-view.component.css'
})
export class AbsoluteMetricsViewComponent implements OnChanges {
  private api = inject(IntensityApiService);

  @Input({ required: true }) period!: string;
  @Input() locationId: string | null = null;

  loading = signal(true);
  errorMessage = signal('');
  overview = signal<IntensityOverview | null>(null);

  async ngOnChanges(): Promise<void> {
    this.loading.set(true);
    this.errorMessage.set('');
    try {
      this.overview.set(await this.api.getOverview(`${this.period}-01`, this.locationId ?? undefined));
    } catch {
      this.errorMessage.set('Could not load absolute totals.');
    } finally {
      this.loading.set(false);
    }
  }

  metrics(): AbsoluteMetric[] {
    const ov = this.overview();
    if (!ov) return [];
    return [
      { label: 'Total energy consumption', current: ov.energy_gj, prior: ov.prior_energy_gj, unit: 'GJ', goodDown: true },
      { label: 'Total water withdrawal', current: ov.water_kl, prior: ov.prior_water_kl, unit: 'KL', goodDown: true },
      { label: 'Total waste generated', current: ov.waste_mt, prior: ov.prior_waste_mt, unit: 'MT', goodDown: true },
      { label: 'Battery production', current: ov.production_mnah, prior: ov.prior_production_mnah, unit: 'Mn Ah', goodDown: false },
      { label: 'Revenue', current: ov.revenue_inr_cr, prior: ov.prior_revenue_inr_cr, unit: 'INR Cr', goodDown: false }
    ];
  }

  comparisonLabel(m: AbsoluteMetric): string {
    if (m.current === null) return 'Not yet entered';
    if (m.prior === null || m.prior === 0) return 'No prior-period comparison';
    const pct = ((m.current - m.prior) / m.prior) * 100;
    return `${Math.abs(pct).toFixed(0)}% ${pct > 0 ? 'higher' : 'lower'} than last month`;
  }

  comparisonStatus(m: AbsoluteMetric): 'green' | 'amber' | 'red' | 'neutral' {
    if (m.current === null || m.prior === null || m.prior === 0) return 'neutral';
    const pct = ((m.current - m.prior) / m.prior) * 100;
    const favorable = m.goodDown ? pct <= 0 : pct >= 0;
    if (favorable) return 'green';
    return Math.abs(pct) <= 10 ? 'amber' : 'red';
  }
}
