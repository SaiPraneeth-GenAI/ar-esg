import { DecimalPipe } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import {
  PeerApiService,
  PeerCompany,
  PeerCompareYearResult,
  PeerExtractResult,
  PeerExtractRow
} from '../../../core/peer-api.service';

type Phase = 'upload' | 'review' | 'compare';

function defaultYear(): number {
  return new Date().getFullYear() - 1;
}

@Component({
  selector: 'app-peer-analysis',
  standalone: true,
  imports: [FormsModule, DecimalPipe],
  templateUrl: './peer-analysis.component.html',
  styleUrl: './peer-analysis.component.css'
})
export class PeerAnalysisComponent implements OnInit {
  private peerApi = inject(PeerApiService);

  loading = signal(true);
  errorMessage = signal('');
  successMessage = signal('');

  company = signal<PeerCompany | null>(null);
  savedYears = signal<number[]>([]);
  year = signal<number>(defaultYear());
  phase = signal<Phase>('upload');

  selectedFile = signal<File | null>(null);
  extracting = signal(false);
  extractResult = signal<PeerExtractResult | null>(null);
  editableValues = signal<Record<string, number | null>>({});
  saving = signal(false);

  compareLoading = signal(false);
  compareResult = signal<PeerCompareYearResult | null>(null);

  yearOptions(): number[] {
    const current = new Date().getFullYear();
    return [current, current - 1, current - 2, current - 3, current - 4];
  }

  async ngOnInit(): Promise<void> {
    this.loading.set(true);
    this.errorMessage.set('');
    try {
      const company = await this.peerApi.getDefaultCompany();
      this.company.set(company);
      await this.refreshSavedYears();
      this.selectYear(this.savedYears()[0] ?? defaultYear());
    } catch {
      this.errorMessage.set('Could not load peer comparison data.');
    } finally {
      this.loading.set(false);
    }
  }

  private async refreshSavedYears(): Promise<void> {
    const company = this.company();
    if (!company) return;
    const rows = await this.peerApi.listData(company.id);
    const years = Array.from(new Set(rows.map((r) => new Date(`${r.period}T00:00:00`).getFullYear()))).sort((a, b) => b - a);
    this.savedYears.set(years);
  }

  hasDataFor(y: number): boolean {
    return this.savedYears().includes(y);
  }

  selectYear(y: number): void {
    this.year.set(y);
    this.errorMessage.set('');
    this.successMessage.set('');
    this.selectedFile.set(null);
    this.extractResult.set(null);
    if (this.hasDataFor(y)) {
      this.phase.set('compare');
      void this.loadCompare(y);
    } else {
      this.phase.set('upload');
    }
  }

  reupload(): void {
    this.phase.set('upload');
    this.extractResult.set(null);
    this.selectedFile.set(null);
    this.successMessage.set('');
  }

  onFileChange(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0] ?? null;
    this.errorMessage.set('');
    if (file && !file.name.toLowerCase().endsWith('.pdf')) {
      this.errorMessage.set('Please upload a PDF file.');
      this.selectedFile.set(null);
      return;
    }
    this.selectedFile.set(file);
  }

  async extract(): Promise<void> {
    const company = this.company();
    const file = this.selectedFile();
    if (!company || !file) return;
    this.extracting.set(true);
    this.errorMessage.set('');
    try {
      const result = await this.peerApi.extractPdf(company.id, file, this.year());
      this.extractResult.set(result);
      const values: Record<string, number | null> = {};
      for (const row of result.rows) values[row.key] = row.peer_value;
      this.editableValues.set(values);
      this.phase.set('review');
    } catch (err: any) {
      this.errorMessage.set(err?.message ?? 'Could not read this PDF. You can still enter figures by hand below.');
      const rows = this.buildBlankRows();
      this.extractResult.set(rows);
      const values: Record<string, number | null> = {};
      for (const row of rows.rows) values[row.key] = null;
      this.editableValues.set(values);
      this.phase.set('review');
    } finally {
      this.extracting.set(false);
    }
  }

  private buildBlankRows(): PeerExtractResult {
    const company = this.company()!;
    return { peer_company_id: company.id, peer_company_name: company.name, year: this.year(), source_filename: '', rows: [] };
  }

  groupedRows(): { group: string; rows: PeerExtractRow[] }[] {
    const rows = this.extractResult()?.rows ?? [];
    const groups: { group: string; rows: PeerExtractRow[] }[] = [];
    for (const row of rows) {
      let bucket = groups.find((g) => g.group === row.group);
      if (!bucket) {
        bucket = { group: row.group, rows: [] };
        groups.push(bucket);
      }
      bucket.rows.push(row);
    }
    return groups;
  }

  setPeerValue(key: string, value: string): void {
    const values = { ...this.editableValues() };
    values[key] = value === '' ? null : Number(value);
    this.editableValues.set(values);
  }

  filledCount(): number {
    return Object.values(this.editableValues()).filter((v) => v !== null && v !== undefined).length;
  }

  async saveComparison(): Promise<void> {
    const company = this.company();
    if (!company || this.filledCount() === 0) return;
    this.saving.set(true);
    this.errorMessage.set('');
    try {
      const metrics: Record<string, number> = {};
      for (const [key, value] of Object.entries(this.editableValues())) {
        if (value !== null && value !== undefined) metrics[key] = value;
      }
      await this.peerApi.upsertData(company.id, {
        period: `${this.year()}-01-01`,
        metrics,
        data_source: this.extractResult()?.source_filename || 'Manual entry',
        source_link: null,
        data_confidence: 'self_reported',
        notes: null
      });
      this.successMessage.set('Comparison saved.');
      await this.refreshSavedYears();
      this.phase.set('compare');
      await this.loadCompare(this.year());
    } catch (err: any) {
      this.errorMessage.set(err?.error?.detail ?? 'Could not save this comparison.');
    } finally {
      this.saving.set(false);
    }
  }

  private async loadCompare(year: number): Promise<void> {
    const company = this.company();
    if (!company) return;
    this.compareLoading.set(true);
    this.errorMessage.set('');
    try {
      this.compareResult.set(await this.peerApi.compareYear(company.id, year));
    } catch {
      this.errorMessage.set('Could not load the comparison.');
    } finally {
      this.compareLoading.set(false);
    }
  }

  barPct(value: number | null, max: number): number {
    if (value === null || value === undefined) return 0;
    return Math.max((value / max) * 100, value === 0 ? 0 : 2);
  }

  pairMax(a: number | null, b: number | null): number {
    return Math.max(a ?? 0, b ?? 0, 0.0001);
  }
}
