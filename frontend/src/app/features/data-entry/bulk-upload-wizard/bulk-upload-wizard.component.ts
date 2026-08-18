import { DatePipe } from '@angular/common';
import { Component, EventEmitter, Input, Output, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { BulkImportRowIn, EntriesApiService, EntryCategory } from '../../../core/entries-api.service';
import { ColumnSuggestion, MappingApiService, SheetDetectionResult } from '../../../core/mapping-api.service';
import {
  TARGET_FIELDS,
  TargetField,
  combineYearMonthToIso,
  formatPeriodLabel,
  guessMapping,
  parsePeriodToIso,
  parseSpreadsheet
} from './bulk-upload-wizard.utils';

type Step = 'upload' | 'preview' | 'mapping' | 'validate' | 'confirm';
type RowStatus = 'valid' | 'error' | 'created' | 'unchecked';
/** 'long' = the wizard's original shape, one row per (data point, period)
 * reading with role columns like Data point/Value/Period. 'wide' = the
 * customer's own file where each column IS a distinct metric (e.g.
 * "Diesel Consumed", "Grid Electricity" as separate columns) and rows are
 * periods -- detected automatically, backed by the same deterministic
 * alias/fuzzy/memory matcher /bulk-import/detect already has, just never
 * wired into this wizard until now. Both converge to the same
 * BulkImportRowIn[] shape before validation/commit. */
type UploadMode = 'long' | 'wide';

interface MappingChoice {
  headerIndex: number;
  header: string;
  target: string | null;
}

interface EditableRow {
  row_index: number;
  category: string | null; // only meaningful/shown in "all categories" mode
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
  private mappingApi = inject(MappingApiService);

  /** null = "all categories" mode -- one upload covering every category at
   * once, matched by (category, data_point_name) since a few field names
   * repeat across categories. */
  @Input() category: EntryCategory | null = null;
  /** Needed only in "all categories" mode, to populate the data-point
   * dropdown and label each row with its category. */
  @Input() allCategories: EntryCategory[] = [];
  @Input({ required: true }) locationId!: string;
  /** ISO "YYYY-MM-01" -- the period already selected at the top of the Data
   * Entry screen. Used for any row that doesn't specify its own period. */
  @Input({ required: true }) period!: string;
  @Output() done = new EventEmitter<void>();
  @Output() cancelled = new EventEmitter<void>();

  isAllCategories(): boolean {
    return this.category === null;
  }

  categoryOptions(): EntryCategory[] {
    return this.category ? [this.category] : this.allCategories;
  }

  targetFields: TargetField[] = TARGET_FIELDS;

  step = signal<Step>('upload');
  dragActive = signal(false);
  fileName = signal('');
  parseError = signal('');

  headers = signal<string[]>([]);
  rawRows = signal<unknown[][]>([]);
  mapping = signal<MappingChoice[]>([]);

  // 'wide' mode: the customer's own file, one column per metric, matched
  // via the backend's real alias/fuzzy/memory-of-past-confirmations
  // matcher (/bulk-import/detect) instead of the client-side role guesser
  // 'long' mode uses. Only available when a single category is selected --
  // "all categories" mode has no way to know which category a wide
  // column's metric belongs to.
  uploadMode = signal<UploadMode>('long');
  wideDetecting = signal(false);
  wideDetectResult = signal<SheetDetectionResult | null>(null);
  wideMapping = signal<Record<number, string | null>>({});
  /** Shown once on the Validate screen after an auto-skip, so the customer
   * isn't left wondering whether mapping happened at all -- it did, it
   * just didn't need them for it. */
  autoMappedMessage = signal('');

  /** Every column resolved by an exact-alias hit, a remembered column
   * (this customer confirmed this exact header before), or a remembered
   * whole-file template -- all effectively certain, unlike a "fuzzy"
   * guess. When the whole file clears this bar, there's nothing left for
   * a human to usefully check, so making them look at a mapping table
   * anyway is pure friction, not safety. */
  wideAllConfident = computed(() => {
    const cols = this.wideDetectResult()?.columns ?? [];
    if (cols.length === 0) return false;
    // Deliberately strict: an unmatched column stays a reason to show the
    // mapping screen, not something to silently skip past -- it might be
    // a real metric the matcher just didn't recognize, and dropping a
    // whole column's data without the customer ever seeing that is worse
    // than one extra click ever saves.
    const confidentRules = new Set(['exact_alias', 'memory', 'template']);
    const hasAnyDataPoint = cols.some((c) => c.target_type === 'data_point');
    return hasAnyDataPoint && cols.every((c) => confidentRules.has(c.rule));
  });

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
        this.parseError.set('This file looks empty — no rows to import.');
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
    await this.api.downloadCsvTemplate(this.category?.name ?? null);
  }

  backToUpload(): void {
    this.step.set('upload');
    this.headers.set([]);
    this.rawRows.set([]);
    this.fileName.set('');
    this.rowsBuiltForMapping = null;
    this.uploadMode.set('long');
    this.wideDetectResult.set(null);
    this.wideMapping.set({});
    this.autoMappedMessage.set('');
  }

  async confirmPreview(): Promise<void> {
    const guesses = guessMapping(this.headers());
    const looksLongFormat = guesses.includes('data_point_name') && guesses.includes('value');
    if (looksLongFormat || !this.category) {
      // "All categories" mode has no wide-format equivalent (a wide
      // column's metric could belong to any category), so it always uses
      // the long-format role-mapping flow regardless of this guess.
      this.uploadMode.set('long');
      this.mapping.set(this.headers().map((header, i) => ({ headerIndex: i, header, target: guesses[i] })));
      this.step.set('mapping');
    } else {
      this.uploadMode.set('wide');
      await this.runWideDetect();
      if (this.wideAllConfident()) {
        // Every column was recognized with certainty (an exact alias, a
        // column this customer has confirmed before, or the exact same
        // file structure as a remembered upload) -- there's nothing left
        // for a manual mapping screen to usefully ask, so skip straight
        // to showing the actual data.
        const count = this.wideDetectResult()?.columns.length ?? 0;
        this.autoMappedMessage.set(`Recognized all ${count} columns automatically — nothing to map.`);
        await this.runValidation();
      } else {
        this.step.set('mapping');
      }
    }
  }

  /** Manual override for when the auto-detected shape guessed wrong. */
  async switchUploadMode(mode: UploadMode): Promise<void> {
    if (mode === this.uploadMode()) return;
    if (mode === 'wide' && !this.category) return;
    this.uploadMode.set(mode);
    if (mode === 'wide' && !this.wideDetectResult()) {
      await this.runWideDetect();
    } else if (mode === 'long' && this.mapping().length === 0) {
      const guesses = guessMapping(this.headers());
      this.mapping.set(this.headers().map((header, i) => ({ headerIndex: i, header, target: guesses[i] })));
    }
  }

  setMapping(headerIndex: number, target: string): void {
    const list = this.mapping().map((m) => (m.headerIndex === headerIndex ? { ...m, target: target || null } : m));
    this.mapping.set(list);
  }

  targetLabel(key: string | null): string {
    return this.targetFields.find((f) => f.key === key)?.label ?? 'Unmatched';
  }

  // -- Wide-format mapping (one column per metric) --------------------

  private async runWideDetect(): Promise<void> {
    if (!this.category) return;
    this.wideDetecting.set(true);
    try {
      const response = await this.mappingApi.detect([{ name: this.category.name, filename: this.fileName(), headers: this.headers() }]);
      const result = response.sheets[0] ?? null;
      this.wideDetectResult.set(result);
      const initial: Record<number, string | null> = {};
      result?.columns.forEach((col, i) => (initial[i] = col.target));
      this.wideMapping.set(initial);
    } finally {
      this.wideDetecting.set(false);
    }
  }

  wideColumnAt(index: number): ColumnSuggestion | undefined {
    return this.wideDetectResult()?.columns[index];
  }

  setWideMapping(headerIndex: number, target: string): void {
    this.wideMapping.set({ ...this.wideMapping(), [headerIndex]: target || null });
  }

  wideMappingComplete = computed(() => Object.values(this.wideMapping()).some((t) => t && t !== 'period' && t !== 'note'));

  ruleLabel(rule: string | undefined): string {
    switch (rule) {
      case 'exact_alias':
        return 'Exact match';
      case 'fuzzy':
        return 'Likely match';
      case 'memory':
        return 'Remembered';
      case 'template':
        return 'Remembered file';
      default:
        return 'Unmatched';
    }
  }

  /** Resolves a data-point id to its name from the CURRENT mapping
   * selection -- not the original suggestion's data_point_name, which
   * goes stale the moment the user picks a different data point in the
   * dropdown. */
  private dataPointNameForId(id: string): string | undefined {
    const cats = this.isAllCategories() ? this.allCategories : this.category ? [this.category] : [];
    for (const cat of cats) {
      const dp = cat.data_points.find((d) => d.id === id);
      if (dp) return dp.name;
    }
    return undefined;
  }

  private buildRowsFromWideFile(): EditableRow[] {
    const result = this.wideDetectResult();
    const map = this.wideMapping();
    if (!result) return [];

    const periodIdx = result.columns.findIndex((_, i) => map[i] === 'period');
    const noteIdx = result.columns.findIndex((_, i) => map[i] === 'note');
    const dataPointCols = result.columns
      .map((_col, i) => ({ i, target: map[i] }))
      .filter((c) => c.target && c.target !== 'period' && c.target !== 'note')
      .map((c) => ({ i: c.i, name: this.dataPointNameForId(c.target!) }))
      .filter((c): c is { i: number; name: string } => !!c.name);

    const rows: EditableRow[] = [];
    let rowIndex = 2;
    for (const rawRow of this.rawRows()) {
      const periodRaw = periodIdx >= 0 ? rawRow[periodIdx] : null;
      const periodIso = (periodRaw ? parsePeriodToIso(periodRaw) : null) ?? this.period;
      const noteVal = noteIdx >= 0 ? String(rawRow[noteIdx] ?? '').trim() || null : null;
      for (const col of dataPointCols) {
        const raw = rawRow[col.i];
        if (raw === '' || raw === null || raw === undefined) continue; // not every metric has a value every row
        rows.push({
          row_index: rowIndex++,
          category: this.category?.name ?? null,
          data_point_name: col.name,
          period_iso: periodIso,
          value_raw: String(raw).trim(),
          unit_raw: null,
          note: noteVal,
          included: true,
          status: 'unchecked',
          message: null,
          entry_id: null,
          unitNote: null,
          suggestedUnit: null
        });
      }
    }
    return rows;
  }

  /** Best-effort: remembers the confirmed mapping (both the whole-file
   * fingerprint and, server-side, each individual column) so the exact
   * same file -- or just a column reused in a different file -- doesn't
   * need mapping again. A failure here shouldn't block the actual
   * upload. */
  private async saveWideMappingMemory(): Promise<void> {
    const result = this.wideDetectResult();
    if (!result?.category_id) return;
    const columnMapping: Record<string, string> = {};
    result.columns.forEach((col, i) => {
      const target = this.wideMapping()[i];
      if (target) columnMapping[col.header] = target;
    });
    if (Object.keys(columnMapping).length === 0) return;
    try {
      await this.mappingApi.saveTemplate(result.category_id, result.header_fingerprint, columnMapping);
    } catch {
      // non-fatal
    }
  }

  private buildRowsFromFile(): EditableRow[] {
    const mapping = this.mapping();
    const indexOf = (key: string) => mapping.find((m) => m.target === key)?.headerIndex;
    const categoryIdx = indexOf('category');
    const nameIdx = indexOf('data_point_name');
    const periodIdx = indexOf('period');
    const yearIdx = indexOf('year');
    const monthIdx = indexOf('month');
    const valueIdx = indexOf('value');
    const unitIdx = indexOf('unit');
    const noteIdx = indexOf('note');

    if (nameIdx === undefined || valueIdx === undefined) {
      return [];
    }

    return this.rawRows().map((row, i) => {
      const periodRaw = periodIdx !== undefined ? row[periodIdx] : null;
      // Either a single Period/Month/Date column, or separate Year + Month
      // columns (the shape the template now uses for a time series -- one
      // row per data point per month). A blank/unparseable cell falls back
      // to the period already selected above -- never a hard error here.
      const yearMonthIso = yearIdx !== undefined && monthIdx !== undefined ? combineYearMonthToIso(row[yearIdx], row[monthIdx]) : null;
      const periodIso = (periodRaw ? parsePeriodToIso(periodRaw) : null) ?? yearMonthIso ?? this.period;
      return {
        row_index: i + 2, // +1 for header row, +1 for 1-indexing
        category: categoryIdx !== undefined ? String(row[categoryIdx] ?? '').trim() || null : null,
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
    if (this.uploadMode() === 'wide') {
      const mappingKey = JSON.stringify(this.wideMapping());
      if (this.rows().length === 0 || mappingKey !== this.rowsBuiltForMapping) {
        this.rows.set(this.buildRowsFromWideFile());
        this.rowsBuiltForMapping = mappingKey;
      }
      void this.saveWideMappingMemory();
    } else {
      const mappingKey = JSON.stringify(this.mapping().map((m) => m.target));
      if (this.rows().length === 0 || mappingKey !== this.rowsBuiltForMapping) {
        this.rows.set(this.buildRowsFromFile());
        this.rowsBuiltForMapping = mappingKey;
      }
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
      category: r.category,
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
      const result = await this.api.bulkImport(
        this.category?.name ?? null,
        this.locationId,
        this.toPayloadRows(current),
        false,
        this.period
      );
      const byIndex = new Map(result.rows.map((r) => [r.row_index, r]));
      const merged = current.map((row) => {
        const r = byIndex.get(row.row_index);
        return {
          ...row,
          category: r?.category ?? row.category,
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
    const all = this.isAllCategories();
    const data = this.rows().map((r) => ({
      ...(all ? { category: r.category ?? '' } : {}),
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
    const widths = [{ wch: 28 }, { wch: 12 }, { wch: 12 }, { wch: 10 }, { wch: 20 }, { wch: 14 }, { wch: 40 }, { wch: 14 }];
    ws['!cols'] = all ? [{ wch: 18 }, ...widths] : widths;
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, 'Review');
    const filename = this.category ? this.category.name.replace(/\s+/g, '_') : 'all_categories';
    XLSX.writeFile(wb, `${filename}_review.xlsx`);
  }

  goToConfirm(): void {
    this.step.set('confirm');
  }

  async commitImport(): Promise<void> {
    const toCommit = this.includedValidRows();
    this.committing.set(true);
    this.commitError.set('');
    try {
      const result = await this.api.bulkImport(
        this.category?.name ?? null,
        this.locationId,
        this.toPayloadRows(toCommit),
        true,
        this.period
      );
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
    this.uploadMode.set('long');
    this.wideDetectResult.set(null);
    this.wideMapping.set({});
    this.autoMappedMessage.set('');
  }
}
