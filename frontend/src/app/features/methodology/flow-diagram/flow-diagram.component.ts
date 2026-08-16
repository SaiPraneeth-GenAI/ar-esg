import { DecimalPipe } from '@angular/common';
import { Component, ElementRef, OnInit, ViewChild, inject, signal } from '@angular/core';
import { CarbonApiService, EmissionCalculationOut } from '../../../core/carbon-api.service';
import { IntensityApiService } from '../../../core/intensity-api.service';
import { SafetyApiService, SafetyMetric } from '../../../core/safety-api.service';
import { TargetApiService, TargetOut } from '../../../core/target-api.service';

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
  // Inputs -- every approved activity data point this project actually collects.
  { id: 'diesel', x: 20, y: 20, w: 190, h: 60, label: 'Diesel Consumed', kind: 'input', live: true, sourceName: 'Diesel Consumed' },
  { id: 'petrol', x: 20, y: 96, w: 190, h: 60, label: 'Petrol Consumed', kind: 'input', live: true, sourceName: 'Petrol Consumed' },
  { id: 'lpg', x: 20, y: 172, w: 190, h: 60, label: 'LPG Consumed', kind: 'input', live: true, sourceName: 'LPG Consumed' },
  { id: 'refrigerant', x: 20, y: 248, w: 190, h: 60, label: 'Refrigerant Leakage', kind: 'input', live: true, sourceName: 'Refrigerant Leakage — R-134a' },
  { id: 'electricity', x: 20, y: 324, w: 190, h: 60, label: 'Grid Electricity Consumed', kind: 'input', live: true, sourceName: 'Grid Electricity Consumed' },
  { id: 'water-sources', x: 20, y: 440, w: 190, h: 60, label: 'Water withdrawal (4 sources)', kind: 'input', live: true },
  { id: 'waste-sources', x: 20, y: 516, w: 190, h: 60, label: 'Waste generated (2 categories)', kind: 'input', live: true },
  { id: 'production-input', x: 20, y: 632, w: 190, h: 60, label: 'Battery Production Volume', kind: 'input', live: true },
  { id: 'revenue-input', x: 20, y: 708, w: 190, h: 60, label: 'Revenue', kind: 'input', live: true },
  { id: 'safety-input', x: 20, y: 800, w: 190, h: 60, label: 'Safety metrics (5)', kind: 'input', live: true },

  // Per-source formula application -- GHG and energy read the same fuel /
  // electricity activity but apply different formulas to it.
  { id: 'fuel-ghg-calc', x: 300, y: 20, w: 210, h: 60, label: 'Fuel × Emission Factor', kind: 'process', live: true },
  { id: 'fuel-energy-calc', x: 300, y: 96, w: 210, h: 60, label: 'Fuel × Net Calorific Value', kind: 'process', live: true },
  { id: 'fugitive-calc', x: 300, y: 248, w: 210, h: 60, label: 'Leaked Mass × GWP-100', kind: 'process', live: true },
  { id: 'grid-ghg-calc', x: 300, y: 324, w: 210, h: 60, label: 'Electricity × Grid Factor', kind: 'process', live: true },
  { id: 'grid-energy-calc', x: 300, y: 400, w: 210, h: 60, label: 'Electricity × 3.6 MJ/kWh', kind: 'process', live: true },

  // Domain totals
  { id: 'scope1-total', x: 600, y: 160, w: 190, h: 60, label: 'Scope 1 Total', kind: 'aggregate', live: true },
  { id: 'scope2-total', x: 600, y: 324, w: 190, h: 60, label: 'Scope 2 Total (location-based)', kind: 'aggregate', live: true },
  { id: 'scope3-total', x: 600, y: 400, w: 190, h: 60, label: 'Scope 3 Total', kind: 'aggregate', live: false },
  { id: 'energy-total', x: 600, y: 58, w: 190, h: 60, label: 'Total Energy', kind: 'aggregate', live: true },
  { id: 'water-total', x: 300, y: 440, w: 190, h: 60, label: 'Total Water', kind: 'aggregate', live: true },
  { id: 'waste-total', x: 300, y: 516, w: 190, h: 60, label: 'Total Waste', kind: 'aggregate', live: true },

  // The sum
  { id: 'total-ghg', x: 900, y: 250, w: 190, h: 72, label: 'Total GHG Emissions', kind: 'sum', live: true },

  // Intensity -- grouped exactly as the two dashboard tabs group them.
  { id: 'intensity-production', x: 1200, y: 300, w: 220, h: 72, label: 'Intensity by Production', kind: 'divide', live: true },
  { id: 'intensity-revenue', x: 1200, y: 560, w: 220, h: 72, label: 'Intensity by Revenue', kind: 'divide', live: true },

  // Targets and terminal
  { id: 'target-comparison', x: 1500, y: 220, w: 200, h: 64, label: 'Target Comparison', kind: 'output', live: true },
  { id: 'dashboard', x: 1780, y: 380, w: 200, h: 76, label: 'ESG Dashboard', kind: 'output', live: true },

  // Warning branch
  { id: 'missing-factor', x: 300, y: 900, w: 210, h: 60, label: 'Missing / ambiguous factor', kind: 'warning', live: true },
  { id: 'unresolved-queue', x: 600, y: 900, w: 210, h: 60, label: 'Unresolved queue', kind: 'warning', live: true }
];

