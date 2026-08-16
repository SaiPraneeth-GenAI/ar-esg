import { Component, EventEmitter, Output, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import {
  EFFactorDraft,
  EFSheetDetectionResult,
  EFSheetInput,
  EmissionFactorsApiService
} from '../../../core/emission-factors-api.service';
import { COLUMN_ROLE_LABEL, COLUMN_ROLE_OPTIONS, ParsedSheet, parseWorkbookAllSheets } from './emission-factor-bulk-upload-wizard.utils';

type Step = 'upload' | 'mapping' | 'validate' | 'confirm';

const CURRENT_YEAR = new Date().getFullYear();
const SCOPE3_CATEGORIES = [
  'Purchased Goods & Services',
  'Capital Goods',
  'Fuel- and Energy-Related Activities',
  'Upstream Transportation & Distribution',
  'Waste Generated in Operations',
  'Business Travel',
  'Employee Commuting',
  'Upstream Leased Assets',
  'Downstream Transportation & Distribution',
  'Processing of Sold Products',
  'Use of Sold Products',
  'End-of-Life Treatment of Sold Products',
  'Downstream Leased Assets',
  'Franchises',
  'Investments'
];

@Component({
  selector: 'app-emission-factor-bulk-upload-wizard',
  standalone: true,
  imports: [FormsModule],
  templateUrl: './emission-factor-bulk-upload-wizard.component.html',
  styleUrl: './emission-factor-bulk-upload-wizard.component.css'
})
export class EmissionFactorBulkUploadWizardComponent {
  private api = inject(EmissionFactorsApiService);
  @Output() done = new EventEmitter<void>();

  columnRoleOptions = COLUMN_ROLE_OPTIONS;
  columnRoleLabel = COLUMN_ROLE_LABEL;
  scope3Categories = SCOPE3_CATEGORIES;

  step = signal<Step>('upload');
  dragActive = signal(false);
  fileName = signal('');
  parseError = signal('');
  detecting = signal(false);

  defaultEffectiveYear = signal(CURRENT_YEAR);
  defaultMethod = signal<'location-based' | 'market-based' | ''>('location-based');

  parsedSheets = signal<ParsedSheet[]>([]);
  detection = signal<EFSheetDetectionResult[]>([]);
  columnOverrides = signal<Map<string, Map<string, string>>>(new Map());

  rows = signal<EFFactorDraft[]>([]);
  validating = signal(false);

  committing = signal(false);
  commitError = signal('');
  commitResult = signal<{ created: number; error: number } | null>(null);

  includedValidRows = computed(() => this.rows().filter((r) => r.included && r.status !== 'error' && r.status !== 'skip'));
  errorRows = computed(() => this.rows().filter((r) => r.status === 'error' || r.status === 'missing_source'));
  hasUnchecked = computed(() => this.rows().some((r) => r.status === 'unchecked'));
  readyRows = computed(() => this.rows().filter((r) => r.status === 'ready'));

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
    if (file) void this.loadFile(file);
  }

  onFileInputChange(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    if (file) void this.loadFile(file);
    input.value = '';
  }

  private async loadFile(file: File): Promise<void> {
    this.parseError.set('');
    this.fileName.set(file.name);
    try {
      const sheets = await parseWorkbookAllSheets(file);
      if (sheets.length === 0) {
        this.parseError.set('This file looks empty -- no sheets with data found.');
        return;
      }
      this.parsedSheets.set(sheets);
      await this.runDetect();
      this.step.set('mapping');
    } catch {
      this.parseError.set('Could not read this file. Make sure it is a .xlsx, .xls, or .csv file.');
    }
  }

  private buildSheetInputs(): EFSheetInput[] {
    const overrides = this.columnOverrides();
    return this.parsedSheets().map((s) => {
      const key = s.name;
      const sheetOverrides = overrides.get(key);
      return {
        name: s.name,
        filename: this.fileName(),
        headers: s.headers,
        rows: s.rows,
        column_overrides: sheetOverrides ? Object.fromEntries(sheetOverrides) : null
      };
    });
  }

  async runDetect(): Promise<void> {
    this.detecting.set(true);
    try {
      const result = await this.api.bulkDetect(
        this.buildSheetInputs(),
        this.defaultEffectiveYear(),
        this.defaultMethod() || null
      );
      this.detection.set(result.sheets);
    } finally {
      this.detecting.set(false);
    }
  }

  setColumnOverride(sheetName: string, blockIndex: number, colIndex: number, role: string): void {
    const overrides = new Map(this.columnOverrides());
    const sheetMap = new Map(overrides.get(sheetName) ?? []);
    sheetMap.set(`${blockIndex}:${colIndex}`, role);
    overrides.set(sheetName, sheetMap);
    this.columnOverrides.set(overrides);
  }

  overrideFor(sheetName: string, blockIndex: number, colIndex: number): string | null {
    return this.columnOverrides().get(sheetName)?.get(`${blockIndex}:${colIndex}`) ?? null;
  }

  async applyMappingAndContinue(): Promise<void> {
    await this.runDetect();
    const allDrafts = this.detection().flatMap((s) => s.factors);
    this.rows.set(allDrafts);
    this.step.set('validate');
  }

  rowKey(row: EFFactorDraft): string {
    return `${row.sheet_name}:${row.block_index}:${row.row_index}:${row.version ?? ''}`;
  }

  updateRow(key: string, patch: Partial<EFFactorDraft>): void {
    const list = this.rows().map((r) =>
      this.rowKey(r) === key ? { ...r, ...patch, status: 'unchecked' as const, message: null } : r
    );
    this.rows.set(list);
  }

  toggleIncluded(key: string): void {
    const list = this.rows().map((r) => (this.rowKey(r) === key ? { ...r, included: !r.included } : r));
    this.rows.set(list);
  }

  removeRow(key: string): void {
    this.rows.set(this.rows().filter((r) => this.rowKey(r) !== key));
  }

  async recheck(): Promise<void> {
    const current = this.rows();
    if (current.length === 0) return;
    this.validating.set(true);
    try {
      const result = await this.api.bulkImport(current, false);
      const byKey = new Map(result.results.map((r, i) => [i, r]));
      const merged = current.map((row, i) => {
        const r = byKey.get(i);
        return r ? { ...row, status: r.status, message: r.message } : row;
      });
      this.rows.set(merged);
    } finally {
      this.validating.set(false);
    }
  }

  goToConfirm(): void {
    this.step.set('confirm');
  }

  async commitImport(): Promise<void> {
    this.committing.set(true);
    this.commitError.set('');
    try {
      const result = await this.api.bulkImport(this.includedValidRows(), true);
      this.commitResult.set({ created: result.created_count, error: result.error_count });
    } catch {
      this.commitError.set('Could not create these factors. Nothing was saved.');
    } finally {
      this.committing.set(false);
    }
  }

  finish(): void {
    this.done.emit();
  }

  startOver(): void {
    this.step.set('upload');
    this.parsedSheets.set([]);
    this.detection.set([]);
    this.columnOverrides.set(new Map());
    this.rows.set([]);
    this.commitResult.set(null);
    this.commitError.set('');
    this.fileName.set('');
  }
}
