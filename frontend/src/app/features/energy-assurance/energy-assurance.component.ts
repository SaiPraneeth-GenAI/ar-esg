import { CommonModule } from '@angular/common';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import {
  AssuranceMeter,
  AssuranceReading,
  AssuranceSource,
  AssuranceWorkspace,
  EnergyAssuranceApiService,
  ImportResult,
  ImportRow
} from '../../core/energy-assurance-api.service';

type Tab = 'overview' | 'registry' | 'ledger' | 'reconciliation' | 'lineage';
type MappingKey = 'meter_code' | 'period' | 'value' | 'unit' | 'evidence_reference';

@Component({
  selector: 'app-energy-assurance',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './energy-assurance.component.html',
  styleUrl: './energy-assurance.component.css'
})
export class EnergyAssuranceComponent implements OnInit {
  private api = inject(EnergyAssuranceApiService);

  workspace = signal<AssuranceWorkspace | null>(null);
  activeTab = signal<Tab>('overview');
  loading = signal(true);
  actionBusy = signal(false);
  errorMessage = signal('');
  successMessage = signal('');
  period = '2026-08-01';
  periodMonth = '2026-08';

  showSourceForm = signal(false);
  showMeterForm = signal(false);
  sourceForm = { name: '', source_type: 'grid', supplier: '', renewable: false };
  meterForm = { source_id: '', meter_code: '', name: '', unit: 'kWh', direction: 'import' };

  fileName = signal('');
  headers = signal<string[]>([]);
  rawRows = signal<Record<string, unknown>[]>([]);
  importResult = signal<ImportResult | null>(null);
  importMapping: Record<MappingKey, string> = {
    meter_code: '', period: '', value: '', unit: '', evidence_reference: ''
  };
  mappingFields: Array<{ key: MappingKey; label: string; required: boolean }> = [
    { key: 'meter_code', label: 'Meter code', required: true },
    { key: 'period', label: 'Reporting period', required: true },
    { key: 'value', label: 'Reading value', required: true },
    { key: 'unit', label: 'Unit', required: false },
    { key: 'evidence_reference', label: 'Evidence reference', required: false }
  ];

  tabs: Array<{ id: Tab; label: string; number: string }> = [
    { id: 'overview', label: 'Control overview', number: '01' },
    { id: 'registry', label: 'Sources & meters', number: '02' },
    { id: 'ledger', label: 'Reading ledger', number: '03' },
    { id: 'reconciliation', label: 'Reconciliation', number: '04' },
    { id: 'lineage', label: 'Source-to-result', number: '05' }
  ];

  exceptionReconciliations = computed(() => this.workspace()?.reconciliations.filter((r) => r.status !== 'passed') ?? []);

  async ngOnInit(): Promise<void> {
    await this.load();
  }

  async load(): Promise<void> {
    this.loading.set(true);
    this.errorMessage.set('');
    try {
      this.workspace.set(await this.api.workspace(undefined, this.period));
    } catch (err) {
      if ((err as { status?: number }).status !== 404) this.errorMessage.set(this.errorOf(err));
      this.workspace.set(null);
    } finally {
      this.loading.set(false);
    }
  }

  async seedDemo(): Promise<void> {
    this.actionBusy.set(true);
    this.errorMessage.set('');
    try {
      await this.api.seedDemo();
      await this.load();
      this.successMessage.set('Synthetic assurance workspace loaded. No operational customer data is used.');
    } catch (err) {
      this.errorMessage.set(this.errorOf(err));
    } finally {
      this.actionBusy.set(false);
    }
  }

  setTab(tab: Tab): void { this.activeTab.set(tab); this.successMessage.set(''); }

  async changePeriod(): Promise<void> {
    this.period = `${this.periodMonth}-01`;
    await this.refresh();
  }

  async addSource(): Promise<void> {
    const ws = this.workspace();
    if (!ws || !this.sourceForm.name.trim()) return;
    await this.act(async () => {
      await this.api.createSource({ site_id: ws.active_site.id, ...this.sourceForm });
      this.sourceForm = { name: '', source_type: 'grid', supplier: '', renewable: false };
      this.showSourceForm.set(false);
    }, 'Energy source added.');
  }

