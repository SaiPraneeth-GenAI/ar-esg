import { DecimalPipe } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { CarbonApiService, CarbonOverview, CarbonOverviewSource, EmissionCalculationOut } from '../../../core/carbon-api.service';
import { EntryHistoryComponent } from '../../data-entry/entry-history/entry-history.component';

function currentMonthValue(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
}

function sourceKey(s: CarbonOverviewSource): string {
  return `${s.data_point_name}:${s.scope}:${s.calculation_method ?? ''}`;
}

@Component({
  selector: 'app-carbon-overview',
  standalone: true,
  imports: [FormsModule, DecimalPipe, EntryHistoryComponent],
  templateUrl: './carbon-overview.component.html',
  styleUrl: './carbon-overview.component.css'
})
export class CarbonOverviewComponent implements OnInit {
  private api = inject(CarbonApiService);

  monthValue = signal(currentMonthValue());
  loading = signal(true);
  errorMessage = signal('');
  overview = signal<CarbonOverview | null>(null);

  expandedSourceKey = signal<string | null>(null);
  sourceCalculations = signal<EmissionCalculationOut[]>([]);
  sourceLoading = signal(false);
  expandedEntryId = signal<string | null>(null);

  showUnresolved = signal(false);
  unresolvedItems = signal<EmissionCalculationOut[]>([]);
  unresolvedLoading = signal(false);

  sourceKey = sourceKey;

  async ngOnInit(): Promise<void> {
    await this.load();
  }

  private periodIso(): string {
    return `${this.monthValue()}-01`;
  }

  async load(): Promise<void> {
    this.loading.set(true);
    this.errorMessage.set('');
    this.expandedSourceKey.set(null);
    this.showUnresolved.set(false);
    try {
      this.overview.set(await this.api.getOverview(this.periodIso()));
    } catch {
      this.errorMessage.set('Could not load the carbon overview.');
    } finally {
      this.loading.set(false);
    }
  }

  async onMonthChange(): Promise<void> {
    await this.load();
  }

  async toggleSource(source: CarbonOverviewSource): Promise<void> {
    const key = sourceKey(source);
    if (this.expandedSourceKey() === key) {
      this.expandedSourceKey.set(null);
      return;
    }
    this.expandedSourceKey.set(key);
    this.expandedEntryId.set(null);
    this.sourceLoading.set(true);
    try {
      this.sourceCalculations.set(
        await this.api.getCalculations(this.periodIso(), {
          scope: source.scope,
          calculationMethod: source.calculation_method ?? undefined,
          dataPointName: source.data_point_name
        })
      );
    } finally {
      this.sourceLoading.set(false);
    }
  }

  toggleEntryHistory(entryId: string): void {
    this.expandedEntryId.set(this.expandedEntryId() === entryId ? null : entryId);
  }

  async toggleUnresolved(): Promise<void> {
    this.showUnresolved.set(!this.showUnresolved());
    this.expandedSourceKey.set(null);
    if (!this.showUnresolved()) return;
    this.unresolvedLoading.set(true);
    try {
      this.unresolvedItems.set(await this.api.getUnresolved());
    } finally {
      this.unresolvedLoading.set(false);
    }
  }

  formatMonth(period: string | null): string {
    if (!period) return '';
    return new Date(`${period}T00:00:00`).toLocaleDateString('en-US', { month: 'long', year: 'numeric' });
  }

  comparisonLabel(current: number | null, prior: number | null): string {
    if (current === null) return 'No data yet';
    if (prior === null || prior === 0) return 'No comparison available';
    const pct = ((current - prior) / prior) * 100;
    return `${Math.abs(pct).toFixed(0)}% ${pct > 0 ? 'higher' : 'lower'} than last month`;
  }

  comparisonStatus(current: number | null, prior: number | null): 'green' | 'amber' | 'red' | 'neutral' {
    if (current === null || prior === null || prior === 0) return 'neutral';
    const pct = ((current - prior) / prior) * 100;
    if (pct <= 0) return 'green';
    if (pct <= 10) return 'amber';
    return 'red';
  }

  completenessStatus(pct: number | null): 'green' | 'amber' | 'red' | 'neutral' {
    if (pct === null) return 'neutral';
    if (pct >= 95) return 'green';
    if (pct >= 75) return 'amber';
    return 'red';
  }
}
