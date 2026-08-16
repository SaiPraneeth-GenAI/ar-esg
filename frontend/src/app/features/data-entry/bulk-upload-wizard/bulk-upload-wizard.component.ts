import { DatePipe } from '@angular/common';
import { Component, EventEmitter, Input, Output, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { BulkImportRowIn, EntriesApiService, EntryCategory } from '../../../core/entries-api.service';
import {
  TARGET_FIELDS,
  TargetField,
  formatPeriodLabel,
  guessMapping,
  parsePeriodToIso,
  parseSpreadsheet
} from './bulk-upload-wizard.utils';

type Step = 'upload' | 'preview' | 'mapping' | 'validate' | 'confirm';
type RowStatus = 'valid' | 'error' | 'created' | 'unchecked';

interface MappingChoice {
  headerIndex: number;
  header: string;
  target: string | null;
}

interface EditableRow {
  row_index: number;
  data_point_name: string;
  period_iso: string; // "" means "use the wizard's selected period"
  value_raw: string;
  unit_raw: string | null;
  note: string | null;
  included: boolean;
  status: RowStatus;
  message: string | null;
  entry_id: string | null;
  unitNote: string | null;
  suggestedUnit: string | null;
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
  imports: [FormsModule, DatePipe],
  templateUrl: './bulk-upload-wizard.component.html',
  styleUrl: './bulk-upload-wizard.component.css'
})
export class BulkUploadWizardComponent {
  private api = inject(EntriesApiService);

  @Input({ required: true }) category!: EntryCategory;
  @Input({ required: true }) locationId!: string;
  /** ISO "YYYY-MM-01" -- the period already selected at the top of the Data
   * Entry screen. Used for any row that doesn't specify its own period. */
  @Input({ required: true }) period!: string;
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
  rows = signal<EditableRow[]>([]);

  committing = signal(false);
  commitError = signal('');
  commitResult = signal<{ created: number; error: number } | null>(null);

  previewRows = computed(() => this.rawRows().slice(0, 8));

  mappingComplete = computed(() => {
    const mapped = new Set(this.mapping().map((m) => m.target).filter(Boolean));
    return this.targetFields.filter((f) => f.required).every((f) => mapped.has(f.key));
  });

  includedValidRows = computed(() => this.rows().filter((r) => r.included && r.status !== 'error'));
  errorRows = computed(() => this.rows().filter((r) => r.status === 'error'));
  hasUnchecked = computed(() => this.rows().some((r) => r.status === 'unchecked'));

