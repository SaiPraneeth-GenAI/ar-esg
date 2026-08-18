import { DecimalPipe } from '@angular/common';
import { Component, ElementRef, OnInit, ViewChild, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute } from '@angular/router';
import { AdminLocation, ApiService } from '../../../core/api.service';
import { CarbonApiService, EmissionCalculationOut } from '../../../core/carbon-api.service';
import { IntensityApiService, PeriodMode } from '../../../core/intensity-api.service';
import { SafetyApiService } from '../../../core/safety-api.service';
import { TargetApiService } from '../../../core/target-api.service';

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
  { id: 'safety-input', x: 20, y: 800, w: 190, h: 172, label: 'Safety metrics (5)', kind: 'input', live: true },

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

  // Intensity -- grouped exactly as the two dashboard tabs group them, all
  // four metrics shown directly, not hidden behind a click.
  { id: 'intensity-production', x: 1200, y: 300, w: 230, h: 172, label: 'Intensity by Production', kind: 'divide', live: true },
  { id: 'intensity-revenue', x: 1200, y: 560, w: 230, h: 172, label: 'Intensity by Revenue', kind: 'divide', live: true },

  // Targets and terminal
  { id: 'target-comparison', x: 1500, y: 210, w: 210, h: 100, label: 'Target Comparison', kind: 'output', live: true },
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

function periodValue(year: number, month: number): string {
  return `${year}-${String(month).padStart(2, '0')}-01`;
}

interface PeriodOption {
  value: string;
  label: string;
}

@Component({
  selector: 'app-flow-diagram',
  standalone: true,
  imports: [DecimalPipe, FormsModule],
  templateUrl: './flow-diagram.component.html',
  styleUrl: './flow-diagram.component.css'
})
export class FlowDiagramComponent implements OnInit {
  private carbonApi = inject(CarbonApiService);
  private intensityApi = inject(IntensityApiService);
  private safetyApi = inject(SafetyApiService);
  private targetApi = inject(TargetApiService);
  private api = inject(ApiService);
  private route = inject(ActivatedRoute);

  @ViewChild('svgEl') svgEl!: ElementRef<SVGSVGElement>;

  nodes = NODES;
  edges = EDGES;

  loading = signal(true);
  period = signal(currentPeriod());
  periodMode = signal<PeriodMode>('month');
  locations = signal<AdminLocation[]>([]);
  locationId = signal('');

  viewBox = signal({ x: 0, y: 0, w: 2020, h: 1010 });
  private panStart: { x: number; y: number; vb: { x: number; y: number; w: number; h: number } } | null = null;

  selectedNode = signal<FlowNode | null>(null);
  detail = signal<NodeDetail | null>(null);

  playing = signal(false);
  activeNodeIds = signal<Set<string>>(new Set());
  activeEdgeKeys = signal<Set<string>>(new Set());

  /** Every node's on-canvas display -- 1-5 short lines, always real numbers
   * (or an explicit "data required"/"planned"), never blank unless a node
   * has genuinely nothing to show. */
  private lines: Record<string, string[]> = {};
  private extraLines: Record<string, string[]> = {};

  async ngOnInit(): Promise<void> {
    this.locations.set(await this.api.listLocations());

    // A dashboard card can deep-link here with the exact period/site/nodes
    // it was showing, so the diagram opens already scoped and spotlit
    // instead of leaving the customer to hunt for the right slice.
    const params = this.route.snapshot.queryParamMap;
    const period = params.get('period');
    const periodMode = params.get('periodMode') as PeriodMode | null;
    const locationId = params.get('locationId');
    const nodeIds = params.get('nodes');
    if (periodMode === 'month' || periodMode === 'quarter' || periodMode === 'ytd') {
      this.periodMode.set(periodMode);
    }
    if (period) {
      this.period.set(period);
    }
    if (locationId) {
      this.locationId.set(locationId);
    }

    await this.load();

    if (nodeIds) {
      this.highlightPath(nodeIds.split(',').filter(Boolean));
    }
  }

  async setLocation(value: string): Promise<void> {
    this.locationId.set(value);
    await this.load();
  }

