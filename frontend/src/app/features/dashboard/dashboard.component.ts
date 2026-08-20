import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { AdminLocation, ApiService } from '../../core/api.service';
import { CarbonApiService } from '../../core/carbon-api.service';
import { PeriodMode } from '../../core/intensity-api.service';
import { ReportFormat, ReportsApiService } from '../../core/reports-api.service';
import { AbsoluteMetricsViewComponent } from './absolute-metrics-view/absolute-metrics-view.component';
import { IntensityViewComponent } from './intensity-view/intensity-view.component';
import { OverallViewComponent } from './overall-view/overall-view.component';
import { SafetyViewComponent } from './safety-view/safety-view.component';

type TabId = 'overall' | 'absolute' | 'production' | 'revenue' | 'safety';

function currentMonthValue(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
}

function monthValue(year: number, month: number): string {
  return `${year}-${String(month).padStart(2, '0')}`;
}

export interface PickerOption {
  value: string;
  label: string;
}

@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [FormsModule, RouterLink, OverallViewComponent, AbsoluteMetricsViewComponent, IntensityViewComponent, SafetyViewComponent],
  templateUrl: './dashboard.component.html',
  styleUrl: './dashboard.component.css'
})
export class DashboardComponent implements OnInit {
  private api = inject(ApiService);
  private carbonApi = inject(CarbonApiService);
  private reportsApi = inject(ReportsApiService);

  period = signal(currentMonthValue());
  periodMode = signal<PeriodMode>('month');
  locationId = signal<string>(''); // '' = company-wide
  activeTab = signal<TabId>('overall');
  locations = signal<AdminLocation[]>([]);
  unresolvedCount = signal(0);
  // Bumped on every click of the unresolved badge -- passed down through
  // absolute-metrics-view to carbon-overview (where the actual unresolved
  // list lives) as a plain counter so the same click always re-triggers
  // even if the panel's already open, instead of a boolean that could
  // silently no-op on a second click.
  unresolvedRequestId = signal(0);

  downloadingFormat = signal<ReportFormat | null>(null);
  downloadError = signal('');

  async ngOnInit(): Promise<void> {
    this.locations.set(await this.api.listLocations());
    await this.refreshUnresolvedBadge();
  }

  /** The badge used to link to /admin/data-entry, which has nothing to do
   * with unresolved GHG calculations (a distinct concept from an Entry's
   * own Draft/Submitted/Approved workflow status) -- there was nowhere on
   * that page to actually find them. This jumps to the tab that has the
   * real unresolved list (Absolute Metrics' Carbon footprint card) and
   * opens it directly instead. */
  focusUnresolved(): void {
    this.activeTab.set('absolute');
    this.unresolvedRequestId.set(this.unresolvedRequestId() + 1);
  }

  async refreshUnresolvedBadge(): Promise<void> {
    try {
      const items = await this.carbonApi.getUnresolved(this.locationId() || undefined);
      this.unresolvedCount.set(items.length);
    } catch {
      // Non-critical badge -- a failed fetch shouldn't block the rest of the dashboard.
    }
  }

  setTab(tab: TabId): void {
    this.activeTab.set(tab);
  }

  onFiltersChange(): void {
    void this.refreshUnresolvedBadge();
  }

  async downloadReport(format: ReportFormat): Promise<void> {
    if (this.downloadingFormat()) return;
    this.downloadingFormat.set(format);
    this.downloadError.set('');
    try {
      await this.reportsApi.downloadDashboardReport(format, `${this.period()}-01`, this.periodMode(), this.effectiveLocationId() ?? undefined);
    } catch {
      this.downloadError.set('Could not generate the report. Please try again.');
    } finally {
      this.downloadingFormat.set(null);
    }
  }

  formatMonth(): string {
    const d = new Date(`${this.period()}-01T00:00:00`);
    return d.toLocaleDateString('en-US', { month: 'long', year: 'numeric' });
  }

  formatPeriodLabel(): string {
    const d = new Date(`${this.period()}-01T00:00:00`);
    if (this.periodMode() === 'month') return this.formatMonth();
    if (this.periodMode() === 'quarter') {
      const quarter = Math.floor(d.getMonth() / 3) + 1;
      return `Q${quarter} ${d.getFullYear()} to date`;
    }
    return `Year to date, ${d.getFullYear()}`;
  }

  effectiveLocationId(): string | null {
    return this.locationId() || null;
  }

  // -- Mode-aware period picker -------------------------------------------
  // Quarterly/YTD pick a whole calendar bucket (a quarter, a year), not an
  // arbitrary day -- the native month input only fits Monthly mode. The
  // anchor month sent to the API is still derived from the pick (last
  // month of the quarter / current-or-December for the year), and the
  // backend naturally truncates to "to date" for a still-in-progress
  // bucket since months without approved data are excluded, not zeroed.

  quarterOptions(): PickerOption[] {
    const now = new Date();
    let year = now.getFullYear();
    let quarter = Math.floor(now.getMonth() / 3) + 1;
    const options: PickerOption[] = [];
    for (let i = 0; i < 8; i++) {
      options.push({ value: monthValue(year, quarter * 3), label: `Q${quarter} ${year}` });
      quarter -= 1;
      if (quarter === 0) {
        quarter = 4;
        year -= 1;
      }
    }
    return options;
  }

  yearOptions(): PickerOption[] {
    const now = new Date();
    const options: PickerOption[] = [];
    for (let i = 0; i < 5; i++) {
      const year = now.getFullYear() - i;
      const anchorMonth = year === now.getFullYear() ? now.getMonth() + 1 : 12;
      options.push({ value: monthValue(year, anchorMonth), label: `${year}` });
    }
    return options;
  }

  setPeriodMode(mode: PeriodMode): void {
    this.periodMode.set(mode);
    if (mode === 'quarter') {
      this.period.set(this.quarterOptions()[0].value);
    } else if (mode === 'ytd') {
      this.period.set(this.yearOptions()[0].value);
    } else {
      this.period.set(currentMonthValue());
    }
  }
}
