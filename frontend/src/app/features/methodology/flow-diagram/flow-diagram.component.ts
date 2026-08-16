import { DecimalPipe } from '@angular/common';
import { Component, ElementRef, OnInit, ViewChild, inject, signal } from '@angular/core';
import { CarbonApiService, EmissionCalculationOut } from '../../../core/carbon-api.service';
import { IntensityApiService } from '../../../core/intensity-api.service';

export type NodeKind = 'input' | 'process' | 'aggregate' | 'sum' | 'divide' | 'output' | 'warning';

export interface FlowNode {
  id: string;
  x: number;
  y: number;
  w: number;
  h: number;
  label: string;
  kind: NodeKind;
  live: boolean;
  /** Data-point name to query /carbon/calculations with, for input nodes. */
  sourceName?: string;
}

export interface FlowEdge {
  from: string;
  to: string;
  dashed?: boolean;
}

const NODES: FlowNode[] = [
  // Column A -- raw activity inputs
  { id: 'diesel', x: 20, y: 20, w: 190, h: 64, label: 'Diesel Consumed', kind: 'input', live: true, sourceName: 'Diesel Consumed' },
  { id: 'petrol', x: 20, y: 104, w: 190, h: 64, label: 'Petrol Consumed', kind: 'input', live: true, sourceName: 'Petrol Consumed' },
  { id: 'lpg', x: 20, y: 188, w: 190, h: 64, label: 'LPG Consumed', kind: 'input', live: true, sourceName: 'LPG Consumed' },
  { id: 'refrigerant', x: 20, y: 272, w: 190, h: 64, label: 'Refrigerant Leakage', kind: 'input', live: true, sourceName: 'Refrigerant Leakage — R-134a' },
  { id: 'electricity', x: 20, y: 356, w: 190, h: 64, label: 'Grid Electricity Consumed', kind: 'input', live: true, sourceName: 'Grid Electricity Consumed' },

  // Column B -- per-source formula application
  { id: 'fuel-calc', x: 300, y: 104, w: 200, h: 64, label: 'Fuel × Emission Factor', kind: 'process', live: true },
  { id: 'fugitive-calc', x: 300, y: 272, w: 200, h: 64, label: 'Leakage × GWP', kind: 'process', live: true },
  { id: 'grid-calc', x: 300, y: 356, w: 200, h: 64, label: 'Electricity × Grid Factor', kind: 'process', live: true },

  // Column C -- scope totals
  { id: 'scope1-total', x: 590, y: 188, w: 190, h: 64, label: 'Scope 1 Total', kind: 'aggregate', live: true },
  { id: 'scope2-total', x: 590, y: 356, w: 190, h: 64, label: 'Scope 2 Total (location-based)', kind: 'aggregate', live: true },
  { id: 'scope3-total', x: 590, y: 440, w: 190, h: 64, label: 'Scope 3 Total', kind: 'aggregate', live: false },

  // Column D -- the sum
  { id: 'total-ghg', x: 870, y: 302, w: 190, h: 76, label: 'Total GHG Emissions', kind: 'sum', live: true },

  // Column E -- denominators
  { id: 'production', x: 1150, y: 140, w: 190, h: 64, label: 'Production Volume', kind: 'input', live: true },
  { id: 'revenue', x: 1150, y: 480, w: 190, h: 64, label: 'Revenue', kind: 'input', live: true },

  // Column F -- intensity outputs
  { id: 'intensity-production', x: 1430, y: 140, w: 210, h: 64, label: 'Intensity by Production', kind: 'divide', live: true },
  { id: 'intensity-revenue', x: 1430, y: 480, w: 210, h: 64, label: 'Intensity by Revenue', kind: 'divide', live: true },

  // Column G -- terminal
  { id: 'dashboard', x: 1730, y: 302, w: 190, h: 76, label: 'Carbon Dashboard', kind: 'output', live: true },

  // Warning branch
  { id: 'missing-factor', x: 300, y: 600, w: 210, h: 64, label: 'Missing / ambiguous factor', kind: 'warning', live: true },
  { id: 'unresolved-queue', x: 590, y: 600, w: 210, h: 64, label: 'Unresolved queue', kind: 'warning', live: true }
];

