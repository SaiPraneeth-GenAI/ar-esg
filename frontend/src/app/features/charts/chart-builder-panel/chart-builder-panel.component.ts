import { Component, EventEmitter, Input, OnInit, Output, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { AdminLocation, ApiService } from '../../../core/api.service';
import { BreakdownDimension, ChartApiService, ChartConfig, ChartMetric, QuestionType, SavedChart } from '../../../core/chart-api.service';
import { PeriodMode } from '../../../core/intensity-api.service';
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

// Plain, field-first wording -- no "analysis"/"composition"/jargon. Each
// option answers one everyday question a non-analyst would actually ask.
const QUESTIONS: QuestionOption[] = [
  {
    type: 'trend',
    icon: '📈',
    title: 'See it over time',
    blurb: 'Is this going up or down, month by month?',
    bullets: ['Watch one number change over months', 'See which months were high or low', 'Compare with last year'],
    example: 'e.g. "GHG intensity, month by month"'
  },
  {
    type: 'breakdown',
    icon: '🥧',
    title: 'See what makes it up',
    blurb: 'What is this total made of?',
    bullets: ['See where a total comes from', 'Find the biggest single source', 'Compare the pieces to each other'],
    example: 'e.g. "How much comes from electricity vs. fuel?"'
  },
  {
    type: 'comparison',
    icon: '📊',
    title: 'Compare a few things',
    blurb: 'How do a few numbers stack up side by side?',
    bullets: ['Put a few numbers next to each other', 'See them as simple bars', 'Spot which one is highest'],
    example: 'e.g. "Scope 1 vs. Scope 2, this month"'
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

  @Input() editing: SavedChart | null = null;
  @Output() closed = new EventEmitter<void>();
  @Output() saved = new EventEmitter<void>();

  questions = QUESTIONS;
  step = signal<1 | 2>(1);

  metrics = signal<ChartMetric[]>([]);
  dimensions = signal<BreakdownDimension[]>([]);
  locations = signal<AdminLocation[]>([]);

  questionType = signal<QuestionType>('trend');

  // trend
  metric = signal<string>('scope1_2_tco2e');
  months = signal(6);

  // breakdown
  dimension = signal<string>('ghg_total');

  // comparison
  comparisonMetrics = signal<Set<string>>(new Set(['scope1_tco2e', 'scope2_tco2e']));

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

  async ngOnInit(): Promise<void> {
    const [metrics, dimensions, locations] = await Promise.all([
      this.chartApi.listMetrics(),
      this.chartApi.listBreakdownDimensions(),
      this.api.listLocations()
    ]);
    this.metrics.set(metrics);
    this.dimensions.set(dimensions);
    this.locations.set(locations);

    if (this.editing) {
      this.name.set(this.editing.name);
      this.description.set(this.editing.description ?? '');
      this.questionType.set(this.editing.config.question_type);
      this.periodMode.set(this.editing.config.period_mode);
      this.months.set(this.editing.config.months);
      this.locationId.set(this.editing.config.location_id ?? '');
      if (this.editing.config.metric) this.metric.set(this.editing.config.metric);
      if (this.editing.config.dimension) this.dimension.set(this.editing.config.dimension);
      if (this.editing.config.metrics) this.comparisonMetrics.set(new Set(this.editing.config.metrics));
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
    if (this.questionType() === 'comparison') return this.comparisonMetrics().size >= 2;
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
      metrics: null,
      location_id: this.locationId() || null
    };
    if (this.questionType() === 'trend') return { ...base, metric: this.metric() };
    if (this.questionType() === 'breakdown') return { ...base, dimension: this.dimension() };
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
