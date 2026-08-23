import { Component, Input, OnChanges, inject, signal } from '@angular/core';
import { TargetComparison } from '../../../core/carbon-api.service';
import { IntensityApiService, IntensityOverview, PeriodMode } from '../../../core/intensity-api.service';
import { SafetyApiService, SafetyMetric } from '../../../core/safety-api.service';

type GroupKey = 'production' | 'safety' | 'revenue' | 'absolute';
type MetricState = 'green' | 'amber' | 'red' | 'neutral';

interface MatrixMetric {
  key: string;
  label: string;
  unit: string;
  priorYear: number | null;
  target: number | null;
  ytd: number | null;
  currentPeriod: number | null;
  goodDown: boolean;
}

interface MatrixGroup {
  key: GroupKey;
  title: string;
  kicker: string;
  accent: string;
  periodLabel: string;
  context: string | null;
  metrics: MatrixMetric[];
}

const SAFETY_GOOD_DOWN = new Set(['Fatality', 'LTIFR', 'Unsafe Conditions', 'Near Miss']);

@Component({
  selector: 'app-overall-view',
  standalone: true,
  templateUrl: './overall-view.component.html',
  styleUrl: './overall-view.component.css'
})
export class OverallViewComponent implements OnChanges {
  private intensityApi = inject(IntensityApiService);
  private safetyApi = inject(SafetyApiService);

  @Input({ required: true }) period!: string;
  @Input() locationId: string | null = null;
  @Input() periodMode: PeriodMode = 'month';

  loading = signal(true);
  errorMessage = signal('');
  monthOverview = signal<IntensityOverview | null>(null);
  quarterOverview = signal<IntensityOverview | null>(null);
  ytdOverview = signal<IntensityOverview | null>(null);
  monthSafety = signal<SafetyMetric[]>([]);
  ytdSafety = signal<SafetyMetric[]>([]);
  selectedMetric = signal<string | null>(null);

  async ngOnChanges(): Promise<void> {
    this.loading.set(true);
    this.errorMessage.set('');
    // The executive matrix is a fixed operating scorecard, not another
    // rendering of the dashboard's Monthly / Quarterly / YTD selector.
    // It always compares the live current month and quarter with current-
    // year YTD, while the selected site remains an applicable boundary.
    const anchor = `${this.currentPeriod()}-01`;
    const location = this.locationId ?? undefined;
    try {
      const [month, quarter, ytd, safetyMonth, safetyYtd] = await Promise.all([
        this.intensityApi.getOverview(anchor, location, 'month'),
        this.intensityApi.getOverview(anchor, location, 'quarter'),
        this.intensityApi.getOverview(anchor, location, 'ytd'),
        this.safetyApi.getOverview(anchor, location, 'month'),
        this.safetyApi.getOverview(anchor, location, 'ytd')
      ]);
      this.monthOverview.set(month);
      this.quarterOverview.set(quarter);
      this.ytdOverview.set(ytd);
      this.monthSafety.set(safetyMonth.metrics);
      this.ytdSafety.set(safetyYtd.metrics);
    } catch {
      this.errorMessage.set('Could not load the executive performance matrix.');
    } finally {
      this.loading.set(false);
    }
  }

