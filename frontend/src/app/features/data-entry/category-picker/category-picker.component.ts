import { Component, EventEmitter, Input, Output } from '@angular/core';
import { EntryCategory } from '../../../core/entries-api.service';

const ICON_BY_CATEGORY: Record<string, string> = {
  Water: 'droplet',
  'ETP-Water': 'droplet',
  'STP-Water': 'droplet',
  Waste: 'trash',
  Ozone: 'wind',
  'Effluent Monitoring': 'flask',
  'Air Emissions': 'cloud',
  'Business Performance': 'chart',
  Safety: 'shield',
  Production: 'battery',
  'Purchased Goods & Services': 'box',
  'Capital Goods': 'factory',
  'Fuel & Energy (Upstream)': 'bolt',
  'Upstream Transportation': 'truck',
  'Downstream Transportation': 'truck',
  'Operational Waste (Third-Party)': 'recycle',
  'End-of-Life of Sold Products': 'recycle',
  'Business Travel': 'plane',
  'Employee Commuting': 'users'
};

interface PickerSection {
  id: string;
  title: string;
  subtitle: string;
  categories: EntryCategory[];
}

@Component({
  selector: 'app-category-picker',
  standalone: true,
  templateUrl: './category-picker.component.html',
  styleUrl: './category-picker.component.css'
})
export class CategoryPickerComponent {
  @Input({ required: true }) categories: EntryCategory[] = [];
  @Output() pick = new EventEmitter<EntryCategory>();

  iconFor(categoryName: string): string {
    return ICON_BY_CATEGORY[categoryName] ?? 'file';
  }

  /** Operations data first, then the Scope 3 value chain -- grouped by the
   * scope the backend reports each category feeds, not by a name list. */
  sections(): PickerSection[] {
    const operations = this.categories.filter((c) => c.ghg_scope !== 3);
    const valueChain = this.categories
      .filter((c) => c.ghg_scope === 3)
      .sort((a, b) => this.scope3Number(a) - this.scope3Number(b));
    const sections: PickerSection[] = [];
    if (operations.length) {
      sections.push({
        id: 'operations',
        title: 'Operations',
        subtitle: 'Site readings — energy, fuels, water, waste, safety and production (Scope 1 & 2 sources)',
        categories: operations
      });
    }
    if (valueChain.length) {
      sections.push({
        id: 'scope3',
        title: 'Value chain · Scope 3',
        subtitle: 'GHG Protocol categories — purchased materials, logistics, travel, commuting and end-of-life',
        categories: valueChain
      });
    }
    return sections;
  }

  /** "Cat 4 · Upstream transportation" -> "Cat 4". */
  scope3Badge(category: EntryCategory): string | null {
    return category.scope3_category ? category.scope3_category.split('·')[0].trim() : null;
  }

  private scope3Number(category: EntryCategory): number {
    const match = /Cat\s+(\d+)/.exec(category.scope3_category ?? '');
    return match ? Number(match[1]) : 99;
  }
}