const EDGES: FlowEdge[] = [
  { from: 'diesel', to: 'fuel-ghg-calc' },
  { from: 'petrol', to: 'fuel-ghg-calc' },
  { from: 'lpg', to: 'fuel-ghg-calc' },
  { from: 'diesel', to: 'fuel-energy-calc' },
  { from: 'petrol', to: 'fuel-energy-calc' },
  { from: 'lpg', to: 'fuel-energy-calc' },
  { from: 'refrigerant', to: 'fugitive-calc' },
  { from: 'electricity', to: 'grid-ghg-calc' },
  { from: 'electricity', to: 'grid-energy-calc' },

  { from: 'fuel-ghg-calc', to: 'scope1-total' },
  { from: 'fugitive-calc', to: 'scope1-total' },
  { from: 'grid-ghg-calc', to: 'scope2-total' },
  { from: 'fuel-energy-calc', to: 'energy-total' },
  { from: 'grid-energy-calc', to: 'energy-total' },
  { from: 'water-sources', to: 'water-total' },
  { from: 'waste-sources', to: 'waste-total' },

  { from: 'scope1-total', to: 'total-ghg' },
  { from: 'scope2-total', to: 'total-ghg' },
  { from: 'scope3-total', to: 'total-ghg', dashed: true },

  { from: 'total-ghg', to: 'intensity-production' },
  { from: 'energy-total', to: 'intensity-production' },
  { from: 'water-total', to: 'intensity-production' },
  { from: 'waste-total', to: 'intensity-production' },
  { from: 'production-input', to: 'intensity-production' },

  { from: 'total-ghg', to: 'intensity-revenue' },
  { from: 'energy-total', to: 'intensity-revenue' },
  { from: 'water-total', to: 'intensity-revenue' },
  { from: 'waste-total', to: 'intensity-revenue' },
  { from: 'revenue-input', to: 'intensity-revenue' },

  { from: 'total-ghg', to: 'target-comparison' },
  { from: 'intensity-production', to: 'target-comparison' },

  { from: 'total-ghg', to: 'dashboard' },
  { from: 'intensity-production', to: 'dashboard' },
  { from: 'intensity-revenue', to: 'dashboard' },
  { from: 'target-comparison', to: 'dashboard' },
  { from: 'safety-input', to: 'dashboard', dashed: true },

  { from: 'diesel', to: 'missing-factor', dashed: true },
  { from: 'missing-factor', to: 'unresolved-queue', dashed: true }
];

const ANIMATION_ORDER: string[][] = [
  ['diesel', 'petrol', 'lpg', 'refrigerant', 'electricity', 'water-sources', 'waste-sources', 'production-input', 'revenue-input', 'safety-input'],
  ['fuel-ghg-calc', 'fuel-energy-calc', 'fugitive-calc', 'grid-ghg-calc', 'grid-energy-calc'],
  ['scope1-total', 'scope2-total', 'scope3-total', 'energy-total', 'water-total', 'waste-total'],
  ['total-ghg'],
  ['intensity-production', 'intensity-revenue'],
  ['target-comparison'],
  ['dashboard']
];

interface NodeDetail {
  title: string;
  live: boolean;
  value: string | null;
  extraValues: string[];
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
  private safetyApi = inject(SafetyApiService);
  private targetApi = inject(TargetApiService);

  @ViewChild('svgEl') svgEl!: ElementRef<SVGSVGElement>;

  nodes = NODES;
  edges = EDGES;

  loading = signal(true);
  period = signal(currentPeriod());

  viewBox = signal({ x: 0, y: 0, w: 2020, h: 1000 });
  private panStart: { x: number; y: number; vb: { x: number; y: number; w: number; h: number } } | null = null;

  selectedNode = signal<FlowNode | null>(null);
  detail = signal<NodeDetail | null>(null);

  playing = signal(false);
  activeNodeIds = signal<Set<string>>(new Set());
  activeEdgeKeys = signal<Set<string>>(new Set());

  private values: Record<string, { value: number | null; unit: string; extra?: string[] }> = {};
  private safetyMetrics: SafetyMetric[] = [];
  private activeTargets: TargetOut[] = [];