  groups(): MatrixGroup[] {
    const month = this.monthOverview();
    const quarter = this.quarterOverview();
    const ytd = this.ytdOverview();
    if (!month || !quarter || !ytd) return [];

    const targetValue = (comparison: TargetComparison | null): number | null => comparison?.target_value ?? null;
    const monthSafety = new Map(this.monthSafety().map((metric) => [metric.name, metric]));

    return [
      {
        key: 'production', title: 'Intensity by production', kicker: 'Environmental performance', accent: 'emerald',
        periodLabel: this.monthLabel(),
        context: month.production_mnah === null ? null : `${this.formatValue(month.production_mnah)} Mn Ah produced this month`,
        metrics: [
          this.metric('production-energy', 'Specific energy per battery production', 'GJ/Mn Ah', ytd.prior_year_energy_per_production, targetValue(ytd.energy_per_production_target), ytd.energy_per_production, month.energy_per_production, true),
          this.metric('production-ghg', 'Specific GHG emissions per battery production', 'tCO2e/Mn Ah', ytd.prior_year_ghg_per_production, targetValue(ytd.ghg_per_production_target), ytd.ghg_per_production, month.ghg_per_production, true),
          this.metric('production-water', 'Specific water per battery production', 'KL/Mn Ah', ytd.prior_year_water_per_production, targetValue(ytd.water_per_production_target), ytd.water_per_production, month.water_per_production, true),
          this.metric('production-waste', 'Specific waste per battery production', 'MT/Mn Ah', ytd.prior_year_waste_per_production, targetValue(ytd.waste_per_production_target), ytd.waste_per_production, month.waste_per_production, true)
        ]
      },
      {
        key: 'safety', title: 'Safety', kicker: 'People and operations', accent: 'blue', periodLabel: this.monthLabel(),
        context: 'Monthly operational safety scorecard',
        metrics: this.ytdSafety().map((metric) => {
          const monthly = monthSafety.get(metric.name);
          return this.metric(`safety-${metric.name.toLowerCase().replaceAll(' ', '-')}`, metric.name, metric.unit, metric.prior_year_value, targetValue(metric.target), metric.value, monthly?.value ?? null, SAFETY_GOOD_DOWN.has(metric.name));
        })
      },
      {
        key: 'revenue', title: 'Intensity by revenue', kicker: 'Environmental performance', accent: 'violet',
        periodLabel: this.quarterLabel(),
        context: quarter.revenue_inr_cr === null ? null : `${this.formatValue(quarter.revenue_inr_cr)} INR Cr revenue this quarter`,
        metrics: [
          this.metric('revenue-energy', 'Specific energy per revenue', 'GJ/INR Cr', ytd.prior_year_energy_per_revenue, targetValue(ytd.energy_per_revenue_target), ytd.energy_per_revenue, quarter.energy_per_revenue, true),
          this.metric('revenue-ghg', 'Specific GHG emissions per revenue', 'tCO2e/INR Cr', ytd.prior_year_ghg_per_revenue, targetValue(ytd.ghg_per_revenue_target), ytd.ghg_per_revenue, quarter.ghg_per_revenue, true),
          this.metric('revenue-water', 'Specific water per revenue', 'KL/INR Cr', ytd.prior_year_water_per_revenue, targetValue(ytd.water_per_revenue_target), ytd.water_per_revenue, quarter.water_per_revenue, true),
          this.metric('revenue-waste', 'Specific waste per revenue', 'MT/INR Cr', ytd.prior_year_waste_per_revenue, targetValue(ytd.waste_per_revenue_target), ytd.waste_per_revenue, quarter.waste_per_revenue, true)
        ]
      },
      {
        key: 'absolute', title: 'Absolute environmental performance', kicker: 'Environmental performance', accent: 'coral',
        periodLabel: this.monthLabel(), context: 'Consumption and footprint totals',
        metrics: [
          this.metric('absolute-energy', 'Total energy consumption', 'GJ', ytd.prior_year_energy_gj, targetValue(ytd.energy_absolute_target), ytd.energy_gj, month.energy_gj, true),
          this.metric('absolute-ghg', 'Total GHG emissions', 'tCO2e', ytd.prior_year_ghg_tco2e, targetValue(ytd.ghg_absolute_target), ytd.ghg_tco2e, month.ghg_tco2e, true),
          this.metric('absolute-water', 'Total water withdrawal', 'KL', ytd.prior_year_water_kl, targetValue(ytd.water_absolute_target), ytd.water_kl, month.water_kl, true),
          this.metric('absolute-waste', 'Total waste generated', 'MT', ytd.prior_year_waste_mt, targetValue(ytd.waste_absolute_target), ytd.waste_mt, month.waste_mt, true),
          this.metric('absolute-production', 'Battery production', 'Mn Ah', ytd.prior_year_production_mnah, targetValue(ytd.production_absolute_target), ytd.production_mnah, month.production_mnah, false)
        ]
      }
    ];
  }

  private metric(key: string, label: string, unit: string, priorYear: number | null, target: number | null, ytd: number | null, currentPeriod: number | null, goodDown: boolean): MatrixMetric {
    return { key, label, unit, priorYear, target, ytd, currentPeriod, goodDown };
  }

  allMetrics(): MatrixMetric[] { return this.groups().flatMap((group) => group.metrics); }
  targetCoverage(): number { return this.allMetrics().filter((metric) => metric.target !== null).length; }
  needsAttention(): number { return this.allMetrics().filter((metric) => ['amber', 'red'].includes(this.metricState(metric))).length; }
  withinTarget(): number { return this.allMetrics().filter((metric) => metric.target !== null && this.metricState(metric) === 'green').length; }

