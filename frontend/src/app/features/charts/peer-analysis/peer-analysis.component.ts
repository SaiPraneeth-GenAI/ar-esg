import { DecimalPipe } from '@angular/common';
import { Component, OnInit, effect, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { PeerApiService, PeerCompany, PeerCompareYearResult, PeerExtractRow } from '../../../core/peer-api.service';

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
  // Public so the template can read extraction progress (extracting(),
  // extractElapsedSeconds(), extractResult()) straight off it -- it's a
  // root-provided singleton, so an in-flight extraction (and its result)
  // survives the user navigating to another tab and coming back.
  peerApi = inject(PeerApiService);

  loading = signal(true);
  errorMessage = signal('');
  successMessage = signal('');

  company = signal<PeerCompany | null>(null);
  savedYears = signal<number[]>([]);
  year = signal<number>(defaultYear());
  phase = signal<Phase>('upload');

  selectedFile = signal<File | null>(null);
  dragActive = signal(false);
  editableValues = signal<Record<string, number | null>>({});
  saving = signal(false);

  compareLoading = signal(false);
  compareResult = signal<PeerCompareYearResult | null>(null);

  constructor() {
    // Picks up a completed extraction whether it finished while the user
    // was still here or while they were off on another tab -- runs once on
    // mount too, so returning to an already-finished extraction jumps
    // straight to review instead of looking stuck.
    effect(() => {
      const result = this.peerApi.extractResult();
      const extracting = this.peerApi.extracting();
      const currentPhase = this.phase();
      if (result || extracting) {
        console.info('[peer-analysis] extraction state changed', { extracting, hasResult: !!result, phase: currentPhase });
      }
      if (!extracting && result && currentPhase === 'upload') {
        const values: Record<string, number | null> = {};
        for (const row of result.rows) values[row.key] = row.peer_value;
        this.editableValues.set(values);
        this.year.set(result.year);
        this.phase.set('review');
      }
    });
  }

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
      if (!this.peerApi.extracting() && !this.peerApi.extractResult()) {
        this.selectYear(this.savedYears()[0] ?? defaultYear());
      }
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
    if (this.hasDataFor(y)) {
      this.phase.set('compare');
      void this.loadCompare(y);
    } else {
      this.phase.set('upload');
    }
  }

  reupload(): void {
    const company = this.company();
    if (company) this.peerApi.invalidateCompare(company.id, this.year());
    this.phase.set('upload');
    this.peerApi.clearExtraction();
    this.selectedFile.set(null);
    this.successMessage.set('');
  }

  private acceptFile(file: File | null): void {
    this.errorMessage.set('');
    if (file && !file.name.toLowerCase().endsWith('.pdf')) {
      this.errorMessage.set('Please upload a PDF file.');
      this.selectedFile.set(null);
      return;
    }
    this.selectedFile.set(file);
  }

  onFileChange(event: Event): void {
    const input = event.target as HTMLInputElement;
    this.acceptFile(input.files?.[0] ?? null);
  }

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
    this.acceptFile(event.dataTransfer?.files?.[0] ?? null);
  }

  async extract(): Promise<void> {
    const company = this.company();
    const file = this.selectedFile();
    if (!company || !file) return;
    this.errorMessage.set('');
    // Fire-and-forget: state lives on PeerApiService, so this keeps running
    // (and the constructor's effect() picks up the result) even if the
    // user navigates to another tab while it works.
    void this.peerApi.startExtraction(company.id, file, this.year());
  }

  groupedRows(): { group: string; rows: PeerExtractRow[] }[] {
    const rows = this.peerApi.extractResult()?.rows ?? [];
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
        data_source: this.peerApi.extractResult()?.source_filename || 'Manual entry',
        source_link: null,
        data_confidence: 'self_reported',
        notes: null
      });
      this.successMessage.set('Comparison saved.');

      // Build the comparison straight from what's already in memory (the
      // AR reference values fetched during extraction, the peer values just
      // confirmed) instead of re-fetching and recomputing everything from
      // the server -- this becomes the cached result for the year until a
      // re-upload invalidates it.
      const extractResult = this.peerApi.extractResult();
      const result: PeerCompareYearResult = {
        year: this.year(),
        peer_company_name: extractResult?.peer_company_name ?? company.name,
        groups: this.groupedRows().map((g) => ({
          group: g.group,
          metrics: g.rows.map((r) => ({
            key: r.key,
            label: r.label,
            unit: r.unit,
            amara_raja_value: r.amara_raja_value,
            peer_value: this.editableValues()[r.key] ?? null
          }))
        }))
      };
      this.peerApi.setCachedCompare(company.id, this.year(), result);
      this.compareResult.set(result);

      this.peerApi.clearExtraction();
      await this.refreshSavedYears();
      this.phase.set('compare');
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
