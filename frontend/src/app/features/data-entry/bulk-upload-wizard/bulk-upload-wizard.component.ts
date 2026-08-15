import { Component, EventEmitter, Input, Output, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { BulkImportRowIn, BulkImportRowResult, EntriesApiService, EntryCategory } from '../../../core/entries-api.service';
import {
  TARGET_FIELDS,
  TargetField,
  formatPeriodLabel,
  guessMapping,
  parsePeriodToIso,
  parseSpreadsheet
} from './bulk-upload-wizard.utils';

type Step = 'upload' | 'preview' | 'mapping' | 'validate' | 'confirm';

interface MappingChoice {
  headerIndex: number;
  header: string;
  target: string | null;
}

interface ValidationRow extends BulkImportRowResult {
  included: boolean;
}

function cellDisplay(value: unknown): string {
  if (value instanceof Date) {
    return value.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' });
  }
  return String(value ?? '');
}

@Component({
  selector: 'app-bulk-upload-wizard',
  standalone: true,
  imports: [FormsModule],
  templateUrl: './bulk-upload-wizard.component.html',
  styleUrl: './bulk-upload-wizard.component.css'
})
export class BulkUploadWizardComponent {
  private api = inject(EntriesApiService);

  @Input({ required: true }) category!: EntryCategory;
  @Input({ required: true }) locationId!: string;
  @Output() done = new EventEmitter<void>();

  targetFields: TargetField[] = TARGET_FIELDS;

  step = signal<Step>('upload');
  dragActive = signal(false);
  fileName = signal('');
  parseError = signal('');

  headers = signal<string[]>([]);
  rawRows = signal<unknown[][]>([]);
  mapping = signal<MappingChoice[]>([]);

  validating = signal(false);
  validationRows = signal<ValidationRow[]>([]);

  committing = signal(false);
  commitError = signal('');
  commitResult = signal<{ created: number; error: number } | null>(null);

  previewRows = computed(() => this.rawRows().slice(0, 8));

  mappingComplete = computed(() => {
    const mapped = new Set(this.mapping().map((m) => m.target).filter(Boolean));
    return this.targetFields.filter((f) => f.required).every((f) => mapped.has(f.key));
  });

  includedValidRows = computed(() => this.validationRows().filter((r) => r.included && r.status !== 'error'));
  errorRows = computed(() => this.validationRows().filter((r) => r.status === 'error'));

  summaryLabel = computed(() => {
    const rows = this.includedValidRows();
    if (rows.length === 0) {
      return '';
    }
    const periods = rows.map((r) => r.period).filter(Boolean) as string[];
    if (periods.length === 0) {
      return `${rows.length} entr${rows.length === 1 ? 'y' : 'ies'} will be created`;
    }
    const sorted = [...periods].sort();
    const first = formatPeriodLabel(sorted[0]);
    const last = formatPeriodLabel(sorted[sorted.length - 1]);
    const range = first === last ? first : `${first} – ${last}`;
    return `${rows.length} entr${rows.length === 1 ? 'y' : 'ies'} will be created across ${range}`;
  });

  cellDisplay = cellDisplay;

  onDragOver(event: DragEvent): void {
    event.preventDefault();
    this.dragActive.set(true);
  }

  onDragLeave(): void {
    this.dragActive.set(false);
  }

  onDrop(event: DragEvent): void {
    event.preventDefault();
    this.dragActive.set(false);
    const file = event.dataTransfer?.files?.[0];
    if (file) {
      void this.loadFile(file);
    }
  }

  onFileInputChange(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    if (file) {
      void this.loadFile(file);
    }
    input.value = '';
  }

  private async loadFile(file: File): Promise<void> {
    this.parseError.set('');
    this.fileName.set(file.name);
    try {
      const { headers, rows } = await parseSpreadsheet(file);
      if (headers.length === 0 || rows.length === 0) {
        this.parseError.set('This file looks empty -- no rows to import.');
        return;
      }
      this.headers.set(headers);
      this.rawRows.set(rows);
      this.step.set('preview');
    } catch {
      this.parseError.set('Could not read this file. Make sure it is a .csv, .xlsx, or .xls file.');
    }
  }

  async downloadTemplate(): Promise<void> {
    await this.api.downloadCsvTemplate(this.category.name);
  }

  backToUpload(): void {
    this.step.set('upload');
    this.headers.set([]);
    this.rawRows.set([]);
    this.fileName.set('');
  }

  confirmPreview(): void {
    const guesses = guessMapping(this.headers());
    this.mapping.set(this.headers().map((header, i) => ({ headerIndex: i, header, target: guesses[i] })));
    this.step.set('mapping');
  }

  setMapping(headerIndex: number, target: string): void {
    const list = this.mapping().map((m) => (m.headerIndex === headerIndex ? { ...m, target: target || null } : m));
    this.mapping.set(list);
  }

  targetLabel(key: string | null): string {
    return this.targetFields.find((f) => f.key === key)?.label ?? 'Unmatched';
  }

  async runValidation(): Promise<void> {
    const mapping = this.mapping();
    const indexOf = (key: string) => mapping.find((m) => m.target === key)?.headerIndex;
    const nameIdx = indexOf('data_point_name');
    const periodIdx = indexOf('period');
    const valueIdx = indexOf('value');
    const unitIdx = indexOf('unit');
    const noteIdx = indexOf('note');

    if (nameIdx === undefined || periodIdx === undefined || valueIdx === undefined) {
      return;
    }

    const payloadRows: BulkImportRowIn[] = this.rawRows().map((row, i) => {
      const periodRaw = row[periodIdx];
      const periodIso = parsePeriodToIso(periodRaw) ?? String(periodRaw ?? '');
      return {
        row_index: i + 2, // +1 for header row, +1 for 1-indexing
        data_point_name: String(row[nameIdx] ?? '').trim(),
        period_iso: periodIso,
        value_raw: String(row[valueIdx] ?? '').trim(),
        unit_raw: unitIdx !== undefined ? String(row[unitIdx] ?? '').trim() || null : null,
        note: noteIdx !== undefined ? String(row[noteIdx] ?? '').trim() || null : null
      };
    });

    this.validating.set(true);
    this.step.set('validate');
    try {
      const result = await this.api.bulkImport(this.category.name, this.locationId, payloadRows, false);
      this.validationRows.set(result.rows.map((r) => ({ ...r, included: r.status !== 'error' })));
    } finally {
      this.validating.set(false);
    }
  }

  toggleIncluded(rowIndex: number): void {
    const list = this.validationRows().map((r) => (r.row_index === rowIndex ? { ...r, included: !r.included } : r));
    this.validationRows.set(list);
  }

  goToConfirm(): void {
    this.step.set('confirm');
  }

  async commitImport(): Promise<void> {
    const mapping = this.mapping();
    const indexOf = (key: string) => mapping.find((m) => m.target === key)?.headerIndex;
    const nameIdx = indexOf('data_point_name')!;
    const periodIdx = indexOf('period')!;
    const valueIdx = indexOf('value')!;
    const unitIdx = indexOf('unit');
    const noteIdx = indexOf('note');

    const includedRowIndexes = new Set(this.includedValidRows().map((r) => r.row_index));
    const payloadRows: BulkImportRowIn[] = this.rawRows()
      .map((row, i) => ({ row, rowIndex: i + 2 }))
      .filter(({ rowIndex }) => includedRowIndexes.has(rowIndex))
      .map(({ row, rowIndex }) => {
        const periodRaw = row[periodIdx];
        const periodIso = parsePeriodToIso(periodRaw) ?? String(periodRaw ?? '');
        return {
          row_index: rowIndex,
          data_point_name: String(row[nameIdx] ?? '').trim(),
          period_iso: periodIso,
          value_raw: String(row[valueIdx] ?? '').trim(),
          unit_raw: unitIdx !== undefined ? String(row[unitIdx] ?? '').trim() || null : null,
          note: noteIdx !== undefined ? String(row[noteIdx] ?? '').trim() || null : null
        };
      });

    this.committing.set(true);
    this.commitError.set('');
    try {
      const result = await this.api.bulkImport(this.category.name, this.locationId, payloadRows, true);
      this.commitResult.set({ created: result.created_count, error: result.error_count });
    } catch {
      this.commitError.set('Could not create these entries. Nothing was saved.');
    } finally {
      this.committing.set(false);
    }
  }

  finish(): void {
    this.done.emit();
  }

  startOver(): void {
    this.step.set('upload');
    this.headers.set([]);
    this.rawRows.set([]);
    this.fileName.set('');
    this.mapping.set([]);
    this.validationRows.set([]);
    this.commitResult.set(null);
    this.commitError.set('');
  }
}
