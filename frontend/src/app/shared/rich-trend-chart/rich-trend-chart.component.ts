import { DecimalPipe } from '@angular/common';
import { Component, Input, OnChanges, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

export interface ChartSeriesDef {
  key: string;
  label: string;
  unit: string;
  /** false = an honestly-empty series (e.g. Scope 3 -- not calculated
   * anywhere in this platform yet). Selectable, but shows a clear "not
   * tracked yet" state instead of a fabricated zero line. */
  tracked: boolean;
}

export interface ChartPoint {
  period: string;
  label: string;
  valuesBySeries: Record<string, number | null>;
}

type ChartKind = 'bar' | 'line';

@Component({
  selector: 'app-rich-trend-chart',
  standalone: true,
  imports: [DecimalPipe, FormsModule],
  templateUrl: './rich-trend-chart.component.html',
  styleUrl: './rich-trend-chart.component.css'
})
export class RichTrendChartComponent implements OnChanges {
  @Input({ required: true }) title!: string;
  @Input({ required: true }) series: ChartSeriesDef[] = [];
  @Input({ required: true }) points: ChartPoint[] = [];
  @Input() defaultSeriesKey?: string;
  @Input() loading = false;
  @Input() decimals = 2;

  chartKind = signal<ChartKind>('bar');
  selectedKey = signal<string>('');

  ngOnChanges(): void {
    if (!this.selectedKey() || !this.series.some((s) => s.key === this.selectedKey())) {
      this.selectedKey.set(this.defaultSeriesKey ?? this.series[0]?.key ?? '');
    }
  }

  setChartKind(kind: ChartKind): void {
    this.chartKind.set(kind);
  }

  selectSeries(key: string): void {
    this.selectedKey.set(key);
  }

  currentSeries(): ChartSeriesDef | undefined {
    return this.series.find((s) => s.key === this.selectedKey());
  }

  activeValues(): (number | null)[] {
    const key = this.selectedKey();
    return this.points.map((p) => p.valuesBySeries[key] ?? null);
  }

  private maxValue(): number {
    const vals = this.activeValues().filter((v): v is number => v !== null);
    return Math.max(...vals, 0.0001);
  }

  barHeightPct(value: number | null): number {
    if (value === null) return 0;
    return Math.max((value / this.maxValue()) * 100, 2);
  }

  // -- Line chart geometry (fixed 600x200 viewBox, percentage-based) ------

  readonly viewW = 600;
  readonly viewH = 200;
  private readonly padTop = 20;
  private readonly padBottom = 10;

  private plotX(index: number): number {
    const n = this.points.length;
    if (n <= 1) return this.viewW / 2;
    return (index / (n - 1)) * this.viewW;
  }

  private plotY(value: number): number {
    const max = this.maxValue();
    const usable = this.viewH - this.padTop - this.padBottom;
    return this.padTop + usable - (value / max) * usable;
  }

  linePathSegments(): { d: string }[] {
    const values = this.activeValues();
    const segments: { d: string }[] = [];
    let current: string | null = null;
    values.forEach((v, i) => {
      if (v === null) {
        current = null;
        return;
      }
      const x = this.plotX(i);
      const y = this.plotY(v);
      if (current === null) {
        current = `M ${x} ${y}`;
        segments.push({ d: current });
      } else {
        current += ` L ${x} ${y}`;
        segments[segments.length - 1].d = current;
      }
    });
    return segments;
  }

  areaPath(): string {
    const values = this.activeValues();
    const baseline = this.viewH - this.padBottom;
    const points: string[] = [];
    let started = false;
    values.forEach((v, i) => {
      if (v === null) return;
      const x = this.plotX(i);
      const y = this.plotY(v);
      if (!started) {
        points.push(`M ${x} ${baseline} L ${x} ${y}`);
        started = true;
      } else {
        points.push(`L ${x} ${y}`);
      }
    });
    if (!started) return '';
    const lastIdx = values.map((v, i) => (v !== null ? i : -1)).filter((i) => i >= 0).pop()!;
    points.push(`L ${this.plotX(lastIdx)} ${baseline} Z`);
    return points.join(' ');
  }

  dotPoints(): { x: number; y: number; value: number; label: string }[] {
    const values = this.activeValues();
    return values
      .map((v, i) => (v !== null ? { x: this.plotX(i), y: this.plotY(v), value: v, label: this.points[i].label } : null))
      .filter((p): p is { x: number; y: number; value: number; label: string } => p !== null);
  }
}
