import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { EmissionFactorOut, EmissionFactorsApiService } from '../../../core/emission-factors-api.service';
import { AddFactorPanelComponent } from './add-factor-panel.component';
import { EmissionFactorBulkUploadWizardComponent } from './emission-factor-bulk-upload-wizard.component';

@Component({
  selector: 'app-emission-factors',
  standalone: true,
  imports: [EmissionFactorBulkUploadWizardComponent, AddFactorPanelComponent],
  templateUrl: './emission-factors.component.html',
  styleUrl: './emission-factors.component.css'
})
export class EmissionFactorsComponent implements OnInit {
  private api = inject(EmissionFactorsApiService);

  loading = signal(true);
  errorMessage = signal('');
  successMessage = signal('');
  factors = signal<EmissionFactorOut[]>([]);
  mode = signal<'list' | 'bulk'>('list');
  activeScope = signal(1);
  showInactive = signal(false);

  showPanel = signal(false);
  editingFactor = signal<EmissionFactorOut | null>(null);

  scopeCounts = computed(() => {
    const all = this.factors();
    return {
      1: all.filter((f) => f.scope === 1).length,
      2: all.filter((f) => f.scope === 2).length,
      3: all.filter((f) => f.scope === 3).length
    };
  });

  visibleFactors = computed(() => this.factors().filter((f) => f.scope === this.activeScope()));

  async ngOnInit(): Promise<void> {
    await this.refresh();
  }

  async refresh(): Promise<void> {
    this.loading.set(true);
    this.errorMessage.set('');
    try {
      this.factors.set(await this.api.list(undefined, this.showInactive()));
    } catch {
      this.errorMessage.set('Could not load emission factors.');
    } finally {
      this.loading.set(false);
    }
  }

  async toggleShowInactive(): Promise<void> {
    this.showInactive.set(!this.showInactive());
    await this.refresh();
  }

  setScope(scope: number): void {
    this.activeScope.set(scope);
  }

  openAddPanel(): void {
    this.editingFactor.set(null);
    this.showPanel.set(true);
  }

  openEditPanel(factor: EmissionFactorOut): void {
    this.editingFactor.set(factor);
    this.showPanel.set(true);
  }

  closePanel(): void {
    this.showPanel.set(false);
    this.editingFactor.set(null);
  }

  async onSaved(): Promise<void> {
    const wasEditing = this.editingFactor() !== null;
    this.showPanel.set(false);
    this.editingFactor.set(null);
    this.successMessage.set(wasEditing ? 'Emission factor updated.' : 'Emission factor saved.');
    await this.refresh();
  }

  async toggleActive(factor: EmissionFactorOut): Promise<void> {
    try {
      await this.api.update(factor.id, {
        scope: factor.scope,
        gas_type: factor.gas_type,
        method: factor.method,
        scope3_category: factor.scope3_category,
        description: factor.description,
        unit: factor.unit,
        factor_value: factor.factor_value,
        effective_year: factor.effective_year,
        source: factor.source,
        source_reference: factor.source_reference ?? '',
        ipcc_reference_key: factor.ipcc_reference_key,
        is_active: !factor.is_active
      });
      await this.refresh();
    } catch {
      this.errorMessage.set('Could not update this factor.');
    }
  }

  displayName(f: EmissionFactorOut): string {
    if (f.scope === 1) return f.gas_type ?? '—';
    if (f.scope === 2) return f.gas_type || f.method || '—';
    return f.scope3_category ?? '—';
  }

  onBulkUploadDone(): void {
    this.mode.set('list');
    void this.refresh();
  }
}