  async load(): Promise<void> {
    this.loading.set(true);
    try {
      const loc = this.locationId() || undefined;
      const [carbon, intensity, safety, targets, allCalcs] = await Promise.all([
        this.carbonApi.getOverview(this.period(), loc, this.periodMode()),
        this.intensityApi.getOverview(this.period(), loc, this.periodMode()),
        this.safetyApi.getOverview(this.period(), loc, this.periodMode()),
        this.targetApi.list('active'),
        this.carbonApi.getCalculations(this.period(), { periodMode: this.periodMode(), locationId: loc })
      ]);

      const byName = (name: string) => allCalcs.filter((c) => c.data_point_name === name);
      const sumTco2e = (rows: EmissionCalculationOut[]): number | null =>
        rows.length === 0 ? null : rows.reduce((s, r) => s + (r.emissions_tco2e ?? 0), 0);
      const activityLine = (rows: EmissionCalculationOut[]): string | null => {
        if (rows.length === 0) return null;
        const total = rows.reduce((s, r) => s + r.activity_value, 0);
        return `${total.toLocaleString(undefined, { maximumFractionDigits: 1 })} ${rows[0].activity_unit}`;
      };
      const tco2eLine = (v: number | null): string => (v !== null ? `${v.toFixed(2)} tCO2e` : 'No approved calculation');
      const numLine = (v: number | null, unit: string, decimals = 1): string =>
        v !== null ? `${v.toFixed(decimals)} ${unit}` : `${unit}: data required`;

      const diesel = byName('Diesel Consumed');
      const petrol = byName('Petrol Consumed');
      const lpg = byName('LPG Consumed');
      const refrigerant = byName('Refrigerant Leakage — R-134a');
      const electricity = byName('Grid Electricity Consumed');

      const fuelGhg = [...diesel, ...petrol, ...lpg];
      const fuelGhgTotal = sumTco2e(fuelGhg);
      const fugitiveTotal = sumTco2e(refrigerant);
      const gridGhgTotal = sumTco2e(electricity);

      // Energy: grid's MJ contribution is computed exactly the way the
      // backend does (kWh x 3.6, /1000 for GJ); fuel's share is the
      // remainder of the real Total Energy figure, so both numbers stay
      // consistent with the actual reported total rather than an
      // independent (and possibly drifting) re-derivation.
      const electricityKwh = electricity.reduce((s, r) => s + r.activity_value, 0);
      const gridEnergyGj = electricity.length > 0 ? (electricityKwh * 3.6) / 1000 : null;
      const fuelEnergyGj =
        intensity.energy_gj !== null && gridEnergyGj !== null ? intensity.energy_gj - gridEnergyGj : intensity.energy_gj;

      const unresolvedCount = carbon.unresolved_count;

      // Worked, value-substituted breakdowns for the aggregate/sum/divide
      // nodes -- built straight from every calculated row this period
      // (not a hardcoded set of data point names), so a new GHG source
      // shows up in the breakdown automatically instead of the total
      // silently drifting away from what the panel explains.
      const byContributor = (rows: EmissionCalculationOut[]): [string, number][] => {
        const totals = new Map<string, number>();
        for (const r of rows) {
          totals.set(r.data_point_name, (totals.get(r.data_point_name) ?? 0) + (r.emissions_tco2e ?? 0));
        }
        return [...totals.entries()];
      };
      const breakdownLine = (parts: [string, number][], total: number | null, unit = 'tCO2e', decimals = 2): string | null => {
        if (parts.length === 0 || total === null) return null;
        const terms = parts.map(([name, v]) => `${name} (${v.toFixed(decimals)})`).join(' + ');
        return `${terms} = ${total.toFixed(decimals)} ${unit}`;
      };
      const ratioLine = (numeratorLabel: string, numerator: number | null, denomLabel: string, denominator: number | null, result: number | null, unit: string, decimals = 3): string | null => {
        if (numerator === null || denominator === null || result === null) return null;
        return `${numeratorLabel} (${numerator.toFixed(2)}) ÷ ${denomLabel} (${denominator.toFixed(2)}) = ${result.toFixed(decimals)} ${unit}`;
      };

      const scope1Calcs = allCalcs.filter((c) => c.scope === 1);
      const scope2Calcs = allCalcs.filter((c) => c.scope === 2 && c.calculation_method !== 'market-based');
      const scope1Breakdown = breakdownLine(byContributor(scope1Calcs), carbon.scope1_tco2e);
      const scope2Breakdown = breakdownLine(byContributor(scope2Calcs), carbon.scope2_location_based_tco2e);
      const totalGhgBreakdown =
        carbon.scope1_tco2e !== null && carbon.scope2_location_based_tco2e !== null && carbon.scope1_2_location_based_tco2e !== null
          ? `Scope 1 (${carbon.scope1_tco2e.toFixed(2)}) + Scope 2 (${carbon.scope2_location_based_tco2e.toFixed(2)}) = ${carbon.scope1_2_location_based_tco2e.toFixed(2)} tCO2e`
          : null;
      const energyBreakdown =
        fuelEnergyGj !== null && gridEnergyGj !== null && intensity.energy_gj !== null
          ? `Fuel (${fuelEnergyGj.toFixed(2)}) + Grid (${gridEnergyGj.toFixed(2)}) = ${intensity.energy_gj.toFixed(2)} GJ`
          : null;
      const intensityProductionRatio = ratioLine(
        'Total GHG', carbon.scope1_2_location_based_tco2e, 'Production', intensity.production_mnah, carbon.intensity_tco2e_per_mnah, 'tCO2e/MnAh'
      );
      const intensityRevenueRatio = ratioLine(
        'Total GHG', carbon.scope1_2_location_based_tco2e, 'Revenue', intensity.revenue_inr_cr, intensity.ghg_per_revenue, 'tCO2e/Cr'
      );

      this.lines = {
        diesel: [activityLine(diesel) ?? 'No approved entry', tco2eLine(sumTco2e(diesel))],
        petrol: [activityLine(petrol) ?? 'No approved entry', tco2eLine(sumTco2e(petrol))],
        lpg: [activityLine(lpg) ?? 'No approved entry', tco2eLine(sumTco2e(lpg))],
        refrigerant: [activityLine(refrigerant) ?? 'No approved entry', tco2eLine(fugitiveTotal)],
        electricity: [activityLine(electricity) ?? 'No approved entry', tco2eLine(gridGhgTotal)],
        'water-sources': [numLine(intensity.water_kl, 'KL')],
        'waste-sources': [numLine(intensity.waste_mt, 'MT', 2)],
        'production-input': [numLine(intensity.production_mnah, 'Mn Ah', 2)],
        'revenue-input': [numLine(intensity.revenue_inr_cr, 'INR Cr', 2)],
        'safety-input': safety.metrics.map((m) => `${m.name}: ${m.value !== null ? m.value + ' ' + m.unit : 'not entered'}`),

        'fuel-ghg-calc': [tco2eLine(fuelGhgTotal)],
        'fuel-energy-calc': [numLine(fuelEnergyGj, 'GJ', 2)],
        'fugitive-calc': [tco2eLine(fugitiveTotal)],
        'grid-ghg-calc': [tco2eLine(gridGhgTotal)],
        'grid-energy-calc': [numLine(gridEnergyGj, 'GJ', 2)],

        'scope1-total': [numLine(carbon.scope1_tco2e, 'tCO2e', 2), ...(scope1Breakdown ? [scope1Breakdown] : [])],
        'scope2-total': [numLine(carbon.scope2_location_based_tco2e, 'tCO2e', 2), ...(scope2Breakdown ? [scope2Breakdown] : [])],
        'scope3-total': ['Not calculated yet'],
        'energy-total': [numLine(intensity.energy_gj, 'GJ', 1), ...(energyBreakdown ? [energyBreakdown] : [])],
        'water-total': [numLine(intensity.water_kl, 'KL', 0)],
        'waste-total': [numLine(intensity.waste_mt, 'MT', 1)],

        'total-ghg': [numLine(carbon.scope1_2_location_based_tco2e, 'tCO2e', 2), ...(totalGhgBreakdown ? [totalGhgBreakdown] : [])],

        'intensity-production': [
          numLine(carbon.intensity_tco2e_per_mnah, 'tCO2e/MnAh', 3),
          ...(intensityProductionRatio ? [intensityProductionRatio] : []),
          numLine(intensity.energy_per_production, 'GJ/MnAh', 2),
          numLine(intensity.water_per_production, 'KL/MnAh', 1),
          numLine(intensity.waste_per_production, 'MT/MnAh', 2)
        ],
        'intensity-revenue': [
          numLine(intensity.ghg_per_revenue, 'tCO2e/Cr', 3),
          ...(intensityRevenueRatio ? [intensityRevenueRatio] : []),
          numLine(intensity.energy_per_revenue, 'GJ/Cr', 2),
          numLine(intensity.water_per_revenue, 'KL/Cr', 1),
          numLine(intensity.waste_per_revenue, 'MT/Cr', 2)
        ],

        'target-comparison':
          targets.length > 0
            ? targets.map((t) => `${t.metric_label}: ${t.current_status_label ?? 'Not enough data'}`)
            : ['No active targets'],

        'unresolved-queue': [`${unresolvedCount} ${unresolvedCount === 1 ? 'entry' : 'entries'} pending`],
        'missing-factor': unresolvedCount > 0 ? ['Currently active'] : ['None this period'],

        dashboard: []
      };

      this.extraLines = {};
    } catch {
      this.lines = {};
    } finally {
      this.loading.set(false);
    }
  }

