import { Component, Input } from '@angular/core';
import { CategoryGroupId } from './connectors.data';

/** One icon per category group, reused across every connector tile in
 * that group -- gives each section its own visual language (spec: "ERP
 * tiles use enterprise visual language, IoT tiles use industrial
 * telemetry language...") without needing 49 distinct connector logos,
 * which would also risk misrepresenting third-party brand marks. */
@Component({
  selector: 'app-category-icon',
  standalone: true,
  template: `
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
      @switch (group) {
        @case ('erp') {
          <path d="M4 21V7l8-4 8 4v14" />
          <path d="M9 21v-6h6v6" />
          <path d="M9 11h.01M15 11h.01M9 15h.01M15 15h.01" />
        }
        @case ('api') {
          <path d="M9 3v4M15 3v4M9 17v4M15 17v4" />
          <rect x="6" y="7" width="12" height="10" rx="2" />
          <path d="M9 12h6" />
        }
        @case ('iot') {
          <circle cx="12" cy="12" r="2" />
          <path d="M8.5 8.5a5 5 0 0 1 7 0M5.5 5.5a9 9 0 0 1 13 0" />
          <path d="M8.5 15.5a5 5 0 0 0 7 0M5.5 18.5a9 9 0 0 0 13 0" />
        }
        @case ('database') {
          <ellipse cx="12" cy="5.5" rx="7" ry="2.8" />
          <path d="M5 5.5v6.2c0 1.5 3.1 2.8 7 2.8s7-1.3 7-2.8V5.5" />
          <path d="M5 11.7v6.2c0 1.5 3.1 2.8 7 2.8s7-1.3 7-2.8v-6.2" />
        }
        @case ('files') {
          <path d="M4 7a2 2 0 0 1 2-2h4l2 2h6a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2Z" />
        }
        @case ('documents') {
          <path d="M7 3h7l4 4v14a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1Z" />
          <path d="M14 3v4h4" />
          <path d="M8.5 13h7M8.5 16.5h5" />
        }
        @case ('utilities') {
          <path d="M13 2 4 14h6l-1 8 9-12h-6l1-8Z" />
        }
        @case ('hr') {
          <circle cx="9" cy="8" r="3" />
          <path d="M3 20c0-3.3 2.7-6 6-6s6 2.7 6 6" />
          <circle cx="17" cy="8" r="2.4" />
          <path d="M15.5 14.2A5.5 5.5 0 0 1 21 20" />
        }
        @case ('supply-chain') {
          <rect x="2" y="9" width="12" height="9" rx="1.2" />
          <path d="M14 12h4l4 3.5V18h-8" />
          <circle cx="6.5" cy="19" r="1.6" />
          <circle cx="17" cy="19" r="1.6" />
        }
        @case ('esg') {
          <circle cx="12" cy="12" r="9" />
          <path d="M3 12h18M12 3c2.5 2.5 3.8 5.7 3.8 9s-1.3 6.5-3.8 9c-2.5-2.5-3.8-5.7-3.8-9S9.5 5.5 12 3Z" />
        }
      }
    </svg>
  `
})
export class CategoryIconComponent {
  @Input({ required: true }) group!: CategoryGroupId;
}
