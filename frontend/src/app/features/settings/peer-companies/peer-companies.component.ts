import { DecimalPipe } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ChartApiService, ChartMetric } from '../../../core/chart-api.service';
import { PeerApiService, PeerCompany, PeerData } from '../../../core/peer-api.service';

function currentMonthValue(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
}

const CONFIDENCE_LABELS: Record<string, string> = {
  verified: 'Verified',
  self_reported: 'Self-reported',
  estimated: 'Estimated'
};

@Component({
  selector: 'app-peer-companies',
  standalone: true,
  imports: [FormsModule, DecimalPipe],
  templateUrl: './peer-companies.component.html',
  styleUrl: './peer-companies.component.css'
})
export class PeerCompaniesComponent implements OnInit {
  private peerApi = inject(PeerApiService);
  private chartApi = inject(ChartApiService);

  loading = signal(true);
  errorMessage = signal('');
  successMessage = signal('');
  companies = signal<PeerCompany[]>([]);
  metrics = signal<ChartMetric[]>([]);

  showAddCompany = signal(false);
  newCompanyName = signal('');
  newCompanyIndustry = signal('');
  newCompanyCountry = signal('');

  expandedCompanyId = signal<string | null>(null);
  companyData = signal<PeerData[]>([]);
  dataLoading = signal(false);

  showAddPeriod = signal(false);
  periodValue = signal(currentMonthValue());
  periodMetricValues = signal<Record<string, number | null>>({});
  dataSource = signal('');
  sourceLink = signal('');
  dataConfidence = signal<string>('self_reported');
  notes = signal('');
  submittingPeriod = signal(false);

  confidenceLabels = CONFIDENCE_LABELS;

  metricGroups(): string[] {
    return Array.from(new Set(this.metrics().map((m) => m.group)));
  }

  metricsInGroup(group: string): ChartMetric[] {
    return this.metrics().filter((m) => m.group === group);
  }

  async ngOnInit(): Promise<void> {
    this.metrics.set(await this.chartApi.listMetrics());
    await this.refresh();
  }

  async refresh(): Promise<void> {
    this.loading.set(true);
    this.errorMessage.set('');
    try {
      this.companies.set(await this.peerApi.listCompanies());
    } catch {
      this.errorMessage.set('Could not load peer companies.');
    } finally {
      this.loading.set(false);
    }
  }

  openAddCompany(): void {
    this.showAddCompany.set(true);
    this.newCompanyName.set('');
    this.newCompanyIndustry.set('');
    this.newCompanyCountry.set('');
  }

  async saveCompany(): Promise<void> {
    if (!this.newCompanyName().trim()) return;
    try {
      await this.peerApi.createCompany({
        name: this.newCompanyName().trim(),
        industry: this.newCompanyIndustry().trim() || null,
        country: this.newCompanyCountry().trim() || null
      });
      this.showAddCompany.set(false);
      this.successMessage.set('Peer company added.');
      await this.refresh();
    } catch (err: any) {
      this.errorMessage.set(err?.error?.detail ?? 'Could not add this peer company.');
    }
  }

  async deleteCompany(company: PeerCompany): Promise<void> {
    try {
      await this.peerApi.deleteCompany(company.id);
      if (this.expandedCompanyId() === company.id) this.expandedCompanyId.set(null);
      this.successMessage.set('Peer company removed.');
      await this.refresh();
    } catch {
      this.errorMessage.set('Could not remove this peer company.');
    }
  }

  async toggleExpand(company: PeerCompany): Promise<void> {
    if (this.expandedCompanyId() === company.id) {
      this.expandedCompanyId.set(null);
      return;
    }
    this.expandedCompanyId.set(company.id);
    this.showAddPeriod.set(false);
    this.dataLoading.set(true);
    try {
      this.companyData.set(await this.peerApi.listData(company.id));
    } finally {
      this.dataLoading.set(false);
    }
  }

  openAddPeriod(): void {
    this.showAddPeriod.set(true);
    this.periodValue.set(currentMonthValue());
    this.periodMetricValues.set({});
    this.dataSource.set('');
    this.sourceLink.set('');
    this.dataConfidence.set('self_reported');
    this.notes.set('');
  }

  setMetricValue(key: string, value: string): void {
    const values = { ...this.periodMetricValues() };
    values[key] = value === '' ? null : Number(value);
    this.periodMetricValues.set(values);
  }

  hasAnyMetricValue(): boolean {
    return Object.values(this.periodMetricValues()).some((v) => v !== null && v !== undefined);
  }

  async savePeriodData(): Promise<void> {
    const companyId = this.expandedCompanyId();
    if (!companyId || !this.hasAnyMetricValue()) return;
    this.submittingPeriod.set(true);
    this.errorMessage.set('');
    try {
      const metrics: Record<string, number> = {};
      for (const [key, value] of Object.entries(this.periodMetricValues())) {
        if (value !== null && value !== undefined) metrics[key] = value;
      }
      await this.peerApi.upsertData(companyId, {
        period: `${this.periodValue()}-01`,
        metrics,
        data_source: this.dataSource().trim() || null,
        source_link: this.sourceLink().trim() || null,
        data_confidence: this.dataConfidence() || null,
        notes: this.notes().trim() || null
      });
      this.showAddPeriod.set(false);
      this.successMessage.set('Peer data saved.');
      this.companyData.set(await this.peerApi.listData(companyId));
      await this.refresh();
    } catch (err: any) {
      this.errorMessage.set(err?.error?.detail ?? 'Could not save this period.');
    } finally {
      this.submittingPeriod.set(false);
    }
  }

  async deletePeriod(row: PeerData): Promise<void> {
    const companyId = this.expandedCompanyId();
    if (!companyId) return;
    try {
      await this.peerApi.deleteData(companyId, row.id);
      this.companyData.set(await this.peerApi.listData(companyId));
      await this.refresh();
    } catch {
      this.errorMessage.set('Could not delete this period.');
    }
  }

  metricLabel(key: string): string {
    return this.metrics().find((m) => m.key === key)?.label ?? key;
  }

  metricUnit(key: string): string {
    return this.metrics().find((m) => m.key === key)?.unit ?? '';
  }

  metricKeysFor(row: PeerData): string[] {
    return Object.keys(row.metrics);
  }

  formatPeriod(period: string): string {
    return new Date(`${period}T00:00:00`).toLocaleDateString('en-US', { month: 'long', year: 'numeric' });
  }
}