  async editSource(source: AssuranceSource): Promise<void> {
    const name = prompt('Source name', source.name)?.trim();
    if (!name) return;
    const supplier = prompt('Supplier or operator', source.supplier ?? '') ?? source.supplier;
    await this.act(() => this.api.updateSource(source.id, { name, supplier }), 'Energy source updated.');
  }

  startMeterForm(sourceId?: string): void {
    this.meterForm = { source_id: sourceId ?? this.workspace()?.sources[0]?.id ?? '', meter_code: '', name: '', unit: 'kWh', direction: 'import' };
    this.showMeterForm.set(true);
  }

  async addMeter(): Promise<void> {
    const ws = this.workspace();
    if (!ws || !this.meterForm.source_id || !this.meterForm.meter_code.trim() || !this.meterForm.name.trim()) return;
    await this.act(async () => {
      await this.api.createMeter({ site_id: ws.active_site.id, ...this.meterForm });
      this.showMeterForm.set(false);
    }, 'Meter added to the isolated registry.');
  }

  async editMeter(meter: AssuranceMeter): Promise<void> {
    const name = prompt('Meter name', meter.name)?.trim();
    if (!name) return;
    await this.act(() => this.api.updateMeter(meter.id, { name }), 'Meter updated.');
  }

  async editReading(reading: AssuranceReading): Promise<void> {
    const valueText = prompt(`Reading value (${reading.unit})`, String(reading.value));
    if (valueText === null || valueText.trim() === '' || Number.isNaN(Number(valueText))) return;
    const evidence = prompt('Evidence reference', reading.evidence_reference ?? '') ?? reading.evidence_reference;
    const status = prompt('Status: review, approved, or rejected', reading.status)?.trim().toLowerCase() ?? reading.status;
    if (!['review', 'approved', 'rejected'].includes(status)) {
      this.errorMessage.set('Status must be review, approved, or rejected.');
      return;
    }
    await this.act(() => this.api.updateReading(reading.id, { value: Number(valueText), evidence_reference: evidence || null, status }), 'Reading updated and controls recalculated.');
  }

  async downloadSampleWorkbook(): Promise<void> {
    const XLSX = await import('xlsx');
    const rows = [
      { 'Meter ID': 'GRID-MAIN-01', Period: '2026-09-01', Reading: 101250, Unit: 'kWh', Evidence: 'September grid bill — synthetic' },
      { 'Meter ID': 'SOLAR-INV-01', Period: '2026-09-01', Reading: 11.8, Unit: 'MWh', Evidence: 'Inverter statement A — synthetic' },
      { 'Meter ID': 'SOLAR-INV-02', Period: '2026-09-01', Reading: 10900, Unit: 'kWh', Evidence: '' },
      { 'Meter ID': 'SOLAR-INV-02', Period: '2026-09-01', Reading: 10900, Unit: 'kWh', Evidence: 'Deliberate duplicate row' },
      { 'Meter ID': 'UNKNOWN-01', Period: '2026-09-01', Reading: 5000, Unit: 'kWh', Evidence: 'Deliberate unknown meter' }
    ];
    const workbook = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(workbook, XLSX.utils.json_to_sheet(rows), 'Energy readings');
    XLSX.writeFile(workbook, 'energy_assurance_synthetic_import.xlsx');
  }

