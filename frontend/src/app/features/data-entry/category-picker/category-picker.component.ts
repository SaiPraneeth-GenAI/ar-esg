import { Component, EventEmitter, Input, Output } from '@angular/core';
import { EntryCategory } from '../../../core/entries-api.service';

@Component({
  selector: 'app-category-picker',
  standalone: true,
  templateUrl: './category-picker.component.html',
  styleUrl: './category-picker.component.css'
})
export class CategoryPickerComponent {
  @Input({ required: true }) categories: EntryCategory[] = [];
  @Output() pick = new EventEmitter<EntryCategory>();
}
