import { DecimalPipe } from '@angular/common';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { TargetApiService, TargetMonthPerformance, TargetOut, TargetStatus } from '../../../core/target-api.service';
import { TargetWizardComponent } from './target-wizard.component';

@Component({
  selector: 'app-targets',
  standalone: true,
  imports: [FormsModule, DecimalPipe, TargetWizardComponent],
  templateUrl: './targets.component.html',
  styleUrl: './targets.component.css'
})
export class TargetsComponent implements OnInit {
  private api = inject(TargetApiService);

  loading = signal(true);
  errorMessage = signal('');
  successMessage = signal('');
  targets = signal<TargetOut[]>([]);
  activeTab = signal<TargetStatus>('active');

  showWizard = signal(false);

  expandedId = signal<string | null>(null);
  performanceMonths = signal<TargetMonthPerformance[]>([]);
  performanceLoading = signal(false);

  activatingId = signal<string | null>(null);
  activateRationale = signal('');

  tabCounts = computed(() => {
    const all = this.targets();
    return {
      draft: all.filter((t) => t.status === 'draft').length,
      active: all.filter((t) => t.status === 'active').length,
      archived: all.filter((t) => t.status === 'archived').length
    };
  });

  visibleTargets = computed(() => this.targets().filter((t) => t.status === this.activeTab()));

  async ngOnInit(): Promise<void> {
    await this.refresh();
  }

  async refresh(): Promise<void> {
    this.loading.set(true);
    this.errorMessage.set('');
    try {
      this.targets.set(await this.api.list());
    } catch {
      this.errorMessage.set('Could not load targets.');
    } finally {
      this.loading.set(false);
    }
  }

  setTab(tab: TargetStatus): void {
    this.activeTab.set(tab);
    this.expandedId.set(null);
  }

  boundaryLabel(t: TargetOut): string {
    const scopeLabel = t.scope === '1_2_combined' ? 'Scope 1+2' : `Scope ${t.scope}`;
    const method = t.calculation_method ? ` (${t.calculation_method === 'location_based' ? 'location-based' : 'market-based'})` : '';
    const metric =
      t.metric_type === 'intensity_tco2e_per_mnah'
        ? 'intensity by production'
        : t.metric_type === 'intensity_tco2e_per_revenue'
          ? 'intensity by revenue'
          : 'absolute';
    return `${scopeLabel}${method} -- ${metric}`;
  }

  unit(t: TargetOut): string {
    if (t.metric_type === 'intensity_tco2e_per_mnah') return 'tCO2e/MnAh';
    if (t.metric_type === 'intensity_tco2e_per_revenue') return 'tCO2e/Cr';
    return 'tCO2e';
  }

  statusClass(label: string | null): string {
    switch (label) {
      case 'On track':
        return 'status-green';
      case 'Watch':
        return 'status-amber';
      case 'Off track':
        return 'status-red';
      default:
        return 'status-neutral';
    }
  }

  openWizard(): void {
    this.showWizard.set(true);
  }

  closeWizard(): void {
    this.showWizard.set(false);
  }

  async onWizardSaved(): Promise<void> {
    this.showWizard.set(false);
    this.successMessage.set('Target saved.');
    await this.refresh();
  }

  startActivate(t: TargetOut): void {
    this.activatingId.set(t.id);
    this.activateRationale.set('');
  }

  cancelActivate(): void {
    this.activatingId.set(null);
  }

  async confirmActivate(t: TargetOut): Promise<void> {
    if (!this.activateRationale().trim()) return;
    try {
      await this.api.activate(t.id, this.activateRationale());
      this.activatingId.set(null);
      this.successMessage.set('Target activated.');
      await this.refresh();
    } catch (err: any) {
      this.errorMessage.set(err?.error?.detail ?? 'Could not activate this target.');
    }
  }

  async archiveTarget(t: TargetOut): Promise<void> {
    try {
      await this.api.archive(t.id);
      this.successMessage.set('Target archived.');
      await this.refresh();
    } catch {
      this.errorMessage.set('Could not archive this target.');
    }
  }

  async restoreTarget(t: TargetOut): Promise<void> {
    try {
      await this.api.restore(t.id);
      this.successMessage.set('Target restored as a draft -- review it and reactivate when ready.');
      await this.refresh();
    } catch {
      this.errorMessage.set('Could not restore this target.');
    }
  }

  async deleteTarget(t: TargetOut): Promise<void> {
    try {
      await this.api.remove(t.id);
      this.successMessage.set('Draft deleted.');
      await this.refresh();
    } catch {
      this.errorMessage.set('Could not delete this draft.');
    }
  }

  async toggleExpand(t: TargetOut): Promise<void> {
    if (this.expandedId() === t.id) {
      this.expandedId.set(null);
      return;
    }
    this.expandedId.set(t.id);
    this.performanceLoading.set(true);
    try {
      const perf = await this.api.performance(t.id);
      this.performanceMonths.set(perf.months);
    } finally {
      this.performanceLoading.set(false);
    }
  }
}
