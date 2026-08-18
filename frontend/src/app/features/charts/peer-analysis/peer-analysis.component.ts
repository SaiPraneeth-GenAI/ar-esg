import { DecimalPipe } from '@angular/common';
import { Component, OnInit, computed, effect, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { PeerApiService, PeerCompany, PeerCompareYearResult, PeerExtractRow } from '../../../core/peer-api.service';

type Phase = 'upload' | 'review' | 'compare';

// The comparison algorithm itself never changes per company -- extract,
// review, save, compare-year all take a company_id and work identically
// for any of them. This cap is purely a UI/UX choice (side-by-side gets
// cramped past four peers), not a backend limitation.
const MAX_PEERS = 4;

interface MultiCompareRow {
  key: string;
  label: string;
  unit: string;
  amara_raja_value: number | null;
  peerValues: (number | null)[];
}

interface MultiCompareGroup {
  group: string;
  rows: MultiCompareRow[];
}

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

  // Every peer this tenant tracks (up to MAX_PEERS) -- `company` is
  // whichever one is currently selected for the upload/review/compare
  // flow below, same as the old single-company version, just no longer
  // hardcoded to one auto-provisioned default.
  companies = signal<PeerCompany[]>([]);
  selectedCompanyId = signal<string | null>(null);
  company = computed<PeerCompany | null>(() => this.companies().find((c) => c.id === this.selectedCompanyId()) ?? null);

  addingPeer = signal(false);
  newPeerName = signal('');
  newPeerIndustry = signal('');
  newPeerCountry = signal('');
  addPeerError = signal('');

  canAddPeer(): boolean {
    return this.companies().length < MAX_PEERS;
  }

  savedYears = signal<number[]>([]);
  year = signal<number>(defaultYear());
  phase = signal<Phase>('upload');

  // Side-by-side view: Amara Raja vs every peer that has data for the
  // selected year, all at once -- not just the currently selected one.
  showCompareAll = signal(false);
  compareAllLoading = signal(false);
  compareAllCompanies = signal<PeerCompany[]>([]);
  compareAllGroups = signal<MultiCompareGroup[]>([]);

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
      let companies = await this.peerApi.listCompanies();
      if (companies.length === 0) {
        // First-ever visit for this tenant: seed one starting peer so the
        // page isn't empty -- fully editable/removable afterward, not a
        // hardcoded fixture the rest of the UI assumes exists.
        await this.peerApi.getDefaultCompany();
        companies = await this.peerApi.listCompanies();
      }
      this.companies.set(companies);
      this.selectedCompanyId.set(companies[0]?.id ?? null);
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

  // -- Multi-peer: switching which company the upload/review/compare flow
  // above operates on, and adding up to MAX_PEERS of them ------------------

  async selectCompany(id: string): Promise<void> {
    if (id === this.selectedCompanyId()) return;
    this.selectedCompanyId.set(id);
    this.errorMessage.set('');
    this.successMessage.set('');
    this.selectedFile.set(null);
    this.showCompareAll.set(false);
    await this.refreshSavedYears();
    this.selectYear(this.savedYears()[0] ?? defaultYear());
  }

  startAddPeer(): void {
    this.addingPeer.set(true);
    this.newPeerName.set('');
    this.newPeerIndustry.set('');
    this.newPeerCountry.set('');
    this.addPeerError.set('');
  }

  cancelAddPeer(): void {
    this.addingPeer.set(false);
  }

  async confirmAddPeer(): Promise<void> {
    const name = this.newPeerName().trim();
    if (!name) {
      this.addPeerError.set('Enter a company name.');
      return;
    }
    if (!this.canAddPeer()) {
      this.addPeerError.set(`Up to ${MAX_PEERS} peers at a time — archive one first if you need a different one.`);
      return;
    }
    this.addPeerError.set('');
    try {
      const created = await this.peerApi.createCompany({
        name,
        industry: this.newPeerIndustry().trim() || null,
        country: this.newPeerCountry().trim() || null
      });
      this.companies.set([...this.companies(), created]);
      this.addingPeer.set(false);
      await this.selectCompany(created.id);
    } catch (err: any) {
      this.addPeerError.set(err?.error?.detail ?? 'Could not add this peer company.');
    }
  }

  async removePeer(company: PeerCompany, event: Event): Promise<void> {
    event.stopPropagation(); // the pill itself also has a (click) to select -- don't select a peer we're about to delete
    const note = company.period_count > 0 ? ` and its ${company.period_count} saved year${company.period_count === 1 ? '' : 's'} of data` : '';
    if (!confirm(`Remove ${company.name}${note}? This can't be undone.`)) return;

    this.errorMessage.set('');
    try {
      await this.peerApi.deleteCompany(company.id);
      const remaining = this.companies().filter((c) => c.id !== company.id);
      this.companies.set(remaining);
      if (this.selectedCompanyId() === company.id) {
        this.selectedCompanyId.set(null);
        this.showCompareAll.set(false);
        if (remaining.length > 0) {
          await this.selectCompany(remaining[0].id);
        } else {
          this.savedYears.set([]);
          this.compareResult.set(null);
          this.phase.set('upload');
        }
      }
    } catch (err: any) {
      this.errorMessage.set(err?.error?.detail ?? 'Could not remove this peer company.');
    }
  }

  // -- Side-by-side: Amara Raja vs every peer with data for this year -----

  async toggleCompareAll(): Promise<void> {
    this.showCompareAll.set(!this.showCompareAll());
    if (this.showCompareAll()) await this.loadCompareAll();
  }

  private async loadCompareAll(): Promise<void> {
    this.compareAllLoading.set(true);
    this.errorMessage.set('');
    try {
      const year = this.year();
      const settled = await Promise.all(
        this.companies().map(async (c) => {
          try {
            return { company: c, result: await this.peerApi.compareYear(c.id, year) };
          } catch {
            return null; // no data saved for this peer/year yet -- skip it, not an error
          }
        })
      );
      const withData = settled.filter((s): s is { company: PeerCompany; result: PeerCompareYearResult } => s !== null);
      this.compareAllCompanies.set(withData.map((w) => w.company));

      const groups: MultiCompareGroup[] = [];
      const first = withData[0]?.result;
      if (first) {
        for (const g of first.groups) {
          groups.push({
            group: g.group,
            rows: g.metrics.map((m) => ({
              key: m.key,
              label: m.label,
              unit: m.unit,
              amara_raja_value: m.amara_raja_value,
              peerValues: withData.map((w) => {
                const group = w.result.groups.find((gr) => gr.group === g.group);
                return group?.metrics.find((mm) => mm.key === m.key)?.peer_value ?? null;
              })
            }))
          });
        }
      }
      this.compareAllGroups.set(groups);
    } catch {
      this.errorMessage.set('Could not load the side-by-side comparison.');
    } finally {
      this.compareAllLoading.set(false);
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
    // Awaited directly: if this component is still mounted when the job
    // finishes, transition right here -- no dependency on a separate
    // effect() noticing the signals changed later. If the user navigates
    // away and this component gets destroyed before the promise settles,
    // that's fine too: the state lives on PeerApiService (a root
    // singleton), so the constructor's effect() on whatever component
    // instance exists when they come back still picks it up from the
    // signals directly, independent of this awaited call ever resolving
    // against a live instance.
    const result = await this.peerApi.startExtraction(company.id, file, this.year());
    if (result && this.phase() === 'upload') {
      const values: Record<string, number | null> = {};
      for (const row of result.rows) values[row.key] = row.peer_value;
      this.editableValues.set(values);
      this.year.set(result.year);
      this.phase.set('review');
    }
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
