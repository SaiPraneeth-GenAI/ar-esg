import { Component, EventEmitter, Input, OnInit, Output, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { AdminLocation, ApiService } from '../../../core/api.service';
import {
  BreakdownDimension,
  ChartApiService,
  ChartConfig,
  ChartMetric,
  ComparisonMode,
  QuestionType,
  SavedChart
} from '../../../core/chart-api.service';
import { PeriodMode } from '../../../core/intensity-api.service';
import { PeerApiService, PeerCompany } from '../../../core/peer-api.service';
import { PieChartComponent, PieSlice } from '../../../shared/pie-chart/pie-chart.component';
import { ChartPoint, ChartSeriesDef, RichTrendChartComponent } from '../../../shared/rich-trend-chart/rich-trend-chart.component';

function currentMonthValue(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
}

interface QuestionOption {
  type: QuestionType;
  icon: string;
  title: string;
  blurb: string;
  bullets: string[];
  example: string;
}

const QUESTIONS: QuestionOption[] = [
  {
    type: 'trend',
    icon: '📈',
    title: 'Trend analysis',
    blurb: 'How has this changed over time?',
    bullets: ['Track a metric month to month', 'Spot patterns, peaks, and valleys', 'Compare against last year'],
    example: 'e.g. "Monthly GHG intensity, last 12 months"'
  },
  {
    type: 'breakdown',
    icon: '🥧',
    title: 'Breakdown analysis',
    blurb: 'What are the parts of a whole?',
    bullets: ['See what makes up a total', 'Find the biggest contributor', 'Understand composition'],
    example: 'e.g. "What share of emissions comes from grid electricity vs fuel?"'
  },
  {
    type: 'comparison',
    icon: '📊',
    title: 'Comparison analysis',
    blurb: 'How do a few things stack up side by side?',
    bullets: ['Compare several metrics at once', 'See them as bars, side by side', 'Spot which one stands out'],
    example: 'e.g. "Scope 1 vs Scope 2 vs GHG intensity, this month"'
  }
];

@Component({
  selector: 'app-chart-builder-panel',
  standalone: true,
  imports: [FormsModule, RichTrendChartComponent, PieChartComponent],
  templateUrl: './chart-builder-panel.component.html',
  styleUrl: './chart-builder-panel.component.css'
})
export class ChartBuilderPanelComponent implements OnInit {
  private chartApi = inject(ChartApiService);
  private api = inject(ApiService);
  private peerApi = inject(PeerApiService);

  @Input() editing: SavedChart | null = null;
  @Output() closed = new EventEmitter<void>();
  @Output() saved = new EventEmitter<void>();

  questions = QUESTIONS;
  step = signal<1 | 2>(1);

  metrics = signal<ChartMetric[]>([]);
  dimensions = signal<BreakdownDimension[]>([]);
  locations = signal<AdminLocation[]>([]);
  peerCompanies = signal<PeerCompany[]>([]);

  questionType = signal<QuestionType>('trend');

  // trend
  metric = signal<string>('scope1_2_tco2e');
  months = signal(6);

  // breakdown
  dimension = signal<string>('ghg_total');

  // comparison
  comparisonMode = signal<ComparisonMode>('metrics');
  comparisonMetrics = signal<Set<string>>(new Set(['scope1_tco2e', 'scope2_tco2e']));
  comparePeerMetric = signal<string>('scope1_2_tco2e');
  selectedPeerIds = signal<Set<string>>(new Set());

  // shared
  periodMode = signal<PeriodMode>('month');
  locationId = signal<string>('');
  name = signal('');
  description = signal('');

  previewLoading = signal(false);
  trendPreviewPoints = signal<ChartPoint[]>([]);
  breakdownSlices = signal<PieSlice[]>([]);
  breakdownUnit = signal('');
  errorMessage = signal('');
  submitting = signal(false);

  metricGroups(): string[] {
    return Array.from(new Set(this.metrics().map((m) => m.group)));
  }

  metricsInGroup(group: string): ChartMetric[] {
    return this.metrics().filter((m) => m.group === group);
  }

  currentMetric(): ChartMetric | undefined {
    return this.metrics().find((m) => m.key === this.metric());
  }

  trendChartSeries(): ChartSeriesDef[] {
    if (this.questionType() === 'comparison') {
      if (this.comparisonMode() === 'peers') {
        const unit = this.metrics().find((x) => x.key === this.comparePeerMetric())?.unit ?? '';
        return [{ key: 'value', label: 'vs peers', unit, tracked: true }];
      }
      const m = Array.from(this.comparisonMetrics())[0];
      const unit = this.metrics().find((x) => x.key === m)?.unit ?? '';
      return [{ key: 'value', label: 'Selected metrics', unit, tracked: true }];
    }
    const m = this.currentMetric();
    return [{ key: 'value', label: m?.label ?? '', unit: m?.unit ?? '', tracked: true }];
  }

  toggleComparisonMetric(key: string): void {
    const set = new Set(this.comparisonMetrics());
    if (set.has(key)) {
      set.delete(key);
    } else if (set.size < 6) {
      set.add(key);
    }
    this.comparisonMetrics.set(set);
    this.onSettingChange();
  }

  isComparisonMetricSelected(key: string): boolean {
    return this.comparisonMetrics().has(key);
  }

  setComparisonMode(mode: ComparisonMode): void {
    this.comparisonMode.set(mode);
    this.onSettingChange();
  }

  togglePeerSelection(id: string): void {
    const set = new Set(this.selectedPeerIds());
    if (set.has(id)) {
      set.delete(id);
    } else {
      set.add(id);
    }
    this.selectedPeerIds.set(set);
    this.onSettingChange();
  }

  isPeerSelected(id: string): boolean {
    return this.selectedPeerIds().has(id);
  }

  async ngOnInit(): Promise<void> {
    const [metrics, dimensions, locations, peerCompanies] = await Promise.all([
      this.chartApi.listMetrics(),
      this.chartApi.listBreakdownDimensions(),
      this.api.listLocations(),
      this.peerApi.listCompanies()
    ]);
    this.metrics.set(metrics);
    this.dimensions.set(dimensions);
    this.locations.set(locations);
    this.peerCompanies.set(peerCompanies);

    if (this.editing) {
      this.name.set(this.editing.name);
      this.description.set(this.editing.description ?? '');
      this.questionType.set(this.editing.config.question_type);
      this.periodMode.set(this.editing.config.period_mode);
      this.months.set(this.editing.config.months);
      this.locationId.set(this.editing.config.location_id ?? '');
      this.comparisonMode.set(this.editing.config.comparison_mode ?? 'metrics');
      if (this.editing.config.metric) {
        this.metric.set(this.editing.config.metric);
        this.comparePeerMetric.set(this.editing.config.metric);
      }
      if (this.editing.config.dimension) this.dimension.set(this.editing.config.dimension);
      if (this.editing.config.metrics) this.comparisonMetrics.set(new Set(this.editing.config.metrics));
      if (this.editing.config.compare_peer_ids) this.selectedPeerIds.set(new Set(this.editing.config.compare_peer_ids));
      this.step.set(2);
      await this.refreshPreview();
    }
  }

  selectQuestion(type: QuestionType): void {
    this.questionType.set(type);
    this.step.set(2);
    void this.refreshPreview();
  }

  backToQuestion(): void {
    this.step.set(1);
  }

  private formatBucketLabel(p: { bucket_start: string | null; bucket_end: string | null; period: string }): string {
    const end = new Date(`${p.bucket_end ?? p.period}T00:00:00`);
    if (this.periodMode() === 'ytd') return `${end.getFullYear()}`;
    if (this.periodMode() === 'quarter') return `Q${Math.floor(end.getMonth() / 3) + 1} '${String(end.getFullYear()).slice(2)}`;
    return end.toLocaleDateString('en-US', { month: 'short' });
  }

  async refreshPreview(): Promise<void> {
    this.previewLoading.set(true);
    this.errorMessage.set('');
    try {
      if (this.questionType() === 'trend') {
        const data = await this.chartApi.getMetricData(this.metric(), `${currentMonthValue()}-01`, this.periodMode(), this.months(), this.locationId() || undefined);
        this.trendPreviewPoints.set(
          data.points.map((p) => ({
            period: p.period,
            label: this.formatBucketLabel(p),
            valuesBySeries: { value: p.value },
            priorYearValuesBySeries: { value: p.prior_year_value }
          }))
        );
      } else if (this.questionType() === 'breakdown') {
        const data = await this.chartApi.getBreakdownData(this.dimension(), `${currentMonthValue()}-01`, this.periodMode(), this.locationId() || undefined);
        this.breakdownSlices.set(data.slices.map((s) => ({ label: s.label, value: s.value })));
        this.breakdownUnit.set(data.unit);
      } else if (this.comparisonMode() === 'peers') {
        const peerIds = Array.from(this.selectedPeerIds());
        if (peerIds.length === 0) {
          this.trendPreviewPoints.set([]);
        } else {
          const data = await this.peerApi.compare(this.comparePeerMetric(), `${currentMonthValue()}-01`, this.periodMode(), peerIds, this.locationId() || undefined);
          this.trendPreviewPoints.set(
            data.entries.map((e) => ({
              period: e.name,
              label: e.name,
              valuesBySeries: { value: e.value }
            }))
          );
        }
      } else {
        const keys = Array.from(this.comparisonMetrics());
        const results = await Promise.all(
          keys.map((key) => this.chartApi.getMetricData(key, `${currentMonthValue()}-01`, this.periodMode(), 1, this.locationId() || undefined))
        );
        this.trendPreviewPoints.set(
          results.map((data, i) => ({
            period: keys[i],
            label: this.metrics().find((m) => m.key === keys[i])?.label ?? keys[i],
            valuesBySeries: { value: data.points[0]?.value ?? null }
          }))
        );
      }
    } catch {
      this.errorMessage.set('Could not load preview data.');
      this.trendPreviewPoints.set([]);
      this.breakdownSlices.set([]);
    } finally {
      this.previewLoading.set(false);
    }
  }

  onSettingChange(): void {
    void this.refreshPreview();
  }

  canSave(): boolean {
    if (!this.name().trim()) return false;
    if (this.questionType() === 'comparison') {
      if (this.comparisonMode() === 'peers') return this.selectedPeerIds().size >= 1;
      return this.comparisonMetrics().size >= 2;
    }
    return true;
  }

  private buildConfig(): ChartConfig {
    const base: ChartConfig = {
      question_type: this.questionType(),
      metric: null,
      chart_kind: 'bar',
      period_mode: this.periodMode(),
      months: this.months(),
      dimension: null,
      comparison_mode: this.comparisonMode(),
      metrics: null,
      compare_peer_ids: null,
      location_id: this.locationId() || null
    };
    if (this.questionType() === 'trend') return { ...base, metric: this.metric() };
    if (this.questionType() === 'breakdown') return { ...base, dimension: this.dimension() };
    if (this.comparisonMode() === 'peers') {
      return { ...base, metric: this.comparePeerMetric(), compare_peer_ids: Array.from(this.selectedPeerIds()) };
    }
    return { ...base, metrics: Array.from(this.comparisonMetrics()) };
  }

  async save(): Promise<void> {
    if (!this.canSave()) return;
    this.submitting.set(true);
    this.errorMessage.set('');
    try {
      if (this.editing) {
        await this.chartApi.update(this.editing.id, { name: this.name(), description: this.description() || null, config: this.buildConfig() });
      } else {
        await this.chartApi.create({ name: this.name(), description: this.description() || null, config: this.buildConfig() });
      }
      this.saved.emit();
    } catch (err: any) {
      this.errorMessage.set(err?.error?.detail ?? 'Could not save this chart.');
    } finally {
      this.submitting.set(false);
    }
  }

  close(): void {
    this.closed.emit();
  }
}
