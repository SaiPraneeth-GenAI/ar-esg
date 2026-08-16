import { Component, EventEmitter, Input, OnInit, Output, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import {
  EmissionFactorCreate,
  EmissionFactorOut,
  EmissionFactorsApiService,
  IpccSearchResult,
  IpccVersionOut
} from '../../../core/emission-factors-api.service';

const CURRENT_YEAR = new Date().getFullYear();

const SCOPE3_CATEGORIES = [
  'Purchased Goods & Services',
  'Capital Goods',
  'Fuel- and Energy-Related Activities',
  'Upstream Transportation & Distribution',
  'Waste Generated in Operations',
  'Business Travel',
  'Employee Commuting',
  'Upstream Leased Assets',
  'Downstream Transportation & Distribution',
  'Processing of Sold Products',
  'Use of Sold Products',
  'End-of-Life Treatment of Sold Products',
  'Downstream Leased Assets',
  'Franchises',
  'Investments'
];

type PanelMode = 'search' | 'ipcc-selected' | 'manual';

interface BreakdownLine {
  label: string;
  value: string;
}

@Component({
  selector: 'app-add-factor-panel',
  standalone: true,
  imports: [FormsModule],
  templateUrl: './add-factor-panel.component.html',
  styleUrl: './add-factor-panel.component.css'
})
export class AddFactorPanelComponent implements OnInit {
  private api = inject(EmissionFactorsApiService);
  @Input() editingFactor: EmissionFactorOut | null = null;
  @Output() closed = new EventEmitter<void>();
  @Output() saved = new EventEmitter<void>();

  scope3Categories = SCOPE3_CATEGORIES;

  mode = signal<PanelMode>('search');
  isEditing = signal(false);
  isActive = signal(true);

  // Search
  searchQuery = signal('');
  searchResults = signal<IpccSearchResult[]>([]);
  searching = signal(false);
  private searchTimer: ReturnType<typeof setTimeout> | null = null;

  // IPCC-assisted
  selectedSubstance = signal<IpccSearchResult | null>(null);
  versions = signal<IpccVersionOut[]>([]);
  selectedVersionId = signal<string | null>(null);
  calculated = signal(false);

  selectedVersion = computed(() => this.versions().find((v) => v.id === this.selectedVersionId()) ?? null);

  breakdown = computed<BreakdownLine[]>(() => {
    const v = this.selectedVersion();
    if (!v) return [];
    if (v.factor_type === 'fuel' && v.ncv_mj_per_unit != null && v.co2_ef_per_tj != null) {
      const lines: BreakdownLine[] = [
        { label: 'NCV', value: `${v.ncv_mj_per_unit} MJ/kg` },
        { label: '× CO2 EF', value: `${v.co2_ef_per_tj.toLocaleString()} kg CO2/TJ` },
        { label: '÷ 1,000,000', value: '' }
      ];
      if (v.oxidation_factor != null) {
        lines.push({ label: '× Oxidation factor', value: `${v.oxidation_factor}` });
      }
      if (v.density_kg_per_unit != null) {
        lines.push({ label: '× Density', value: `${v.density_kg_per_unit} kg/L` });
      }
      lines.push({ label: '=', value: `${v.derived_factor_value} ${v.unit}` });
      return lines;
    }
    if (v.factor_type === 'gwp') {
      return [
        { label: 'Published GWP-100 lookup', value: `${v.publication}` },
        { label: '=', value: `${v.derived_factor_value} ${v.unit}` }
      ];
    }
    if (v.factor_type === 'grid_electricity') {
      return [
        { label: 'Published CEA baseline value', value: `${v.publication}` },
        { label: '=', value: `${v.derived_factor_value} ${v.unit}` }
      ];
    }
    return [{ label: 'Published reference value', value: `${v.derived_factor_value} ${v.unit}` }];
  });

  // Shared editable result
  resultValue = signal<number | null>(null);
  resultModified = computed(() => {
    const v = this.selectedVersion();
    return v !== null && this.resultValue() !== null && this.resultValue() !== v.derived_factor_value;
  });

  // Manual / shared fields
  manualScope = signal(1);
  gasType = signal('');
  method = signal('');
  scope3Category = signal('');
  description = signal('');
  unit = signal('');
  effectiveYear = signal(CURRENT_YEAR);
  source = signal('');
  sourceReference = signal('');

  submitting = signal(false);
  formError = signal('');

  effectiveScope = computed(() => (this.mode() === 'ipcc-selected' ? this.selectedSubstance()?.scope ?? 1 : this.manualScope()));

  canSave = computed(() => {
    if (!this.unit().trim() || this.resultValue() === null || !this.sourceReference().trim()) return false;
    const scope = this.effectiveScope();
    if (scope === 1) return !!this.gasType().trim();
    if (scope === 2) return !!this.method();
    if (scope === 3) return !!this.scope3Category();
    return false;
  });

  ngOnInit(): void {
    const f = this.editingFactor;
    if (!f) return;
    this.isEditing.set(true);
    this.isActive.set(f.is_active);
    this.mode.set('manual');
    this.manualScope.set(f.scope);
    this.gasType.set(f.gas_type ?? '');
    this.method.set(f.method ?? '');
    this.scope3Category.set(f.scope3_category ?? '');
    this.description.set(f.description ?? '');
    this.unit.set(f.unit);
    this.effectiveYear.set(f.effective_year);
    this.source.set(f.source ?? '');
    this.sourceReference.set(f.source_reference ?? '');
    this.resultValue.set(f.factor_value);
  }

  onSearchInput(q: string): void {
    this.searchQuery.set(q);
    if (this.searchTimer) clearTimeout(this.searchTimer);
    if (!q.trim()) {
      this.searchResults.set([]);
      return;
    }
    this.searchTimer = setTimeout(() => void this.runSearch(q), 180);
  }

  private async runSearch(q: string): Promise<void> {
    this.searching.set(true);
    try {
      this.searchResults.set(await this.api.searchIpccReference(q));
    } finally {
      this.searching.set(false);
    }
  }

  async selectSubstance(result: IpccSearchResult): Promise<void> {
    this.selectedSubstance.set(result);
    this.mode.set('ipcc-selected');
    this.gasType.set(result.substance_name);
    this.calculated.set(false);
    this.resultValue.set(null);
    const versions = await this.api.listIpccVersions(result.substance_name);
    this.versions.set(versions);
    if (versions.length > 0) {
      this.selectedVersionId.set(versions[0].id);
      this.unit.set(versions[0].unit);
      this.sourceReference.set(versions[0].source_reference);
    }
  }

  onVersionChange(id: string): void {
    this.selectedVersionId.set(id);
    this.calculated.set(false);
    this.resultValue.set(null);
    const v = this.versions().find((x) => x.id === id);
    if (v) {
      this.unit.set(v.unit);
      this.sourceReference.set(v.source_reference);
    }
  }

  calculate(): void {
    const v = this.selectedVersion();
    if (!v) return;
    this.resultValue.set(v.derived_factor_value);
    this.calculated.set(true);
  }

  goManual(): void {
    this.mode.set('manual');
    this.selectedSubstance.set(null);
    this.versions.set([]);
    this.selectedVersionId.set(null);
    this.calculated.set(false);
  }

  backToSearch(): void {
    this.mode.set('search');
    this.selectedSubstance.set(null);
    this.resultValue.set(null);
    this.resetSharedFields();
  }

  private resetSharedFields(): void {
    this.gasType.set('');
    this.method.set('');
    this.scope3Category.set('');
    this.description.set('');
    this.unit.set('');
    this.effectiveYear.set(CURRENT_YEAR);
    this.source.set('');
    this.sourceReference.set('');
  }

  async save(): Promise<void> {
    if (!this.canSave() || this.submitting()) return;
    this.submitting.set(true);
    this.formError.set('');
    const scope = this.effectiveScope();
    const payload: EmissionFactorCreate = {
      scope,
      unit: this.unit().trim(),
      factor_value: this.resultValue()!,
      effective_year: this.mode() === 'ipcc-selected' ? this.selectedVersion()?.effective_year ?? this.effectiveYear() : this.effectiveYear(),
      source: this.source().trim() || null,
      source_reference: this.sourceReference().trim(),
      // Editing always lands on the manual form (see ngOnInit), which
      // would otherwise silently clear an existing IPCC link on every
      // edit -- preserve whatever the factor already had unless this
      // save is actually coming from a fresh IPCC selection.
      ipcc_reference_key: this.isEditing()
        ? this.editingFactor?.ipcc_reference_key ?? null
        : this.mode() === 'ipcc-selected'
          ? this.selectedVersionId()
          : null
    };
    if (scope === 1) payload.gas_type = this.gasType().trim();
    if (scope === 2) payload.method = this.method();
    if (scope === 3) {
      payload.scope3_category = this.scope3Category();
      payload.description = this.description().trim() || null;
    }

    try {
      if (this.isEditing() && this.editingFactor) {
        await this.api.update(this.editingFactor.id, { ...payload, is_active: this.isActive() });
      } else {
        await this.api.create(payload);
      }
      this.saved.emit();
    } catch (err) {
      this.formError.set(this.extractError(err) ?? 'Could not save this factor.');
    } finally {
      this.submitting.set(false);
    }
  }

  private extractError(err: unknown): string | null {
    const httpErr = err as { error?: { detail?: unknown } };
    const detail = httpErr?.error?.detail;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail) && detail[0]?.msg) return String(detail[0].msg).replace('Value error, ', '');
    return null;
  }

  close(): void {
    this.closed.emit();
  }
}