  priorityMetric(): MatrixMetric | null {
    const metrics = this.allMetrics().filter((metric) => metric.ytd !== null);
    return metrics.find((metric) => this.metricState(metric) === 'red') ?? metrics.find((metric) => this.metricState(metric) === 'amber') ?? null;
  }

  metricState(metric: MatrixMetric): MetricState {
    return this.metricStateForValue(metric, metric.ytd);
  }

  metricStateForValue(metric: MatrixMetric, value: number | null): MetricState {
    if (value === null || metric.target === null) return 'neutral';
    const within = metric.goodDown ? value <= metric.target : value >= metric.target;
    if (within) return 'green';
    const variance = Math.abs(value - metric.target) / Math.abs(metric.target || 1);
    return variance <= 0.05 ? 'amber' : 'red';
  }

  stateLabel(metric: MatrixMetric): string {
    switch (this.metricState(metric)) {
      case 'green': return 'On target';
      case 'amber': return 'Near target';
      case 'red': return 'Needs attention';
      default: return metric.ytd === null ? 'Awaiting data' : 'Target not set';
    }
  }

  targetArrow(metric: MatrixMetric, value: number | null): string {
    if (value === null || metric.target === null || value === metric.target) return '→';
    return value > metric.target ? '↑' : '↓';
  }

  variancePercent(metric: MatrixMetric): number | null {
    if (metric.ytd === null || metric.target === null || metric.target === 0) return null;
    return ((metric.ytd - metric.target) / Math.abs(metric.target)) * 100;
  }

  varianceLabel(metric: MatrixMetric): string {
    const variance = this.variancePercent(metric);
    if (variance === null) return 'No target comparison';
    if (Math.abs(variance) < 0.05) return 'Exactly on target';
    return `${Math.abs(variance).toFixed(1)}% ${variance > 0 ? 'above' : 'below'} target`;
  }

  businessInsight(metric: MatrixMetric): string {
    if (metric.ytd === null) return 'Current FY-to-date data is not available yet.';
    if (metric.target !== null) {
      const gap = Math.abs(metric.ytd - metric.target);
      const within = metric.goodDown ? metric.ytd <= metric.target : metric.ytd >= metric.target;
      return within
        ? `FY-to-date performance is inside target by ${this.formatValue(gap)} ${metric.unit}.`
        : `FY-to-date performance misses target by ${this.formatValue(gap)} ${metric.unit}. Review the source entries and operating drivers.`;
    }
    return 'The value is reported, but no approved target has been configured for this measure.';
  }

  private currentPeriod(): string {
    const now = new Date();
    return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
  }

  monthLabel(): string { return new Date(`${this.currentPeriod()}-01T00:00:00`).toLocaleDateString('en-US', { month: 'short', year: '2-digit' }); }
  quarterLabel(): string { const date = new Date(`${this.currentPeriod()}-01T00:00:00`); return `Q${Math.floor(date.getMonth() / 3) + 1} ${String(date.getFullYear()).slice(2)}`; }
  currentYear(): number { return new Date().getFullYear(); }
  previousYear(): number { return this.currentYear() - 1; }
  currentFiscalYearShort(): string {
    const now = new Date();
    const fiscalYearEnd = now.getMonth() >= 3 ? now.getFullYear() + 1 : now.getFullYear();
    return String(fiscalYearEnd).slice(-2);
  }
  previousFiscalYearShort(): string {
    return String(Number(this.currentFiscalYearShort()) - 1).padStart(2, '0');
  }
  toggleMetric(key: string): void { this.selectedMetric.set(this.selectedMetric() === key ? null : key); }
  groupExceedanceCount(group: MatrixGroup): number { return group.metrics.filter((metric) => this.metricState(metric) === 'red').length; }
  exceedanceLabel(group: MatrixGroup): string {
    const count = this.groupExceedanceCount(group);
    return count === 0 ? 'No exceedances' : `${count} ${count === 1 ? 'exceedance' : 'exceedances'}`;
  }

  formatValue(value: number | null): string {
    if (value === null) return '—';
    return value.toLocaleString(undefined, { maximumFractionDigits: 3 });
  }
}
