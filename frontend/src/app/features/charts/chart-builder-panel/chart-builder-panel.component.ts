import { Component, EventEmitter, Input, OnInit, Output, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { AdminLocation, ApiService } from '../../../core/api.service';
import { ChartApiService, ChartConfig, ChartMetric, SavedChart } from '../../../core/chart-api.service';
import { PeriodMode } from '../../../core/intensity-api.service';
import { ChartPoint, ChartSeriesDef, RichTrendChartComponent } from '../../../shared/rich-trend-chart/rich-trend-chart.component';

function currentMonthValue(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
}

@Component({
  selector: 'app-chart-builder-panel',
  standalone: true,
  imports: [FormsModule, RichTrendChartComponent],
  templateUrl: './chart-builder-panel.component.html',
  styleUrl: './chart-builder-panel.component.css'
})
export class ChartBuilderPanelComponent implements OnInit {
  private chartApi = inject(ChartApiService);
  private api = inject(ApiService);

  @Input() editing: SavedChart | null = null;
  @Output() closed = new EventEmitter<void>();
  @Output() saved = new EventEmitter<void>();

  metrics = signal<ChartMetric[]>([]);
  locations = signal<AdminLocation[]>([]);

  metric = signal<string>('scope1_2_tco2e');
  periodMode = signal<PeriodMode>('month');
  months = signal(6);
  locationId = signal<string>('');
  name = signal('');
  description = signal('');

  previewLoading = signal(false);
  previewPoints = signal<ChartPoint[]>([]);
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

  chartSeries(): ChartSeriesDef[] {
    const m = this.currentMetric();
    return [{ key: 'value', label: m?.label ?? '', unit: m?.unit ?? '', tracked: true }];
  }

  async ngOnInit(): Promise<void> {
    const [metrics, locations] = await Promise.all([this.chartApi.listMetrics(), this.api.listLocations()]);
    this.metrics.set(metrics);
    this.locations.set(locations);

    if (this.editing) {
      this.name.set(this.editing.name);
      this.description.set(this.editing.description ?? '');
      this.metric.set(this.editing.config.metric);
      this.periodMode.set(this.editing.config.period_mode);
      this.months.set(this.editing.config.months);
      this.locationId.set(this.editing.config.location_id ?? '');
    }

    await this.refreshPreview();
  }

  async refreshPreview(): Promise<void> {
    this.previewLoading.set(true);
    this.errorMessage.set('');
    try {
      const data = await this.chartApi.getMetricData(
        this.metric(),
        `${currentMonthValue()}-01`,
        this.periodMode(),
        this.months(),
        this.locationId() || undefined
      );
      this.previewPoints.set(
        data.points.map((p) => ({
          period: p.period,
          label: this.formatBucketLabel(p),
          valuesBySeries: { value: p.value },
          priorYearValuesBySeries: { value: p.prior_year_value }
        }))
      );
    } catch {
      this.errorMessage.set('Could not load preview data for this metric.');
      this.previewPoints.set([]);
    } finally {
      this.previewLoading.set(false);
    }
  }

  private formatBucketLabel(p: { bucket_start: string | null; bucket_end: string | null; period: string }): string {
    const end = new Date(`${p.bucket_end ?? p.period}T00:00:00`);
    if (this.periodMode() === 'ytd') return `${end.getFullYear()}`;
    if (this.periodMode() === 'quarter') return `Q${Math.floor(end.getMonth() / 3) + 1} '${String(end.getFullYear()).slice(2)}`;
    return end.toLocaleDateString('en-US', { month: 'short' });
  }

  onSettingChange(): void {
    void this.refreshPreview();
  }

  canSave(): boolean {
    return this.name().trim().length > 0;
  }

  private buildConfig(): ChartConfig {
    return {
      metric: this.metric(),
      chart_kind: 'bar',
      period_mode: this.periodMode(),
      months: this.months(),
      location_id: this.locationId() || null
    };
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
