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
  showPanel = signal(false);

  scope1Factors = computed(() => this.factors().filter((f) => f.scope === 1));
  scope2Factors = computed(() => this.factors().filter((f) => f.scope === 2));
  scope3Factors = computed(() => this.factors().filter((f) => f.scope === 3));

  async ngOnInit(): Promise<void> {
    await this.refresh();
  }

  async refresh(): Promise<void> {
    this.loading.set(true);
    this.errorMessage.set('');
    try {
      this.factors.set(await this.api.list());
    } catch {
      this.errorMessage.set('Could not load emission factors.');
    } finally {
      this.loading.set(false);
    }
  }

  openPanel(): void {
    this.showPanel.set(true);
  }

  closePanel(): void {
    this.showPanel.set(false);
  }

  async onSaved(): Promise<void> {
    this.showPanel.set(false);
    this.successMessage.set('Emission factor saved.');
    await this.refresh();
  }

  displayName(f: EmissionFactorOut): string {
    if (f.scope === 1) return f.gas_type ?? '—';
    if (f.scope === 2) return f.method ?? '—';
    return f.scope3_category ?? '—';
  }

  onBulkUploadDone(): void {
    this.mode.set('list');
    void this.refresh();
  }
}
