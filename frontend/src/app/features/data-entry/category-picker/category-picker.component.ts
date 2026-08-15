import { Component, EventEmitter, Input, Output } from '@angular/core';
import { EntryCategory } from '../../../core/entries-api.service';

const ICON_BY_CATEGORY: Record<string, string> = {
  Water: 'droplet',
  'ETP-Water': 'droplet',
  'STP-Water': 'droplet',
  Waste: 'trash',
  Ozone: 'wind',
  'Effluent Monitoring': 'flask',
  'Air Emissions': 'cloud'
};

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
}
