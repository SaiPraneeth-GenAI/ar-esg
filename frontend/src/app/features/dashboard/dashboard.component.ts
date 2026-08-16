import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { ApiService, DashboardCard, DrilldownResponse } from '../../core/api.service';
import { CarbonOverviewComponent } from './carbon-overview/carbon-overview.component';

interface CardGroup {
  category: string;
  cards: DashboardCard[];
}

@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [CarbonOverviewComponent],
  templateUrl: './dashboard.component.html',
  styleUrl: './dashboard.component.css'
})
export class DashboardComponent implements OnInit {
  private api = inject(ApiService);

  loading = signal(true);
  cards = signal<DashboardCard[]>([]);
  period = signal<string | null>(null);

  expandedKey = signal<string | null>(null);
  drilldown = signal<DrilldownResponse | null>(null);
  drilldownLoading = signal(false);

  groups = computed<CardGroup[]>(() => {
    const map = new Map<string, DashboardCard[]>();
    for (const card of this.cards()) {
      if (!map.has(card.category)) {
        map.set(card.category, []);
      }
      map.get(card.category)!.push(card);
    }
    return Array.from(map.entries()).map(([category, cards]) => ({ category, cards }));
  });

  async ngOnInit(): Promise<void> {
    this.loading.set(true);
    try {
      const summary = await this.api.getDashboardSummary();
      this.cards.set(summary.cards);
      this.period.set(summary.period);
    } finally {
      this.loading.set(false);
    }
  }

  cardKey(card: DashboardCard): string {
    return `${card.category}:${card.metric_type}`;
  }

  async toggleCard(card: DashboardCard): Promise<void> {
    const key = this.cardKey(card);
    if (this.expandedKey() === key) {
      this.expandedKey.set(null);
      this.drilldown.set(null);
      return;
    }

    this.expandedKey.set(key);
    this.drilldown.set(null);
    this.drilldownLoading.set(true);
    try {
      this.drilldown.set(await this.api.getDashboardDrilldown(card.category, card.period, card.metric_type));
    } finally {
      this.drilldownLoading.set(false);
    }
  }

  formatMonth(period: string | null): string {
    if (!period) {
      return '';
    }
    const parsed = new Date(`${period}T00:00:00`);
    return parsed.toLocaleDateString('en-US', { month: 'long', year: 'numeric' });
  }
}
