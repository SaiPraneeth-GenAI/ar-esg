import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { EntriesApiService, EntryRecord } from '../../../core/entries-api.service';
import { EntryHistoryComponent } from '../entry-history/entry-history.component';

@Component({
  selector: 'app-approval-queue',
  standalone: true,
  imports: [FormsModule, EntryHistoryComponent],
  templateUrl: './approval-queue.component.html',
  styleUrl: './approval-queue.component.css'
})
export class ApprovalQueueComponent implements OnInit {
  private api = inject(EntriesApiService);

  loading = signal(true);
  queue = signal<EntryRecord[]>([]);
  errorMessage = signal('');
  successMessage = signal('');
  busyId = signal<string | null>(null);
  rejectingId = signal<string | null>(null);
  rejectNote = '';
  historyOpenId = signal<string | null>(null);

  async ngOnInit(): Promise<void> {
    await this.refresh();
  }

  async refresh(): Promise<void> {
    this.loading.set(true);
    this.errorMessage.set('');
    try {
      this.queue.set(await this.api.getQueue());
    } catch {
      this.errorMessage.set('Could not load the approval queue.');
    } finally {
      this.loading.set(false);
    }
  }

  async approve(entry: EntryRecord): Promise<void> {
    this.busyId.set(entry.id);
    this.errorMessage.set('');
    this.successMessage.set('');
    try {
      await this.api.approve(entry.id);
      this.successMessage.set(`${entry.data_point_name} approved.`);
      await this.refresh();
    } catch (err) {
      this.errorMessage.set(this.extractError(err));
    } finally {
      this.busyId.set(null);
    }
  }

  startReject(entry: EntryRecord): void {
    this.rejectingId.set(entry.id);
    this.rejectNote = '';
  }

  cancelReject(): void {
    this.rejectingId.set(null);
    this.rejectNote = '';
  }

  async confirmReject(entry: EntryRecord): Promise<void> {
    if (!this.rejectNote.trim()) {
      this.errorMessage.set('A rejection note is required.');
      return;
    }
    this.busyId.set(entry.id);
    this.errorMessage.set('');
    this.successMessage.set('');
    try {
      await this.api.reject(entry.id, this.rejectNote.trim());
      this.successMessage.set(`${entry.data_point_name} rejected.`);
      this.rejectingId.set(null);
      await this.refresh();
    } catch (err) {
      this.errorMessage.set(this.extractError(err));
    } finally {
      this.busyId.set(null);
    }
  }

  toggleHistory(entry: EntryRecord): void {
    this.historyOpenId.set(this.historyOpenId() === entry.id ? null : entry.id);
  }

  private extractError(err: unknown): string {
    return (err as { error?: { detail?: string } })?.error?.detail ?? 'Something went wrong.';
  }
}
