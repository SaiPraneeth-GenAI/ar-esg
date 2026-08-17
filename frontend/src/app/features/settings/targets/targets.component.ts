import { DecimalPipe } from '@angular/common';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ChartPoint, ChartSeriesDef, RichTrendChartComponent } from '../../../shared/rich-trend-chart/rich-trend-chart.component';
import { TargetApiService, TargetMonthPerformance, TargetOut, TargetStatus } from '../../../core/target-api.service';
import { TargetWizardComponent } from './target-wizard.component';

function monthLabel(period: string): string {
  return new Date(`${period}T00:00:00`).toLocaleDateString('en-US', { month: 'short', year: '2-digit' });
}

@Component({
  selector: 'app-targets',
  standalone: true,
  imports: [FormsModule, DecimalPipe, TargetWizardComponent, RichTrendChartComponent],
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

  // Monthly performance is fetched for every activated/archived target up
  // front (not gated behind a click) so the visual history is the thing the
  // customer sees by default, not a feature they have to discover.
  performanceByTarget = signal<Record<string, TargetMonthPerformance[]>>({});
  performanceLoadingIds = signal<Set<string>>(new Set());
  detailsOpenId = signal<string | null>(null);

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
      const targets = await this.api.list();
      this.targets.set(targets);
      this.loadAllPerformance(targets);
    } catch {
      this.errorMessage.set('Could not load targets.');
    } finally {
      this.loading.set(false);
    }
  }

  /** Fires in parallel for every target that has locked-in performance data
   * (draft targets have no baseline/actuals to plot yet) -- one failed
   * fetch doesn't block the rest of the page from showing its history. */
  private loadAllPerformance(targets: TargetOut[]): void {
    const trackable = targets.filter((t) => t.status === 'active' || t.status === 'archived');
    this.performanceLoadingIds.set(new Set(trackable.map((t) => t.id)));
    for (const t of trackable) {
      this.api
        .performance(t.id)
        .then((perf) => {
          this.performanceByTarget.update((m) => ({ ...m, [t.id]: perf.months }));
        })
        .catch(() => {})
        .finally(() => {
          this.performanceLoadingIds.update((ids) => {
            const next = new Set(ids);
            next.delete(t.id);
            return next;
          });
        });
    }
  }

  setTab(tab: TargetStatus): void {
    this.activeTab.set(tab);
  }

  toggleDetails(t: TargetOut): void {
    this.detailsOpenId.set(this.detailsOpenId() === t.id ? null : t.id);
  }

  performanceLoading(t: TargetOut): boolean {
    return this.performanceLoadingIds().has(t.id);
  }

  performanceMonths(t: TargetOut): TargetMonthPerformance[] {
    return this.performanceByTarget()[t.id] ?? [];
  }

  hasPerformance(t: TargetOut): boolean {
    return this.performanceMonths(t).some((m) => m.actual !== null);
  }

  chartSeries(t: TargetOut): ChartSeriesDef[] {
    return [{ key: 'actual', label: t.metric_label, unit: t.metric_unit, tracked: true }];
  }

  chartPoints(t: TargetOut): ChartPoint[] {
    return this.performanceMonths(t).map((m) => ({
      period: m.period,
      label: monthLabel(m.period),
      valuesBySeries: { actual: m.actual },
      targetValuesBySeries: { actual: m.target }
    }));
  }

  /** The plain-language answer to "what do I actually need to do" -- the
   * thing the numbers on the card don't say out loud. */
  guidanceText(t: TargetOut): string {
    if (t.status === 'draft') {
      return 'Activate this target to start tracking monthly progress against it.';
    }
    if (t.status === 'archived') {
      return 'Archived -- kept for reference, no longer tracked month to month.';
    }
    if (t.baseline_value === null || t.target_value === null) {
      return 'Waiting on enough approved data to lock a baseline before progress can be tracked.';
    }
    const byWhen = new Date(`${t.target_period_end}T00:00:00`).toLocaleDateString('en-US', { month: 'long', year: 'numeric' });
    const months = this.performanceMonths(t);
    const latestActual = [...months].reverse().find((m) => m.actual !== null)?.actual ?? null;
    const reference = latestActual ?? t.baseline_value;
    const gap = reference - t.target_value;
    const closeText =
      Math.abs(gap) < 0.0001
        ? 'already at goal'
        : `${gap > 0 ? 'reduce' : 'grow'} by ${Math.abs(gap).toLocaleString(undefined, { maximumFractionDigits: 2 })} ${t.metric_unit} more`;

    switch (t.current_status_label) {
      case 'On track':
        return `On track -- hold this pace through ${byWhen} to land on target.`;
      case 'Watch':
        return `Slipping -- needs to ${closeText} to get back on pace for ${byWhen}.`;
      case 'Off track':
        return `Behind pace -- needs to ${closeText} before ${byWhen} to catch up.`;
      default:
        return `Tracking toward ${byWhen}.`;
    }
  }

  boundaryLabel(t: TargetOut): string {
    return t.metric_label;
  }

  unit(t: TargetOut): string {
    return t.metric_unit;
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

  async confirmActivate(t: TargetOut): Promise<void> {
    try {
      await this.api.activate(t.id);
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

}
