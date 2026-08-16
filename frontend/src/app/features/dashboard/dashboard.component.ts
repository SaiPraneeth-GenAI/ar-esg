import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { AdminLocation, ApiService } from '../../core/api.service';
import { CarbonApiService } from '../../core/carbon-api.service';
import { PeriodMode } from '../../core/intensity-api.service';
import { AbsoluteMetricsViewComponent } from './absolute-metrics-view/absolute-metrics-view.component';
import { IntensityViewComponent } from './intensity-view/intensity-view.component';
import { SafetyViewComponent } from './safety-view/safety-view.component';

type TabId = 'absolute' | 'production' | 'revenue' | 'safety';

function currentMonthValue(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
}

@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [FormsModule, RouterLink, AbsoluteMetricsViewComponent, IntensityViewComponent, SafetyViewComponent],
  templateUrl: './dashboard.component.html',
  styleUrl: './dashboard.component.css'
})
export class DashboardComponent implements OnInit {
  private api = inject(ApiService);
  private carbonApi = inject(CarbonApiService);

  period = signal(currentMonthValue());
  periodMode = signal<PeriodMode>('month');
  locationId = signal<string>(''); // '' = company-wide
  activeTab = signal<TabId>('absolute');
  locations = signal<AdminLocation[]>([]);
  unresolvedCount = signal(0);

  async ngOnInit(): Promise<void> {
    this.locations.set(await this.api.listLocations());
    await this.refreshUnresolvedBadge();
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
}