  periodLabel(): string {
    const d = new Date(`${this.period()}T00:00:00`);
    if (this.periodMode() === 'month') return d.toLocaleDateString('en-US', { month: 'long', year: 'numeric' });
    if (this.periodMode() === 'quarter') return `Q${Math.floor(d.getMonth() / 3) + 1} ${d.getFullYear()} to date`;
    return `Year to date, ${d.getFullYear()}`;
  }

  // -- Mode-aware period picker (mirrors the dashboard's) ------------------

  quarterOptions(): PeriodOption[] {
    const now = new Date();
    let year = now.getFullYear();
    let quarter = Math.floor(now.getMonth() / 3) + 1;
    const options: PeriodOption[] = [];
    for (let i = 0; i < 8; i++) {
      options.push({ value: periodValue(year, quarter * 3), label: `Q${quarter} ${year}` });
      quarter -= 1;
      if (quarter === 0) {
        quarter = 4;
        year -= 1;
      }
    }
    return options;
  }

  yearOptions(): PeriodOption[] {
    const now = new Date();
    const options: PeriodOption[] = [];
    for (let i = 0; i < 5; i++) {
      const year = now.getFullYear() - i;
      const anchorMonth = year === now.getFullYear() ? now.getMonth() + 1 : 12;
      options.push({ value: periodValue(year, anchorMonth), label: `${year}` });
    }
    return options;
  }

