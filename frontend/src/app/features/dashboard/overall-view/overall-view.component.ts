import { Component, Input, OnChanges, inject, signal } from '@angular/core';
import { TargetComparison } from '../../../core/carbon-api.service';
import { IntensityApiService, IntensityOverview, PeriodMode } from '../../../core/intensity-api.service';
import { SafetyApiService, SafetyMetric } from '../../../core/safety-api.service';

type GroupKey = 'absolute' | 'production' | 'revenue' | 'safety';
type MetricState = 'green' | 'amber' | 'red' | 'neutral';

interface OverallMetric {
  key: string;
  label: string;
  unit: string;
  current: number | null;
  priorYear: number | null;
  target: number | null;
  targetStatus: string | null;
  goodDown: boolean;
}

interface OverallGroup {
  key: GroupKey;
  title: string;
  kicker: string;
  accent: string;
  context: string | null;
  metrics: OverallMetric[];
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
  overview = signal<IntensityOverview | null>(null);
  safetyMetrics = signal<SafetyMetric[]>([]);
  focusedGroup = signal<GroupKey | null>(null);
  selectedMetric = signal<string | null>(null);

  async ngOnChanges(): Promise<void> {
    this.loading.set(true);
    this.errorMessage.set('');
    try {
      const [overview, safety] = await Promise.all([
        this.intensityApi.getOverview(`${this.period}-01`, this.locationId ?? undefined, this.periodMode),
        this.safetyApi.getOverview(`${this.period}-01`, this.locationId ?? undefined, this.periodMode)
      ]);
      this.overview.set(overview);
      this.safetyMetrics.set(safety.metrics);
    } catch {
      this.errorMessage.set('Could not load the overall performance view.');
    } finally {
      this.loading.set(false);
    }
  }

  groups(): OverallGroup[] {
    const ov = this.overview();
    if (!ov) return [];

    const target = (comparison: TargetComparison | null): Pick<OverallMetric, 'target' | 'targetStatus'> => ({
      target: comparison?.target_value ?? null,
      targetStatus: comparison?.status ?? null
    });

    return [
      {
        key: 'absolute',
        title: 'Absolute metrics',
        kicker: 'Environmental footprint',
        accent: 'emerald',
        context: null,
        metrics: [
          { key: 'absolute-energy', label: 'Energy consumption', unit: 'GJ', current: ov.energy_gj, priorYear: ov.prior_year_energy_gj, ...target(ov.energy_absolute_target), goodDown: true },
          { key: 'absolute-ghg', label: 'GHG emissions', unit: 'tCO2e', current: ov.ghg_tco2e, priorYear: ov.prior_year_ghg_tco2e, ...target(ov.ghg_absolute_target), goodDown: true },
          { key: 'absolute-water', label: 'Water withdrawal', unit: 'KL', current: ov.water_kl, priorYear: ov.prior_year_water_kl, ...target(ov.water_absolute_target), goodDown: true },
          { key: 'absolute-waste', label: 'Waste generated', unit: 'MT', current: ov.waste_mt, priorYear: ov.prior_year_waste_mt, ...target(ov.waste_absolute_target), goodDown: true },
          { key: 'absolute-production', label: 'Battery production', unit: 'Mn Ah', current: ov.production_mnah, priorYear: ov.prior_year_production_mnah, ...target(ov.production_absolute_target), goodDown: false }
        ]
      },
      {
        key: 'production',
        title: 'Intensity by production',
        kicker: 'Efficiency per output',
        accent: 'blue',
        context: ov.production_mnah === null ? null : `${this.formatValue(ov.production_mnah)} Mn Ah produced`,
        metrics: [
          { key: 'production-energy', label: 'Energy intensity', unit: 'GJ/Mn Ah', current: ov.energy_per_production, priorYear: ov.prior_year_energy_per_production, ...target(ov.energy_per_production_target), goodDown: true },
          { key: 'production-ghg', label: 'GHG intensity', unit: 'tCO2e/Mn Ah', current: ov.ghg_per_production, priorYear: ov.prior_year_ghg_per_production, ...target(ov.ghg_per_production_target), goodDown: true },
          { key: 'production-water', label: 'Water intensity', unit: 'KL/Mn Ah', current: ov.water_per_production, priorYear: ov.prior_year_water_per_production, ...target(ov.water_per_production_target), goodDown: true },
          { key: 'production-waste', label: 'Waste intensity', unit: 'MT/Mn Ah', current: ov.waste_per_production, priorYear: ov.prior_year_waste_per_production, ...target(ov.waste_per_production_target), goodDown: true }
        ]
      },
      {
        key: 'revenue',
        title: 'Intensity by revenue',
        kicker: 'Efficiency per revenue',
        accent: 'violet',
        context: ov.revenue_inr_cr === null ? null : `${this.formatValue(ov.revenue_inr_cr)} INR Cr revenue`,
        metrics: [
          { key: 'revenue-energy', label: 'Energy intensity', unit: 'GJ/INR Cr', current: ov.energy_per_revenue, priorYear: ov.prior_year_energy_per_revenue, ...target(ov.energy_per_revenue_target), goodDown: true },
          { key: 'revenue-ghg', label: 'GHG intensity', unit: 'tCO2e/INR Cr', current: ov.ghg_per_revenue, priorYear: ov.prior_year_ghg_per_revenue, ...target(ov.ghg_per_revenue_target), goodDown: true },
          { key: 'revenue-water', label: 'Water intensity', unit: 'KL/INR Cr', current: ov.water_per_revenue, priorYear: ov.prior_year_water_per_revenue, ...target(ov.water_per_revenue_target), goodDown: true },
          { key: 'revenue-waste', label: 'Waste intensity', unit: 'MT/INR Cr', current: ov.waste_per_revenue, priorYear: ov.prior_year_waste_per_revenue, ...target(ov.waste_per_revenue_target), goodDown: true }
        ]
      },
      {
        key: 'safety',
        title: 'Safety & trends',
        kicker: 'People and operations',
        accent: 'amber',
        context: null,
        metrics: this.safetyMetrics().map((metric) => ({
          key: `safety-${metric.name.toLowerCase().replaceAll(' ', '-')}`,
          label: metric.name,
          unit: metric.unit,
          current: metric.value,
          priorYear: metric.prior_year_value,
          target: metric.target?.target_value ?? null,
          targetStatus: metric.target?.status ?? null,
          goodDown: SAFETY_GOOD_DOWN.has(metric.name)
        }))
      }
    ];
  }