  summaryLabel = computed(() => {
    const rows = this.includedValidRows();
    if (rows.length === 0) {
      return '';
    }
    const periods = rows.map((r) => r.period_iso || this.period).filter(Boolean);
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
    this.rowsBuiltForMapping = null;
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

  private buildRowsFromFile(): EditableRow[] {
    const mapping = this.mapping();
    const indexOf = (key: string) => mapping.find((m) => m.target === key)?.headerIndex;
    const nameIdx = indexOf('data_point_name');
    const periodIdx = indexOf('period');
    const valueIdx = indexOf('value');
    const unitIdx = indexOf('unit');
    const noteIdx = indexOf('note');

    if (nameIdx === undefined || valueIdx === undefined) {
      return [];
    }

    return this.rawRows().map((row, i) => {
      const periodRaw = periodIdx !== undefined ? row[periodIdx] : null;
      // A blank cell or one we can't parse just falls back to the period
      // already selected above -- we never leave this looking "empty" in the
      // Validate table, and we never make that a hard error.
      const periodIso = (periodRaw ? parsePeriodToIso(periodRaw) : null) ?? this.period;
      return {
        row_index: i + 2, // +1 for header row, +1 for 1-indexing
        data_point_name: String(row[nameIdx] ?? '').trim(),
        period_iso: periodIso,
        value_raw: String(row[valueIdx] ?? '').trim(),
        unit_raw: unitIdx !== undefined ? String(row[unitIdx] ?? '').trim() || null : null,
        note: noteIdx !== undefined ? String(row[noteIdx] ?? '').trim() || null : null,
        included: true,
        status: 'unchecked' as RowStatus,
        message: null,
        entry_id: null,
        unitNote: null,
        suggestedUnit: null
      };
    });
  }

  private rowsBuiltForMapping: string | null = null;

  async runValidation(): Promise<void> {
    const mappingKey = JSON.stringify(this.mapping().map((m) => m.target));
    if (this.rows().length === 0 || mappingKey !== this.rowsBuiltForMapping) {
      this.rows.set(this.buildRowsFromFile());
      this.rowsBuiltForMapping = mappingKey;
    }
    this.step.set('validate');
    await this.recheck();
  }

  updateRow(rowIndex: number, patch: Partial<EditableRow>): void {
    const list = this.rows().map((r) =>
      r.row_index === rowIndex
        ? { ...r, ...patch, status: 'unchecked' as RowStatus, message: null, unitNote: null, suggestedUnit: null }
        : r
    );
    this.rows.set(list);
  }

  toggleIncluded(rowIndex: number): void {
    const list = this.rows().map((r) => (r.row_index === rowIndex ? { ...r, included: !r.included } : r));
    this.rows.set(list);
  }

  removeRow(rowIndex: number): void {
    this.rows.set(this.rows().filter((r) => r.row_index !== rowIndex));
  }

  private toPayloadRows(source: EditableRow[]): BulkImportRowIn[] {
    return source.map((r) => ({
      row_index: r.row_index,
      data_point_name: r.data_point_name,
      period_iso: r.period_iso,
      value_raw: r.value_raw,
      unit_raw: r.unit_raw,
      note: r.note
    }));
  }

  async recheck(): Promise<void> {
    const current = this.rows();
    if (current.length === 0) {
      return;
    }
    this.validating.set(true);
    try {
      const result = await this.api.bulkImport(this.category.name, this.locationId, this.toPayloadRows(current), false, this.period);
      const byIndex = new Map(result.rows.map((r) => [r.row_index, r]));
      const merged = current.map((row) => {
        const r = byIndex.get(row.row_index);
        return {
          ...row,
          status: (r?.status as RowStatus) ?? 'error',
          message: r?.message ?? null,
          included: r ? r.status !== 'error' : false,
          unitNote: r?.unit_note ?? null,
          suggestedUnit: r?.suggested_unit ?? null
        };
      });
      this.rows.set(merged);
    } finally {
      this.validating.set(false);
    }
  }

  /** One-click fix for a unit error: swaps in the exact unit the data
   * point expects and re-marks the row for re-validation. */
  applySuggestedUnit(rowIndex: number): void {
    const row = this.rows().find((r) => r.row_index === rowIndex);
    if (!row?.suggestedUnit) return;
    this.updateRow(rowIndex, { unit_raw: row.suggestedUnit });
  }

  /** Hands back a real .xlsx with every row's outcome -- status, message,
   * and (for unit errors) the exact expected unit -- so a user working in
   * Excel can fix problems there and re-upload, instead of only seeing
   * errors inside this wizard. */
  async downloadAnnotatedFile(): Promise<void> {
    const XLSX = await import('xlsx');
    const data = this.rows().map((r) => ({
      data_point_name: r.data_point_name,
      period: r.period_iso || this.period,
      value: r.value_raw,
      unit: r.unit_raw ?? '',
      note: r.note ?? '',
      status: r.status === 'error' ? 'Needs fix' : r.status === 'created' ? 'Created' : 'Ready to upload',
      message: r.message ?? (r.unitNote ?? ''),
      suggested_unit: r.suggestedUnit ?? ''
    }));
    const ws = XLSX.utils.json_to_sheet(data);
    ws['!cols'] = [{ wch: 28 }, { wch: 12 }, { wch: 12 }, { wch: 10 }, { wch: 20 }, { wch: 14 }, { wch: 40 }, { wch: 14 }];
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, 'Review');
    XLSX.writeFile(wb, `${this.category.name.replace(/\s+/g, '_')}_review.xlsx`);
  }

  goToConfirm(): void {
    this.step.set('confirm');
  }

  async commitImport(): Promise<void> {
    const toCommit = this.includedValidRows();
    this.committing.set(true);
    this.commitError.set('');
    try {
      const result = await this.api.bulkImport(this.category.name, this.locationId, this.toPayloadRows(toCommit), true, this.period);
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
    this.rows.set([]);
    this.rowsBuiltForMapping = null;
    this.commitResult.set(null);
    this.commitError.set('');
  }
}
