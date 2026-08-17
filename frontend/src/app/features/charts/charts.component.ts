import { Component, OnInit, inject, signal } from '@angular/core';
import { BreakdownDimension, ChartApiService, ChartMetric, ChartMetricPoint, SavedChart } from '../../core/chart-api.service';
import { PeriodMode } from '../../core/intensity-api.service';
import { PieChartComponent, PieSlice } from '../../shared/pie-chart/pie-chart.component';
import { ChartPoint, ChartSeriesDef, RichTrendChartComponent } from '../../shared/rich-trend-chart/rich-trend-chart.component';
import { ChartBuilderPanelComponent } from './chart-builder-panel/chart-builder-panel.component';
import { PeerAnalysisComponent } from './peer-analysis/peer-analysis.component';

type TabId = 'company' | 'peers';

function currentMonthValue(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
}

function formatBucketLabel(p: { bucket_start: string | null; bucket_end: string | null; period: string }, mode: PeriodMode): string {
  const end = new Date(`${p.bucket_end ?? p.period}T00:00:00`);
  if (mode === 'ytd') return `${end.getFullYear()}`;
  if (mode === 'quarter') return `Q${Math.floor(end.getMonth() / 3) + 1} '${String(end.getFullYear()).slice(2)}`;
  return end.toLocaleDateString('en-US', { month: 'short' });
}

interface RenderedChart {
  chart: SavedChart;
  displayLabel: string;
  series: ChartSeriesDef[];
  points: ChartPoint[];
  slices: PieSlice[];
  unit: string;
  loading: boolean;
}

@Component({
  selector: 'app-charts',
  standalone: true,
  imports: [RichTrendChartComponent, PieChartComponent, ChartBuilderPanelComponent, PeerAnalysisComponent],
  templateUrl: './charts.component.html',
  styleUrl: './charts.component.css'
})
export class ChartsComponent implements OnInit {
  private chartApi = inject(ChartApiService);

  activeTab = signal<TabId>('company');

  loading = signal(true);
  errorMessage = signal('');
  rendered = signal<RenderedChart[]>([]);
  metrics = signal<ChartMetric[]>([]);
  dimensions = signal<BreakdownDimension[]>([]);

  showBuilder = signal(false);
  editingChart = signal<SavedChart | null>(null);

  companyCharts(): RenderedChart[] {
    return this.rendered();
  }

  setTab(tab: TabId): void {
    this.activeTab.set(tab);
  }

  async ngOnInit(): Promise<void> {
    const [metrics, dimensions] = await Promise.all([this.chartApi.listMetrics(), this.chartApi.listBreakdownDimensions()]);
    this.metrics.set(metrics);
    this.dimensions.set(dimensions);
    await this.refresh();
  }

  private displayLabel(chart: SavedChart): string {
    const cfg = chart.config;
    if (cfg.question_type === 'trend') return this.metrics().find((m) => m.key === cfg.metric)?.label ?? cfg.metric ?? '';
    if (cfg.question_type === 'breakdown') return this.dimensions().find((d) => d.key === cfg.dimension)?.label ?? cfg.dimension ?? '';
    return (cfg.metrics ?? []).map((k) => this.metrics().find((m) => m.key === k)?.label ?? k).join(' vs ');
  }

  async refresh(): Promise<void> {
    this.loading.set(true);
    this.errorMessage.set('');
    try {
      const charts = await this.chartApi.list();
      const items: RenderedChart[] = charts.map((chart) => ({
        chart,
        displayLabel: this.displayLabel(chart),
        series: [],
        points: [],
        slices: [],
        unit: '',
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
    const cfg = item.chart.config;
    try {
      if (cfg.question_type === 'breakdown' && cfg.dimension) {
        const data = await this.chartApi.getBreakdownData(cfg.dimension, `${currentMonthValue()}-01`, cfg.period_mode, cfg.location_id ?? undefined);
        item.slices = data.slices.map((s) => ({ label: s.label, value: s.value }));
        item.unit = data.unit;
      } else if (cfg.question_type === 'comparison' && cfg.metrics) {
        const results = await Promise.all(
          cfg.metrics.map((key) => this.chartApi.getMetricData(key, `${currentMonthValue()}-01`, cfg.period_mode, 1, cfg.location_id ?? undefined))
        );
        item.series = [{ key: 'value', label: item.displayLabel, unit: results[0]?.unit ?? '', tracked: true }];
        item.points = results.map((data, i) => ({
          period: cfg.metrics![i],
          label: this.metrics().find((m) => m.key === cfg.metrics![i])?.label ?? cfg.metrics![i],
          valuesBySeries: { value: data.points[0]?.value ?? null }
        }));
      } else if (cfg.metric) {
        const data = await this.chartApi.getMetricData(cfg.metric, `${currentMonthValue()}-01`, cfg.period_mode, cfg.months, cfg.location_id ?? undefined);
        item.series = [{ key: 'value', label: data.label, unit: data.unit, tracked: true }];
        item.points = data.points.map((p: ChartMetricPoint) => ({
          period: p.period,
          label: formatBucketLabel(p, cfg.period_mode),
          valuesBySeries: { value: p.value },
          priorYearValuesBySeries: { value: p.prior_year_value },
          targetValuesBySeries: { value: p.target_value }
        }));
      }
    } finally {
      item.loading = false;
      this.rendered.set([...this.rendered()]);
    }
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