const EDGES: FlowEdge[] = [
  { from: 'diesel', to: 'fuel-calc' },
  { from: 'petrol', to: 'fuel-calc' },
  { from: 'lpg', to: 'fuel-calc' },
  { from: 'refrigerant', to: 'fugitive-calc' },
  { from: 'electricity', to: 'grid-calc' },

  { from: 'fuel-calc', to: 'scope1-total' },
  { from: 'fugitive-calc', to: 'scope1-total' },
  { from: 'grid-calc', to: 'scope2-total' },

  { from: 'scope1-total', to: 'total-ghg' },
  { from: 'scope2-total', to: 'total-ghg' },
  { from: 'scope3-total', to: 'total-ghg', dashed: true },

  { from: 'total-ghg', to: 'intensity-production' },
  { from: 'production', to: 'intensity-production' },
  { from: 'total-ghg', to: 'intensity-revenue' },
  { from: 'revenue', to: 'intensity-revenue' },

  { from: 'total-ghg', to: 'dashboard' },
  { from: 'intensity-production', to: 'dashboard' },
  { from: 'intensity-revenue', to: 'dashboard' },

  { from: 'diesel', to: 'missing-factor', dashed: true },
  { from: 'missing-factor', to: 'unresolved-queue', dashed: true }
];

const ANIMATION_ORDER: string[][] = [
  ['diesel', 'petrol', 'lpg', 'refrigerant', 'electricity'],
  ['fuel-calc', 'fugitive-calc', 'grid-calc'],
  ['scope1-total', 'scope2-total', 'scope3-total'],
  ['total-ghg'],
  ['production', 'revenue'],
  ['intensity-production', 'intensity-revenue'],
  ['dashboard']
];

interface NodeDetail {
  title: string;
  live: boolean;
  value: string | null;
  formula: string;
  note: string;
  loading: boolean;
  evidence: EmissionCalculationOut[];
}