  toggleGroup(key: GroupKey): void {
    this.focusedGroup.set(this.focusedGroup() === key ? null : key);
  }

  toggleMetric(key: string): void {
    this.selectedMetric.set(this.selectedMetric() === key ? null : key);
  }

  metricState(metric: OverallMetric): MetricState {
    if (metric.current === null) return 'neutral';
    if (metric.target !== null) {
      const within = metric.goodDown ? metric.current <= metric.target : metric.current >= metric.target;
      if (within) return 'green';
      const variance = Math.abs(metric.current - metric.target) / Math.abs(metric.target || 1);
      return variance <= 0.05 ? 'amber' : 'red';
    }
    if (metric.priorYear === null) return 'neutral';
    const change = (metric.current - metric.priorYear) / Math.abs(metric.priorYear || 1);
    const favourable = metric.goodDown ? change <= 0 : change >= 0;
    if (favourable) return 'green';
    return Math.abs(change) <= 0.1 ? 'amber' : 'red';
  }

  stateLabel(metric: OverallMetric): string {
    switch (this.metricState(metric)) {
      case 'green': return metric.target !== null ? 'Within target' : 'Favourable';
      case 'amber': return 'Review';
      case 'red': return 'Needs attention';
      default: return 'Awaiting data';
    }
  }

  groupAttentionCount(group: OverallGroup): number {
    return group.metrics.filter((metric) => ['amber', 'red'].includes(this.metricState(metric))).length;
  }

  allMetrics(): OverallMetric[] {
    return this.groups().flatMap((group) => group.metrics);
  }

  targetCoverage(): number {
    return this.allMetrics().filter((metric) => metric.target !== null).length;
  }

  needsAttention(): number {
    return this.allMetrics().filter((metric) => ['amber', 'red'].includes(this.metricState(metric))).length;
  }

  withinTarget(): number {
    return this.allMetrics().filter((metric) => metric.target !== null && this.metricState(metric) === 'green').length;
  }

  priorityMetric(): OverallMetric | null {
    const ranked = this.allMetrics().filter((metric) => metric.current !== null);
    return ranked.find((metric) => this.metricState(metric) === 'red')
      ?? ranked.find((metric) => this.metricState(metric) === 'amber')
      ?? null;
  }

  barWidth(metric: OverallMetric): number {
    if (metric.current === null) return 0;
    const maximum = Math.max(metric.current, metric.priorYear ?? 0, metric.target ?? 0, 0.0001) * 1.12;
    return Math.min((metric.current / maximum) * 100, 100);
  }

  private markerPosition(metric: OverallMetric, marker: number | null): number {
    if (marker === null) return 0;
    const maximum = Math.max(metric.current ?? 0, metric.priorYear ?? 0, metric.target ?? 0, 0.0001) * 1.12;
    return Math.min((marker / maximum) * 100, 100);
  }

  priorMarkerPosition(metric: OverallMetric): number {
    return this.markerPosition(metric, metric.priorYear);
  }

  targetMarkerPosition(metric: OverallMetric): number {
    return this.markerPosition(metric, metric.target);
  }

  businessInsight(metric: OverallMetric): string {
    if (metric.current === null) return 'Current-period data is not available yet.';
    if (metric.target !== null) {
      const gap = Math.abs(metric.current - metric.target);
      const within = metric.goodDown ? metric.current <= metric.target : metric.current >= metric.target;
      if (within) {
        return `Performance is within the target by ${this.formatValue(gap)} ${metric.unit}.`;
      }
      return metric.goodDown
        ? `The target is exceeded by ${this.formatValue(gap)} ${metric.unit}; this needs attention.`
        : `Performance is ${this.formatValue(gap)} ${metric.unit} below target; this needs attention.`;
    }
    if (metric.priorYear === null) return 'A prior-year comparison and target are not available yet.';
    const change = Math.abs(metric.current - metric.priorYear);
    const favourable = metric.goodDown ? metric.current <= metric.priorYear : metric.current >= metric.priorYear;
    return favourable
      ? `Performance improved by ${this.formatValue(change)} ${metric.unit} compared with the same time previous year.`
      : `Performance moved away from the preferred direction by ${this.formatValue(change)} ${metric.unit} compared with the same time previous year.`;
  }

  formatValue(value: number | null): string {
    if (value === null) return '—';
    return value.toLocaleString(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 3 });
  }
}
