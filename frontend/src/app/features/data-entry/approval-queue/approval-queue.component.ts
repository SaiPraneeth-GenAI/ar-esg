import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { TimeoutError } from 'rxjs';
import { EntriesApiService, EntryRecord } from '../../../core/entries-api.service';
import { ToastService } from '../../../core/toast.service';
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
  private toast = inject(ToastService);

  loading = signal(true);
  queue = signal<EntryRecord[]>([]);
  errorMessage = signal('');
  successMessage = signal('');
  busyId = signal<string | null>(null);
  rejectingId = signal<string | null>(null);
  rejectNote = '';
  historyOpenId = signal<string | null>(null);

  selectedIds = signal<Set<string>>(new Set());
  bulkBusy = signal(false);
  bulkRejecting = signal(false);
  bulkRejectNote = '';

  selectedCount = computed(() => this.selectedIds().size);
  allSelected = computed(() => this.queue().length > 0 && this.selectedIds().size === this.queue().length);

  async ngOnInit(): Promise<void> {
    await this.refresh();
  }

  async refresh(): Promise<void> {
    this.loading.set(true);
    this.errorMessage.set('');
    try {
      this.queue.set(await this.api.getQueue());
      this.selectedIds.set(new Set());
    } catch {
      this.errorMessage.set('Could not load the approval queue.');
    } finally {
      this.loading.set(false);
    }
  }

  isSelected(entry: EntryRecord): boolean {
    return this.selectedIds().has(entry.id);
  }

  toggleSelect(entry: EntryRecord): void {
    const next = new Set(this.selectedIds());
    if (next.has(entry.id)) {
      next.delete(entry.id);
    } else {
      next.add(entry.id);
    }
    this.selectedIds.set(next);
  }

  toggleSelectAll(): void {
    this.selectedIds.set(this.allSelected() ? new Set() : new Set(this.queue().map((e) => e.id)));
  }

  clearSelection(): void {
    this.selectedIds.set(new Set());
  }

  async bulkApprove(): Promise<void> {
    const ids = Array.from(this.selectedIds());
    if (ids.length === 0) return;
    this.bulkBusy.set(true);
    this.errorMessage.set('');
    this.successMessage.set('');
    try {
      const result = await this.api.bulkApprove(ids);
      const message = this.summarize(result.processed_count, 'approved', result.skipped.length);
      this.successMessage.set(message);
      this.toast.show(message, 'success');
      await this.refresh();
    } catch (err) {
      const message = this.extractError(err);
      this.errorMessage.set(message);
      this.toast.show(message, 'error');
    } finally {
      this.bulkBusy.set(false);
    }
  }

  startBulkReject(): void {
    this.bulkRejecting.set(true);
    this.bulkRejectNote = '';
  }

  cancelBulkReject(): void {
    this.bulkRejecting.set(false);
    this.bulkRejectNote = '';
  }

  async confirmBulkReject(): Promise<void> {
    const ids = Array.from(this.selectedIds());
    if (ids.length === 0) return;
    if (!this.bulkRejectNote.trim()) {
      this.errorMessage.set('A rejection note is required.');
      return;
    }
    this.bulkBusy.set(true);
    this.errorMessage.set('');
    this.successMessage.set('');
    try {
      const result = await this.api.bulkReject(ids, this.bulkRejectNote.trim());
      const message = this.summarize(result.processed_count, 'rejected', result.skipped.length);
      this.successMessage.set(message);
      this.toast.show(message, 'success');
      this.bulkRejecting.set(false);
      await this.refresh();
    } catch (err) {
      const message = this.extractError(err);
      this.errorMessage.set(message);
      this.toast.show(message, 'error');
    } finally {
      this.bulkBusy.set(false);
    }
  }

  private summarize(processed: number, verb: string, skipped: number): string {
    const base = `${processed} entr${processed === 1 ? 'y' : 'ies'} ${verb}.`;
    return skipped > 0 ? `${base} ${skipped} skipped (already decided or not yours to decide).` : base;
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
    if (err instanceof TimeoutError) {
      return 'This is taking longer than expected. Some of these may already be decided -- refresh the queue before retrying.';
    }
    return (err as { error?: { detail?: string } })?.error?.detail ?? 'Something went wrong.';
  }
}
