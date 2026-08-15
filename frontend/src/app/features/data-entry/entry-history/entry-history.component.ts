import { DatePipe } from '@angular/common';
import { Component, Input, OnChanges, inject, signal } from '@angular/core';
import { AuditEntry, EntriesApiService } from '../../../core/entries-api.service';

@Component({
  selector: 'app-entry-history',
  standalone: true,
  imports: [DatePipe],
  templateUrl: './entry-history.component.html',
  styleUrl: './entry-history.component.css'
})
export class EntryHistoryComponent implements OnChanges {
  private api = inject(EntriesApiService);

  @Input({ required: true }) entryId!: string;

  loading = signal(true);
  history = signal<AuditEntry[]>([]);

  async ngOnChanges(): Promise<void> {
    this.loading.set(true);
    try {
      this.history.set(await this.api.getHistory(this.entryId));
    } finally {
      this.loading.set(false);
    }
  }
}