  async onFileSelected(event: Event): Promise<void> {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) return;
    if (!/\.(xlsx|xls|csv)$/i.test(file.name)) {
      this.errorMessage.set('Choose an Excel or CSV file.');
      return;
    }
    const XLSX = await import('xlsx');
    const workbook = XLSX.read(await file.arrayBuffer(), { type: 'array', cellDates: true });
    const sheet = workbook.Sheets[workbook.SheetNames[0]];
    const rows = XLSX.utils.sheet_to_json<Record<string, unknown>>(sheet, { defval: '' });
    const headers = rows.length ? Object.keys(rows[0]) : [];
    this.fileName.set(file.name);
    this.rawRows.set(rows);
    this.headers.set(headers);
    this.importResult.set(null);
    this.autoMap(headers);
  }

  autoMap(headers: string[]): void {
    const find = (patterns: RegExp[]) => headers.find((h) => patterns.some((p) => p.test(h.toLowerCase()))) ?? '';
    this.importMapping = {
      meter_code: find([/meter.*(id|code|no)/, /^meter$/]),
      period: find([/period/, /month/, /date/]),
      value: find([/reading/, /consumption/, /generation/, /value/, /energy/]),
      unit: find([/^unit$/, /uom/]),
      evidence_reference: find([/evidence/, /invoice/, /bill.*(ref|no)/, /document/])
    };
  }

  mappedRows(): ImportRow[] {
    return this.rawRows().map((row, index) => ({
      row_index: index + 2,
      meter_code: String(row[this.importMapping.meter_code] ?? ''),
      period: this.toIsoPeriod(row[this.importMapping.period]),
      value: String(row[this.importMapping.value] ?? ''),
      unit: this.importMapping.unit ? String(row[this.importMapping.unit] ?? 'kWh') : 'kWh',
      evidence_reference: this.importMapping.evidence_reference ? String(row[this.importMapping.evidence_reference] ?? '') || null : null
    }));
  }

  async previewImport(commit = false): Promise<void> {
    const ws = this.workspace();
    if (!ws || !this.fileName() || !this.importMapping.meter_code || !this.importMapping.period || !this.importMapping.value) {
      this.errorMessage.set('Map meter code, reporting period, and reading value before validating.');
      return;
    }
    this.actionBusy.set(true);
    this.errorMessage.set('');
    try {
      const result = await this.api.importReadings(ws.active_site.id, this.fileName(), this.mappedRows(), commit);
      this.importResult.set(result);
      if (commit && result.imported_count) {
        this.successMessage.set(`${result.imported_count} readings imported into the isolated ledger.`);
        await this.refresh();
      }
    } catch (err) {
      this.errorMessage.set(this.errorOf(err));
    } finally {
      this.actionBusy.set(false);
    }
  }

  formatNumber(value: number | null, digits = 0): string {
    return value == null ? '—' : new Intl.NumberFormat('en-IN', { maximumFractionDigits: digits }).format(value);
  }

  sourceIcon(type: string): string {
    return type === 'grid' ? 'GRID' : type.includes('renewable') ? 'RE' : type === 'generator' ? 'DG' : 'SRC';
  }

  sourceType(type: string): string { return type.replaceAll('_', ' ').replace(/\b\w/g, (m) => m.toUpperCase()); }

  private async act(operation: () => Promise<unknown>, message: string): Promise<void> {
    this.actionBusy.set(true);
    this.errorMessage.set('');
    this.successMessage.set('');
    try {
      await operation();
      await this.refresh();
      this.successMessage.set(message);
    } catch (err) {
      this.errorMessage.set(this.errorOf(err));
    } finally {
      this.actionBusy.set(false);
    }
  }

  private async refresh(): Promise<void> {
    const siteId = this.workspace()?.active_site.id;
    this.workspace.set(await this.api.workspace(siteId, this.period));
  }

  private toIsoPeriod(value: unknown): string {
    if (value instanceof Date) return `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, '0')}-01`;
    if (typeof value === 'number') {
      const d = new Date(Date.UTC(1899, 11, 30) + value * 86400000);
      return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}-01`;
    }
    const text = String(value ?? '').trim();
    if (/^\d{4}-\d{2}$/.test(text)) return `${text}-01`;
    if (/^\d{4}-\d{2}-\d{2}/.test(text)) return text.slice(0, 10);
    return text;
  }

  private errorOf(err: unknown): string {
    return (err as { error?: { detail?: string } })?.error?.detail ?? 'The Energy Assurance request could not be completed.';
  }
}
