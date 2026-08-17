import { Component, OnInit, inject, signal } from '@angular/core';
import { ChartApiService, ChartMetric, ChartMetricPoint, SavedChart } from '../../core/chart-api.service';
import { PeriodMode } from '../../core/intensity-api.service';
import { ChartPoint, ChartSeriesDef, RichTrendChartComponent } from '../../shared/rich-trend-chart/rich-trend-chart.component';
import { ChartBuilderPanelComponent } from './chart-builder-panel/chart-builder-panel.component';

function currentMonthValue(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
}

interface RenderedChart {
  chart: SavedChart;
  metricLabel: string;
  metricUnit: string;
  series: ChartSeriesDef[];
  points: ChartPoint[];
  loading: boolean;
}

@Component({
  selector: 'app-charts',
  standalone: true,
  imports: [RichTrendChartComponent, ChartBuilderPanelComponent],
  templateUrl: './charts.component.html',
  styleUrl: './charts.component.css'
})
export class ChartsComponent implements OnInit {
  private chartApi = inject(ChartApiService);

  loading = signal(true);
  errorMessage = signal('');
  rendered = signal<RenderedChart[]>([]);
  metrics = signal<ChartMetric[]>([]);

  showBuilder = signal(false);
  editingChart = signal<SavedChart | null>(null);

  async ngOnInit(): Promise<void> {
    this.metrics.set(await this.chartApi.listMetrics());
    await this.refresh();
  }

  async refresh(): Promise<void> {
    this.loading.set(true);
    this.errorMessage.set('');
    try {
      const charts = await this.chartApi.list();
      const items: RenderedChart[] = charts.map((chart) => ({
        chart,
        metricLabel: this.metrics().find((m) => m.key === chart.config.metric)?.label ?? chart.config.metric,
        metricUnit: this.metrics().find((m) => m.key === chart.config.metric)?.unit ?? '',
        series: [],
        points: [],
        loading: true
      }));
      this.rendered.set(items);
      await Promise.all(items.map((item) => this.loadChartData(item)));
    } catch {
      this.errorMessage.set('Could not load your charts.');
    } finally {
      this.loading.set(false);
    }
  }

  private async loadChartData(item: RenderedChart): Promise<void> {
    try {
      const data = await this.chartApi.getMetricData(
        item.chart.config.metric,
        `${currentMonthValue()}-01`,
        item.chart.config.period_mode,
        item.chart.config.months,
        item.chart.config.location_id ?? undefined
      );
      item.series = [{ key: 'value', label: data.label, unit: data.unit, tracked: true }];
      item.points = data.points.map((p: ChartMetricPoint) => ({
        period: p.period,
        label: this.formatBucketLabel(p, item.chart.config.period_mode),
        valuesBySeries: { value: p.value },
        priorYearValuesBySeries: { value: p.prior_year_value }
      }));
    } finally {
      item.loading = false;
      this.rendered.set([...this.rendered()]);
    }
  }

  private formatBucketLabel(p: ChartMetricPoint, mode: PeriodMode): string {
    const end = new Date(`${p.bucket_end ?? p.period}T00:00:00`);
    if (mode === 'ytd') return `${end.getFullYear()}`;
    if (mode === 'quarter') return `Q${Math.floor(end.getMonth() / 3) + 1} '${String(end.getFullYear()).slice(2)}`;
    return end.toLocaleDateString('en-US', { month: 'short' });
  }

  openNewChart(): void {
    this.editingChart.set(null);
    this.showBuilder.set(true);
  }

  openEditChart(item: RenderedChart): void {
    this.editingChart.set(item.chart);
    this.showBuilder.set(true);
  }

  closeBuilder(): void {
    this.showBuilder.set(false);
  }

  async onBuilderSaved(): Promise<void> {
    this.showBuilder.set(false);
    await this.refresh();
  }

  async deleteChart(item: RenderedChart): Promise<void> {
    try {
      await this.chartApi.remove(item.chart.id);
      await this.refresh();
    } catch {
      this.errorMessage.set('Could not delete this chart.');
    }
  }
}
