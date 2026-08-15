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
          return {
            dataPoint: dp,
            value: entry?.value ?? null,
            note: entry?.note ?? '',
            entry,
            lastValue: lastValueByDataPoint.get(dp.id) ?? null,
            attachments: [],
            historyOpen: false,
            saving: false
          };
        })
      );
    } catch {
      this.errorMessage.set('Could not load this category.');
    } finally {
      this.loading.set(false);
    }
  }

  isLocked(field: FieldState): boolean {
    return field.entry?.status === 'Submitted' || field.entry?.status === 'Approved';
  }

  updateField(index: number, patch: Partial<FieldState>): void {
    const list = [...this.fields()];
    list[index] = { ...list[index], ...patch };
    this.fields.set(list);
  }

  async saveAllClassic(): Promise<void> {
    const editable = this.fields()
      .map((f, i) => ({ f, i }))
      .filter(({ f }) => !this.isLocked(f) && f.value !== null);

    if (editable.length === 0) {
      return;
    }

    this.submitting.set(true);
    this.errorMessage.set('');
    try {
      const records = await this.api.saveDrafts(
        editable.map(({ f }) => ({
          data_point_id: f.dataPoint.id,
          location_id: this.locationId,
          period: this.periodIso,
          value: f.value,
          note: f.note || null
        }))
      );
      const list = [...this.fields()];
      editable.forEach(({ i }, recordIndex) => {
        list[i] = { ...list[i], entry: records[recordIndex] };
      });
      this.fields.set(list);
      this.message.set('Draft saved.');
    } catch {
      this.errorMessage.set('Could not save this form.');
    } finally {
      this.submitting.set(false);
    }
  }

  hasAnyDraft(): boolean {
    return this.fields().some((f) => f.entry?.status === 'Draft');
  }

  async submitForApproval(): Promise<void> {
    this.submitting.set(true);
    this.errorMessage.set('');
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
