import { Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { CategoryIconComponent } from './category-icon.component';
import { CATEGORY_GROUPS, CONNECTORS, CategoryGroup, Connector, FILTER_PILLS } from './connectors.data';

interface CategorySection {
  group: CategoryGroup;
  connectors: Connector[];
}

@Component({
  selector: 'app-data-connections',
  standalone: true,
  imports: [FormsModule, CategoryIconComponent],
  templateUrl: './data-connections.component.html',
  styleUrl: './data-connections.component.css'
})
export class DataConnectionsComponent {
  private router = inject(Router);

  search = signal('');
  activeFilter = signal(0); // index into FILTER_PILLS
  pills = FILTER_PILLS;

  featured = CONNECTORS.filter((c) => c.featured);

  private matchesSearch(c: Connector, term: string): boolean {
    if (!term) return true;
    const t = term.toLowerCase();
    return (
      c.name.toLowerCase().includes(t) ||
      c.description.toLowerCase().includes(t) ||
      c.badges.some((b) => b.toLowerCase().includes(t))
    );
  }

  private matchesFilter(c: Connector): boolean {
    const pill = this.pills[this.activeFilter()];
    if (pill.groups === 'all') return true;
    return pill.groups.includes(c.categoryGroup);
  }

  sections = computed<CategorySection[]>(() => {
    const term = this.search().trim();
    return CATEGORY_GROUPS.map((group) => ({
      group,
      connectors: CONNECTORS.filter((c) => c.categoryGroup === group.id && this.matchesFilter(c) && this.matchesSearch(c, term))
    })).filter((section) => section.connectors.length > 0);
  });

  hasAnyResults = computed(() => this.sections().length > 0);

  requestSent = signal(false);

  setFilter(index: number): void {
    this.activeFilter.set(index);
  }

  openConnector(id: string): void {
    this.router.navigate(['/admin/settings/data-connections', id]);
  }

  requestCustomConnector(): void {
    this.requestSent.set(true);
  }
}
