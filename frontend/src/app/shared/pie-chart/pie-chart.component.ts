import { DecimalPipe } from '@angular/common';
import { Component, Input, OnChanges, computed, signal } from '@angular/core';

export interface PieSlice {
  label: string;
  value: number;
}

interface RenderedSlice extends PieSlice {
  pct: number;
  color: string;
  dashArray: string;
  dashOffset: number;
}

// Validated categorical order (node scripts/validate_palette.js, --pairs all,
// light mode): green/orange/blue/violet clear every CVD and normal-vision
// floor together. A 5th real hue does not -- past four, fold the remainder
// into "Other" (muted grey) rather than add a hue that can't be told apart
// from its neighbors. Every slice still carries a direct-labeled legend row
// (name + value + %), which is the required mitigation for the one WARN
// (green<->orange sits in the 6-8 CVD floor band, legal only with secondary
// encoding).
const PALETTE = ['#127a45', '#eb6834', '#2a78d6', '#4a3aa7'];
const OTHER_COLOR = '#98a2b3';
const MAX_SLICES = 4; // beyond this, group the smallest remainder into "Other"

const CIRC = 2 * Math.PI * 40; // r=40

@Component({
  selector: 'app-pie-chart',
  standalone: true,
  imports: [DecimalPipe],
  templateUrl: './pie-chart.component.html',
  styleUrl: './pie-chart.component.css'
})
export class PieChartComponent implements OnChanges {
  @Input({ required: true }) title!: string;
  @Input({ required: true }) slices: PieSlice[] = [];
  @Input() unit = '';
  @Input() decimals = 1;
  @Input() loading = false;
  @Input() emptyMessage = 'No data for this period yet.';

  readonly circumference = CIRC;
  rendered = signal<RenderedSlice[]>([]);

  ngOnChanges(): void {
    const positive = this.slices.filter((s) => s.value > 0).sort((a, b) => b.value - a.value);
    let display = positive;
    if (positive.length > MAX_SLICES) {
      const top = positive.slice(0, MAX_SLICES - 1);
      const otherValue = positive.slice(MAX_SLICES - 1).reduce((sum, s) => sum + s.value, 0);
      display = [...top, { label: 'Other', value: otherValue }];
    }
    const total = display.reduce((sum, s) => sum + s.value, 0);
    let offset = 0;
    this.rendered.set(
      display.map((s, i) => {
        const pct = total > 0 ? (s.value / total) * 100 : 0;
        const arc = (pct / 100) * CIRC;
        const slice: RenderedSlice = {
          ...s,
          pct,
          color: s.label === 'Other' ? OTHER_COLOR : PALETTE[i % PALETTE.length],
          dashArray: `${arc} ${CIRC - arc}`,
          dashOffset: -offset
        };
        offset += arc;
        return slice;
      })
    );
  }

  total = computed(() => this.rendered().reduce((sum, s) => sum + s.value, 0));

  hasData(): boolean {
    return this.rendered().length > 0;
  }
}