  async setPeriodMode(mode: PeriodMode): Promise<void> {
    this.periodMode.set(mode);
    if (mode === 'quarter') {
      this.period.set(this.quarterOptions()[0].value);
    } else if (mode === 'ytd') {
      this.period.set(this.yearOptions()[0].value);
    } else {
      this.period.set(currentPeriod());
    }
    await this.load();
  }

  async setPeriod(value: string): Promise<void> {
    this.period.set(value);
    await this.load();
  }

  monthInputValue(): string {
    return this.period().slice(0, 7);
  }

  async setMonthPeriod(value: string): Promise<void> {
    await this.setPeriod(`${value}-01`);
  }

  nodeLines(node: FlowNode): string[] {
    return this.lines[node.id] ?? [];
  }

  private static readonly LINE_HEIGHT = 13;

  private contentTop(node: FlowNode): number {
    const n = this.nodeLines(node).length;
    const totalH = (n + 1) * FlowDiagramComponent.LINE_HEIGHT;
    return (node.h - totalH) / 2;
  }

  labelY(node: FlowNode): number {
    return this.contentTop(node) + FlowDiagramComponent.LINE_HEIGHT - 2;
  }

  lineY(node: FlowNode, index: number): number {
    return this.contentTop(node) + (index + 2) * FlowDiagramComponent.LINE_HEIGHT - 2;
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
    this.viewBox.set({ x: 0, y: 0, w: 2020, h: 1010 });
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
    const nodeLines = this.lines[node.id] ?? [];
    this.detail.set({
      title: node.label,
      live: node.live,
      value: nodeLines[0] ?? null,
      extraValues: nodeLines.slice(1),
      formula: this.formulaFor(node),
      note: this.noteFor(node),
      loading: !!node.sourceName,
      evidence: []
    });

    if (node.sourceName) {
      try {
        const evidence = await this.carbonApi.getCalculations(this.period(), {
          dataPointName: node.sourceName,
          periodMode: this.periodMode(),
          locationId: this.locationId() || undefined
        });
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
        return 'Not calculated yet — deliberately deferred';
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
        return 'Entered directly, never calculated — LTIFR is provided by HR';
      case 'dashboard':
        return 'Four tabs: Absolute Metrics, Intensity by Production, Intensity by Revenue, Safety & Trends';
      default:
        return 'Approved activity entry for the current period';
    }
  }

  private noteFor(node: FlowNode): string {
    if (!node.live) return 'Planned — not calculated yet.';
    switch (node.kind) {
      case 'input':
        return node.sourceName
          ? 'Click a row below to see the exact factor version used for that entry.'
          : 'Read from the same approved entries the rest of the dashboard uses.';
      case 'warning':
        return 'Never silently estimated — the entry is set aside until a human fixes the underlying data.';
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

  /** Spotlights one or more target nodes plus everything that feeds them --
   * walked backward through the edge list, same graph the Play animation
   * uses, just resolved instantly instead of staged. Used when a dashboard
   * card deep-links straight to "how was this number built". */
  highlightPath(targetIds: string[]): void {
    const validTargets = targetIds.filter((id) => this.nodes.some((n) => n.id === id));
    if (validTargets.length === 0) return;

    const nodeIds = new Set<string>(validTargets);
    const edgeKeys = new Set<string>();
    let frontier = [...validTargets];
    while (frontier.length > 0) {
      const next: string[] = [];
      for (const id of frontier) {
        for (const edge of this.edges) {
          if (edge.to !== id) continue;
          edgeKeys.add(`${edge.from}->${edge.to}`);
          if (!nodeIds.has(edge.from)) {
            nodeIds.add(edge.from);
            next.push(edge.from);
          }
        }
      }
      frontier = next;
    }

    this.activeNodeIds.set(nodeIds);
    this.activeEdgeKeys.set(edgeKeys);
    this.fitToNodes([...nodeIds]);
    if (validTargets.length > 0) {
      const first = this.nodes.find((n) => n.id === validTargets[0]);
      if (first) this.selectNode(first);
    }
  }

  private fitToNodes(nodeIds: string[]): void {
    const targetNodes = this.nodes.filter((n) => nodeIds.includes(n.id));
    if (targetNodes.length === 0) return;
    const pad = 90;
    const minX = Math.min(...targetNodes.map((n) => n.x)) - pad;
    const minY = Math.min(...targetNodes.map((n) => n.y)) - pad;
    const maxX = Math.max(...targetNodes.map((n) => n.x + n.w)) + pad;
    const maxY = Math.max(...targetNodes.map((n) => n.y + n.h)) + pad;
    this.viewBox.set({ x: minX, y: minY, w: Math.max(maxX - minX, 400), h: Math.max(maxY - minY, 300) });
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

  /** True whenever any node is spotlit (mid-Play or a deep-linked
   * highlight) -- drives dimming everything else so the lit path actually
   * reads as "this is the answer", not just one more highlighted node
   * among equals. */
  isHighlighting(): boolean {
    return this.activeNodeIds().size > 0;
  }

  isNodeActive(node: FlowNode): boolean {
    return this.activeNodeIds().has(node.id);
  }
}