function currentPeriod(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-01`;
}

@Component({
  selector: 'app-flow-diagram',
  standalone: true,
  imports: [DecimalPipe],
  templateUrl: './flow-diagram.component.html',
  styleUrl: './flow-diagram.component.css'
})
export class FlowDiagramComponent implements OnInit {
  private carbonApi = inject(CarbonApiService);
  private intensityApi = inject(IntensityApiService);

  @ViewChild('svgEl') svgEl!: ElementRef<SVGSVGElement>;

  nodes = NODES;
  edges = EDGES;

  loading = signal(true);
  period = signal(currentPeriod());

  viewBox = signal({ x: 0, y: 0, w: 1960, h: 720 });
  private panStart: { x: number; y: number; vb: { x: number; y: number; w: number; h: number } } | null = null;

  selectedNode = signal<FlowNode | null>(null);
  detail = signal<NodeDetail | null>(null);

  playing = signal(false);
  activeNodeIds = signal<Set<string>>(new Set());
  activeEdgeKeys = signal<Set<string>>(new Set());

  // Live values, keyed by node id, filled from real API data.
  private values: Record<string, { value: number | null; unit: string }> = {};

  async ngOnInit(): Promise<void> {
    this.loading.set(true);
    try {
      const [carbon, intensity] = await Promise.all([
        this.carbonApi.getOverview(this.period()),
        this.intensityApi.getOverview(this.period())
      ]);
      this.values = {
        'scope1-total': { value: carbon.scope1_tco2e, unit: 'tCO2e' },
        'scope2-total': { value: carbon.scope2_location_based_tco2e, unit: 'tCO2e' },
        'scope3-total': { value: null, unit: 'tCO2e' },
        'total-ghg': { value: carbon.scope1_2_location_based_tco2e, unit: 'tCO2e' },
        'production': { value: intensity.production_mnah, unit: 'Mn Ah' },
        'revenue': { value: intensity.revenue_inr_cr, unit: 'INR Cr' },
        'intensity-production': { value: carbon.intensity_tco2e_per_mnah, unit: 'tCO2e/MnAh' },
        'intensity-revenue': { value: intensity.ghg_per_revenue, unit: 'tCO2e/Cr' },
        'dashboard': { value: null, unit: '' }
      };
    } catch {
      this.values = {};
    } finally {
      this.loading.set(false);
    }
  }

  periodLabel(): string {
    return new Date(`${this.period()}T00:00:00`).toLocaleDateString('en-US', { month: 'long', year: 'numeric' });
  }

  nodeValueLabel(node: FlowNode): string | null {
    const v = this.values[node.id];
    if (!v || v.value === null) return null;
    const decimals = Math.abs(v.value) < 1 ? 3 : 1;
    return `${v.value.toFixed(decimals)} ${v.unit}`;
  }

  // -- Pan / zoom -----------------------------------------------------

  onWheel(event: WheelEvent): void {
    event.preventDefault();
    const factor = event.deltaY > 0 ? 1.1 : 0.9;
    this.zoomAt(event.offsetX, event.offsetY, factor);
  }

  zoomAt(pxX: number, pxY: number, factor: number): void {
    const svg = this.svgEl?.nativeElement;
    if (!svg) return;
    const rect = svg.getBoundingClientRect();
    const vb = this.viewBox();
    const svgX = vb.x + (pxX / rect.width) * vb.w;
    const svgY = vb.y + (pxY / rect.height) * vb.h;
    const newW = Math.min(Math.max(vb.w * factor, 400), 6000);
    const newH = Math.min(Math.max(vb.h * factor, 150), 2200);
    this.viewBox.set({
      x: svgX - (svgX - vb.x) * (newW / vb.w),
      y: svgY - (svgY - vb.y) * (newH / vb.h),
      w: newW,
      h: newH
    });
  }

  zoomButton(factor: number): void {
    const vb = this.viewBox();
    this.zoomAt(vb.w / 2, vb.h / 2, factor);
  }

  fitToView(): void {
    this.viewBox.set({ x: 0, y: 0, w: 1960, h: 720 });
  }

  onPointerDown(event: PointerEvent): void {
    this.panStart = { x: event.clientX, y: event.clientY, vb: this.viewBox() };
    (event.target as Element).setPointerCapture(event.pointerId);
  }

  onPointerMove(event: PointerEvent): void {
    if (!this.panStart) return;
    const svg = this.svgEl?.nativeElement;
    if (!svg) return;
    const rect = svg.getBoundingClientRect();
    const vb = this.panStart.vb;
    const dxSvg = ((event.clientX - this.panStart.x) / rect.width) * vb.w;
    const dySvg = ((event.clientY - this.panStart.y) / rect.height) * vb.h;
    this.viewBox.set({ x: vb.x - dxSvg, y: vb.y - dySvg, w: vb.w, h: vb.h });
  }

  onPointerUp(): void {
    this.panStart = null;
  }

  // -- Node selection ---------------------------------------------------

  async selectNode(node: FlowNode): Promise<void> {
    this.selectedNode.set(node);
    const v = this.values[node.id];
    this.detail.set({
      title: node.label,
      live: node.live,
      value: v && v.value !== null ? `${v.value.toFixed(v.value < 1 ? 4 : 2)} ${v.unit}` : null,
      formula: this.formulaFor(node),
      note: this.noteFor(node),
      loading: !!node.sourceName,
      evidence: []
    });

    if (node.sourceName) {
      try {
        const evidence = await this.carbonApi.getCalculations(this.period(), { dataPointName: node.sourceName });
        this.detail.update((d) => (d ? { ...d, loading: false, evidence } : d));
      } catch {
        this.detail.update((d) => (d ? { ...d, loading: false } : d));
      }
    }
  }

  closeDetail(): void {
    this.selectedNode.set(null);
    this.detail.set(null);
  }

  private formulaFor(node: FlowNode): string {
    switch (node.id) {
      case 'fuel-calc':
        return 'Normalized activity × emission factor = kgCO2e';
      case 'fugitive-calc':
        return 'Leaked mass (kg) × GWP-100 = kgCO2e';
      case 'grid-calc':
        return 'Normalized MWh × grid factor (tCO2e/MWh) = tCO2e';
      case 'scope1-total':
        return 'Fuel combustion + fugitive emissions';
      case 'scope2-total':
        return 'Sum of approved grid-electricity calculations (location-based)';
      case 'scope3-total':
        return 'Not calculated yet -- deliberately deferred';
      case 'total-ghg':
        return 'Scope 1 + Scope 2 + Scope 3';
      case 'intensity-production':
        return 'Total GHG (tCO2e) ÷ Production volume (Mn Ah)';
      case 'intensity-revenue':
        return 'Total GHG (tCO2e) ÷ Revenue (INR Cr)';
      case 'missing-factor':
        return 'No matching factor, or two factors tie for the same period';
      case 'unresolved-queue':
        return 'Excluded from every total until an Admin resolves it';
      case 'dashboard':
        return 'Cards, trend charts and drill-down evidence for every number above';
      default:
        return 'Approved activity entry for the current period';
    }
  }

  private noteFor(node: FlowNode): string {
    if (!node.live) return 'Planned -- not calculated in the platform yet.';
    switch (node.kind) {
      case 'input':
        return node.sourceName
          ? 'Click a row below to see the exact factor version used for that entry.'
          : 'Read from the same approved entries the rest of the dashboard uses.';
      case 'warning':
        return 'Never silently estimated -- the entry is set aside until a human fixes the underlying data.';
      default:
        return 'Computed from approved calculation snapshots for the selected period, never a live sum.';
    }
  }

  // -- Play animation ---------------------------------------------------

  async play(): Promise<void> {
    if (this.playing()) return;
    this.playing.set(true);
    this.activeNodeIds.set(new Set());
    this.activeEdgeKeys.set(new Set());

    for (let i = 0; i < ANIMATION_ORDER.length; i++) {
      const stage = ANIMATION_ORDER[i];
      this.activeNodeIds.update((s) => new Set([...s, ...stage]));
      if (i > 0) {
        const prevStage = ANIMATION_ORDER[i - 1];
        const keys = this.edges
          .filter((e) => prevStage.includes(e.from) && stage.includes(e.to))
          .map((e) => `${e.from}->${e.to}`);
        this.activeEdgeKeys.update((s) => new Set([...s, ...keys]));
      }
      await new Promise((r) => setTimeout(r, 550));
    }
    this.playing.set(false);
  }

  resetPlay(): void {
    this.activeNodeIds.set(new Set());
    this.activeEdgeKeys.set(new Set());
  }

  // -- Geometry helpers ---------------------------------------------------

  edgePath(edge: FlowEdge): string {
    const from = this.nodes.find((n) => n.id === edge.from)!;
    const to = this.nodes.find((n) => n.id === edge.to)!;
    const x1 = from.x + from.w;
    const y1 = from.y + from.h / 2;
    const x2 = to.x;
    const y2 = to.y + to.h / 2;
    const mx = (x1 + x2) / 2;
    return `M ${x1} ${y1} C ${mx} ${y1}, ${mx} ${y2}, ${x2} ${y2}`;
  }

  edgeKey(edge: FlowEdge): string {
    return `${edge.from}->${edge.to}`;
  }

  isEdgeActive(edge: FlowEdge): boolean {
    return this.activeEdgeKeys().has(this.edgeKey(edge));
  }

  isNodeActive(node: FlowNode): boolean {
    return this.activeNodeIds().has(node.id);
  }
}
