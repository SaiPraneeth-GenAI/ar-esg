import { Component, EventEmitter, Input, OnChanges, Output, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import {
  AttachmentRecord,
  DataPoint,
  EntriesApiService,
  EntryCategory,
  EntryRecord,
  LastValueEntry
} from '../../../core/entries-api.service';
import { BulkUploadWizardComponent } from '../bulk-upload-wizard/bulk-upload-wizard.component';
import { EntryHistoryComponent } from '../entry-history/entry-history.component';

interface FieldState {
  dataPoint: DataPoint;
  value: number | null;
  note: string;
  entry: EntryRecord | null;
  lastValue: LastValueEntry | null;
  attachments: AttachmentRecord[];
  historyOpen: boolean;
  saving: boolean;
  autosaved: boolean;
  lastSavedValue: number | null;
  lastSavedNote: string;
}

function currentMonthValue(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
}

@Component({
  selector: 'app-entry-form',
  standalone: true,
  imports: [FormsModule, EntryHistoryComponent, BulkUploadWizardComponent],
  templateUrl: './entry-form.component.html',
  styleUrl: './entry-form.component.css'
})
export class EntryFormComponent implements OnChanges {
  private api = inject(EntriesApiService);

  @Input({ required: true }) category!: EntryCategory;
  @Input({ required: true }) locationId!: string;
  @Input() initialPeriod: string | null = null;
  @Output() back = new EventEmitter<void>();

  loading = signal(true);
  submitting = signal(false);
  message = signal('');
  errorMessage = signal('');

  monthValue = signal(currentMonthValue());
  mode = signal<'entry' | 'bulk'>('entry');
  fields = signal<FieldState[]>([]);

  get periodIso(): string {
    return `${this.monthValue()}-01`;
  }

  async ngOnChanges(): Promise<void> {
    this.mode.set('entry');
    if (this.initialPeriod) {
      this.monthValue.set(this.initialPeriod.slice(0, 7));
    }
    await this.load();
  }

  async onMonthChange(): Promise<void> {
    await this.load();
  }

  private async load(): Promise<void> {
    this.loading.set(true);
    this.errorMessage.set('');
    try {
      const [current, lastValues] = await Promise.all([
        this.api.getCurrentEntries(this.category.name, this.periodIso, this.locationId),
        this.api.getLastValuesBatch(this.category.name, this.locationId, this.periodIso)
      ]);
      const byDataPoint = new Map(current.map((e) => [e.data_point_id, e]));
      const lastValueByDataPoint = new Map(lastValues.map((v) => [v.data_point_id, v]));

      this.fields.set(
        this.category.data_points.map((dp) => {
          const entry = byDataPoint.get(dp.id) ?? null;
          const value = entry?.value ?? null;
          const note = entry?.note ?? '';
          return {
            dataPoint: dp,
            value,
            note,
            entry,
            lastValue: lastValueByDataPoint.get(dp.id) ?? null,
            attachments: [],
            historyOpen: false,
            saving: false,
            autosaved: false,
            lastSavedValue: value,
            lastSavedNote: note
          };
        })
      );
    } catch {
      this.errorMessage.set('Could not load this category.');
    } finally {
      this.loading.set(false);
    }
  }

  /** Only "Submitted" (awaiting a decision) is locked -- editing an
   * Approved value is allowed, but see onFieldBlur/flushPendingEdits:
   * the backend sends it back to Draft when that happens, so a
   * correction always needs a fresh Submit -> Approve before it can
   * affect any calculated figure. */
  isLocked(field: FieldState): boolean {
    return field.entry?.status === 'Submitted';
  }

  /** True once an edit to a currently-Approved value has actually been
   * typed -- used to warn before the field reverts to Draft on save. */
  editingApproved(field: FieldState): boolean {
    return field.entry?.status === 'Approved';
  }

  updateField(index: number, patch: Partial<FieldState>): void {
    const list = [...this.fields()];
    list[index] = { ...list[index], ...patch };
    this.fields.set(list);
  }

  /** Saves a single field as a Draft on blur -- no aggressive polling, just
   * when the user finishes with a field and moves on. Reopening this
   * category/period later reloads from whatever was last autosaved. */
  async onFieldBlur(index: number): Promise<void> {
    const field = this.fields()[index];
    if (this.isLocked(field)) {
      return;
    }
    if (field.value === field.lastSavedValue && field.note === field.lastSavedNote) {
      return;
    }
    if (field.value === null) {
      return;
    }

    this.updateField(index, { saving: true });
    try {
      const [record] = await this.api.saveDrafts([
        {
          data_point_id: field.dataPoint.id,
          location_id: this.locationId,
          period: this.periodIso,
          value: field.value,
          note: field.note || null
        }
      ]);
      this.updateField(index, {
        entry: record,
        saving: false,
        autosaved: true,
        lastSavedValue: field.value,
        lastSavedNote: field.note
      });
      setTimeout(() => this.updateField(index, { autosaved: false }), 2000);
    } catch {
      this.updateField(index, { saving: false });
      this.errorMessage.set(`Could not save ${field.dataPoint.name} -- your change wasn't saved, please try again.`);
    }
  }

  /** Saves every field that's been edited but not yet persisted. Used both
   * by the explicit "Save draft" button and as the first step of Submit, so
   * Submit always works in one click even if autosave hasn't caught up
   * with the latest keystroke yet. */
  private async flushPendingEdits(): Promise<boolean> {
    const pending = this.fields()
      .map((f, i) => ({ f, i }))
      .filter(({ f }) => !this.isLocked(f) && f.value !== null && (f.value !== f.lastSavedValue || f.note !== f.lastSavedNote));

    if (pending.length === 0) {
      return true;
    }

    try {
      const records = await this.api.saveDrafts(
        pending.map(({ f }) => ({
          data_point_id: f.dataPoint.id,
          location_id: this.locationId,
          period: this.periodIso,
          value: f.value,
          note: f.note || null
        }))
      );
      const list = [...this.fields()];
      pending.forEach(({ i }, recordIndex) => {
        list[i] = { ...list[i], entry: records[recordIndex], lastSavedValue: list[i].value, lastSavedNote: list[i].note };
      });
      this.fields.set(list);
      return true;
    } catch {
      this.errorMessage.set('Could not save your changes.');
      return false;
    }
  }

  async saveAllClassic(): Promise<void> {
    this.submitting.set(true);
    this.errorMessage.set('');
    const ok = await this.flushPendingEdits();
    if (ok) {
      this.message.set('Draft saved.');
    }
    this.submitting.set(false);
  }

  /** Enabled the moment there's anything to submit -- either already saved
   * as a Draft, or edited-but-not-yet-saved (Submit will save it first). */
  hasAnyDraft(): boolean {
    return this.fields().some(
      (f) => f.entry?.status === 'Draft' || (!this.isLocked(f) && f.value !== null && (f.value !== f.lastSavedValue || f.note !== f.lastSavedNote))
    );
  }

  async submitForApproval(): Promise<void> {
    this.submitting.set(true);
    this.errorMessage.set('');
    const saved = await this.flushPendingEdits();
    if (!saved) {
      this.submitting.set(false);
      return;
    }
    try {
      await this.api.submit(this.category.name, this.periodIso, this.locationId);
      this.message.set('Submitted for approval.');
      await this.load();
    } catch {
      this.errorMessage.set('Could not submit for approval.');
    } finally {
      this.submitting.set(false);
    }
  }

  toggleHistory(index: number): void {
    const field = this.fields()[index];
    this.updateField(index, { historyOpen: !field.historyOpen });
  }

  async onFileSelected(index: number, event: Event): Promise<void> {
    const field = this.fields()[index];
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file || !field.entry) {
      return;
    }
    try {
      const attachment = await this.api.uploadAttachment(field.entry.id, file);
      this.updateField(index, { attachments: [...field.attachments, attachment] });
    } catch {
      this.errorMessage.set('Could not upload attachment.');
    } finally {
      input.value = '';
    }
  }

  statusLabel(field: FieldState): string {
    return field.entry?.status ?? 'Not started';
  }

  onBulkUploadDone(): void {
    this.mode.set('entry');
    void this.load();
  }
}
