import { DecimalPipe } from '@angular/common';
import { Component, Input, OnChanges, inject, signal } from '@angular/core';
import { IntensityApiService, IntensityOverview, PeriodMode } from '../../../core/intensity-api.service';
import { CarbonOverviewComponent } from '../carbon-overview/carbon-overview.component';

interface AbsoluteMetric {
  label: string;
  current: number | null;
  prior: number | null;
  priorYear: number | null;
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
  @Input() periodMode: PeriodMode = 'month';

  loading = signal(true);
  errorMessage = signal('');
  overview = signal<IntensityOverview | null>(null);

  async ngOnChanges(): Promise<void> {
    this.loading.set(true);
    this.errorMessage.set('');
    try {
      this.overview.set(await this.api.getOverview(`${this.period}-01`, this.locationId ?? undefined, this.periodMode));
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
      { label: 'Total energy consumption', current: ov.energy_gj, prior: ov.prior_energy_gj, priorYear: ov.prior_year_energy_gj, unit: 'GJ', goodDown: true },
      { label: 'Total water withdrawal', current: ov.water_kl, prior: ov.prior_water_kl, priorYear: ov.prior_year_water_kl, unit: 'KL', goodDown: true },
      { label: 'Total waste generated', current: ov.waste_mt, prior: ov.prior_waste_mt, priorYear: ov.prior_year_waste_mt, unit: 'MT', goodDown: true },
      { label: 'Battery production', current: ov.production_mnah, prior: ov.prior_production_mnah, priorYear: ov.prior_year_production_mnah, unit: 'Mn Ah', goodDown: false },
      { label: 'Revenue', current: ov.revenue_inr_cr, prior: ov.prior_revenue_inr_cr, priorYear: ov.prior_year_revenue_inr_cr, unit: 'INR Cr', goodDown: false }
    ];
  }

  comparisonLabel(current: number | null, prior: number | null, against = 'last month'): string {
    if (current === null) return 'Not yet entered';
    if (prior === null || prior === 0) return `No comparison available`;
    const pct = ((current - prior) / prior) * 100;
    return `${Math.abs(pct).toFixed(0)}% ${pct > 0 ? 'higher' : 'lower'} than ${against}`;
  }

  comparisonStatus(current: number | null, prior: number | null, goodDown: boolean): 'green' | 'amber' | 'red' | 'neutral' {
    if (current === null || prior === null || prior === 0) return 'neutral';
    const pct = ((current - prior) / prior) * 100;
    const favorable = goodDown ? pct <= 0 : pct >= 0;
    if (favorable) return 'green';
    return Math.abs(pct) <= 10 ? 'amber' : 'red';
  }
}
