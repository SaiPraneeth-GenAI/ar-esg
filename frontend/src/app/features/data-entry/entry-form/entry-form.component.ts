import { Component, EventEmitter, Input, OnChanges, Output, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import {
  AttachmentRecord,
  DataPoint,
  EntriesApiService,
  EntryCategory,
  EntryRecord,
  LastValue
} from '../../../core/entries-api.service';
import { EntryHistoryComponent } from '../entry-history/entry-history.component';

interface FieldState {
  dataPoint: DataPoint;
  value: number | null;
  note: string;
  entry: EntryRecord | null;
  lastValue: LastValue | null;
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
  imports: [FormsModule, EntryHistoryComponent],
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
  mode = signal<'guided' | 'classic'>('guided');
  fields = signal<FieldState[]>([]);
  stepIndex = signal(0);
  reviewing = signal(false);

  get periodIso(): string {
    return `${this.monthValue()}-01`;
  }

  async ngOnChanges(): Promise<void> {
    this.mode.set(this.category.data_points[0]?.default_mode ?? 'guided');
    this.stepIndex.set(0);
    this.reviewing.set(false);
    await this.load();
  }

  async onMonthChange(): Promise<void> {
    this.stepIndex.set(0);
    this.reviewing.set(false);
    await this.load();
  }

  private async load(): Promise<void> {
    this.loading.set(true);
    this.errorMessage.set('');
    try {
      const current = await this.api.getCurrentEntries(this.category.name, this.periodIso, this.locationId);
      const byDataPoint = new Map(current.map((e) => [e.data_point_id, e]));

      const fields: FieldState[] = [];
      for (const dp of this.category.data_points) {
        const entry = byDataPoint.get(dp.id) ?? null;
        const lastValue = await this.api.getLastValue(dp.id, this.locationId, this.periodIso);
        fields.push({
          dataPoint: dp,
          value: entry?.value ?? null,
          note: entry?.note ?? '',
          entry,
          lastValue,
          attachments: [],
          historyOpen: false,
          saving: false
        });
      }
      this.fields.set(fields);
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

  async saveField(index: number): Promise<void> {
    const field = this.fields()[index];
    if (this.isLocked(field)) {
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
      this.updateField(index, { entry: record, saving: false });
    } catch {
      this.updateField(index, { saving: false });
      this.errorMessage.set(`Could not save ${field.dataPoint.name}.`);
    }
  }

  async next(): Promise<void> {
    await this.saveField(this.stepIndex());
    if (this.stepIndex() < this.fields().length - 1) {
      this.stepIndex.update((i) => i + 1);
    } else {
      this.reviewing.set(true);
    }
  }

  prev(): void {
    if (this.reviewing()) {
      this.reviewing.set(false);
      return;
    }
    this.stepIndex.update((i) => Math.max(0, i - 1));
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
      this.reviewing.set(false);
      this.stepIndex.set(0);
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
    if (!field.entry) {
      this.errorMessage.set('Save this field before attaching a file.');
      return;
    }
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) {
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
}