  async ngOnInit(): Promise<void> {
    this.loading.set(true);
    try {
      const [carbon, intensity, safety, targets] = await Promise.all([
        this.carbonApi.getOverview(this.period()),
        this.intensityApi.getOverview(this.period()),
        this.safetyApi.getOverview(this.period()),
        this.targetApi.list('active')
      ]);
      this.safetyMetrics = safety.metrics;
      this.activeTargets = targets;

      this.values = {
        'scope1-total': { value: carbon.scope1_tco2e, unit: 'tCO2e' },
        'scope2-total': { value: carbon.scope2_location_based_tco2e, unit: 'tCO2e' },
        'scope3-total': { value: null, unit: 'tCO2e' },
        'energy-total': { value: intensity.energy_gj, unit: 'GJ' },
        'water-total': { value: intensity.water_kl, unit: 'KL' },
        'waste-total': { value: intensity.waste_mt, unit: 'MT' },
        'total-ghg': { value: carbon.scope1_2_location_based_tco2e, unit: 'tCO2e' },
        'production-input': { value: intensity.production_mnah, unit: 'Mn Ah' },
        'revenue-input': { value: intensity.revenue_inr_cr, unit: 'INR Cr' },
        'intensity-production': {
          value: carbon.intensity_tco2e_per_mnah,
          unit: 'tCO2e/MnAh',
          extra: [
            intensity.energy_per_production !== null ? `${intensity.energy_per_production.toFixed(2)} GJ/MnAh` : 'Energy: data required',
            intensity.water_per_production !== null ? `${intensity.water_per_production.toFixed(1)} KL/MnAh` : 'Water: data required',
            intensity.waste_per_production !== null ? `${intensity.waste_per_production.toFixed(2)} MT/MnAh` : 'Waste: data required'
          ]
        },
        'intensity-revenue': {
          value: intensity.ghg_per_revenue,
          unit: 'tCO2e/Cr',
          extra: [
            intensity.energy_per_revenue !== null ? `${intensity.energy_per_revenue.toFixed(2)} GJ/Cr` : 'Energy: data required',
            intensity.water_per_revenue !== null ? `${intensity.water_per_revenue.toFixed(1)} KL/Cr` : 'Water: data required',
            intensity.waste_per_revenue !== null ? `${intensity.waste_per_revenue.toFixed(2)} MT/Cr` : 'Waste: data required'
          ]
        },
        'target-comparison': {
          value: targets.length,
          unit: targets.length === 1 ? 'active target' : 'active targets',
          extra: targets.map((t) => `${t.metric_type === 'intensity_tco2e_per_mnah' ? 'Intensity' : 'Absolute'}: ${t.current_status_label ?? 'Not enough data'}`)
        },
        'safety-input': {
          value: safety.metrics.length,
          unit: 'metrics tracked',
          extra: safety.metrics.map((m) => `${m.name}: ${m.value !== null ? m.value + ' ' + m.unit : 'not yet entered'}`)
        },
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
    if (node.id === 'target-comparison' || node.id === 'safety-input') {
      return `${v.value} ${v.unit}`;
    }
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
    const newH = Math.min(Math.max(vb.h * factor, 150), 3000);
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
    this.viewBox.set({ x: 0, y: 0, w: 2020, h: 1000 });
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
      value: v && v.value !== null ? `${v.value} ${v.unit}` : null,
      extraValues: v?.extra ?? [],
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
      case 'fuel-ghg-calc':
        return 'Normalized activity × emission factor = kgCO2e';
      case 'fuel-energy-calc':
        return 'Mass (kg) × net calorific value (MJ/kg) = MJ';
      case 'fugitive-calc':
        return 'Leaked mass (kg) × GWP-100 = kgCO2e';
      case 'grid-ghg-calc':
        return 'Normalized MWh × grid factor (tCO2e/MWh) = tCO2e';
      case 'grid-energy-calc':
        return 'kWh × 3.6 = MJ';
      case 'scope1-total':
        return 'Fuel combustion + fugitive emissions';
      case 'scope2-total':
        return 'Sum of approved grid-electricity calculations (location-based)';
      case 'scope3-total':
        return 'Not calculated yet -- deliberately deferred';
      case 'energy-total':
        return 'Sum of fuel MJ + electricity MJ, ÷ 1000 = GJ';
      case 'water-total':
        return 'Sum of approved entries across all Water data points';
      case 'waste-total':
        return 'Sum of approved entries across Hazardous + Non-Hazardous Waste';
      case 'total-ghg':
        return 'Scope 1 + Scope 2 + Scope 3';
      case 'intensity-production':
        return '(GHG, Energy, Water, Waste) ÷ Production volume (Mn Ah)';
      case 'intensity-revenue':
        return '(GHG, Energy, Water, Waste) ÷ Revenue (INR Cr)';
      case 'target-comparison':
        return 'Actual (this month) vs. declared annual target, evaluated against monthly phasing';
      case 'missing-factor':
        return 'No matching factor, or two factors tie for the same period';
      case 'unresolved-queue':
        return 'Excluded from every total until an Admin resolves it';
      case 'safety-input':
        return 'Entered directly, never calculated -- LTIFR is computed by HR before it reaches this platform';
      case 'dashboard':
        return 'Four tabs: Absolute Metrics, Intensity by Production, Intensity by Revenue, Safety & Trends';
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
