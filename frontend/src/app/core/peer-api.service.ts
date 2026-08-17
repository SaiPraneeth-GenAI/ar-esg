import { HttpClient } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../environments/environment';
import { SupabaseService } from './supabase.service';

export interface PeerCompany {
  id: string;
  name: string;
  industry: string | null;
  country: string | null;
  created_at: string;
  period_count: number;
}

export interface PeerData {
  id: string;
  peer_company_id: string;
  period: string;
  metrics: Record<string, number>;
  data_source: string | null;
  source_link: string | null;
  data_confidence: string | null;
  notes: string | null;
  uploaded_by_email: string | null;
  uploaded_at: string;
  updated_at: string;
}

export interface PeerDataCreate {
  period: string;
  metrics: Record<string, number>;
  data_source: string | null;
  source_link: string | null;
  data_confidence: string | null;
  notes: string | null;
}

export interface PeerExtractRow {
  key: string;
  label: string;
  unit: string;
  group: string;
  amara_raja_value: number | null;
  peer_value: number | null;
}

export interface PeerExtractResult {
  peer_company_id: string;
  peer_company_name: string;
  year: number;
  source_filename: string;
  rows: PeerExtractRow[];
}

export interface PeerCompareYearMetric {
  key: string;
  label: string;
  unit: string;
  amara_raja_value: number | null;
  peer_value: number | null;
}

export interface PeerCompareYearGroup {
  group: string;
  metrics: PeerCompareYearMetric[];
}

export interface PeerCompareYearResult {
  year: number;
  peer_company_name: string;
  groups: PeerCompareYearGroup[];
}

interface PeerExtractJob {
  job_id: string;
  status: 'processing' | 'done' | 'error';
  result?: PeerExtractResult;
  error?: string;
}

interface StoredExtractJob {
  jobId: string;
  companyId: string;
  fileName: string;
  startedAt: number;
}

// A page reload (not just navigating to another in-app tab) would otherwise
// lose track of an in-flight extraction, even though the server keeps
// working on it -- persisting the job id here lets a fresh page load pick
// polling back up instead of leaving the user with no way to see the result.
const EXTRACT_JOB_STORAGE_KEY = 'enviqo_peer_extract_job';

@Injectable({ providedIn: 'root' })
export class PeerApiService {
  private http = inject(HttpClient);
  private supabase = inject(SupabaseService);

  constructor() {
    this.resumePendingExtraction();
  }

  private async authHeaders(): Promise<{ Authorization: string }> {
    const { data } = await this.supabase.client.auth.getSession();
    return { Authorization: `Bearer ${data.session?.access_token ?? ''}` };
  }

  async getDefaultCompany(): Promise<PeerCompany> {
    const headers = await this.authHeaders();
    return firstValueFrom(this.http.get<PeerCompany>(`${environment.apiBaseUrl}/peers/default-company`, { headers }));
  }

  async listData(companyId: string): Promise<PeerData[]> {
    const headers = await this.authHeaders();
    return firstValueFrom(this.http.get<PeerData[]>(`${environment.apiBaseUrl}/peers/${companyId}/data`, { headers }));
  }

  async upsertData(companyId: string, payload: PeerDataCreate): Promise<PeerData> {
    const headers = await this.authHeaders();
    return firstValueFrom(this.http.post<PeerData>(`${environment.apiBaseUrl}/peers/${companyId}/data`, payload, { headers }));
  }

  async deleteData(companyId: string, dataId: string): Promise<void> {
    const headers = await this.authHeaders();
    await firstValueFrom(this.http.delete<void>(`${environment.apiBaseUrl}/peers/${companyId}/data/${dataId}`, { headers }));
  }

  // Extraction state lives here (a root-provided singleton), not on the
  // component, so it survives the user navigating to another tab and back.
  // The server-side work (rendering ~8 pages and a vision AI call) runs as
  // a background job there too -- this just starts it and polls, so
  // there's no single long-held HTTP request for a flaky connection or a
  // proxy timeout to kill.
  extracting = signal(false);
  extractError = signal('');
  extractResult = signal<PeerExtractResult | null>(null);
  extractFileName = signal('');
  extractElapsedSeconds = signal(0);
  private extractTimer: ReturnType<typeof setInterval> | null = null;
  private pollTimer: ReturnType<typeof setInterval> | null = null;

  private resumePendingExtraction(): void {
    const raw = localStorage.getItem(EXTRACT_JOB_STORAGE_KEY);
    if (!raw) return;
    try {
      const stored: StoredExtractJob = JSON.parse(raw);
      this.extracting.set(true);
      this.extractError.set('');
      this.extractFileName.set(stored.fileName);
      this.startElapsedTimer(stored.startedAt);
      this.pollJob(stored.companyId, stored.jobId);
    } catch {
      localStorage.removeItem(EXTRACT_JOB_STORAGE_KEY);
    }
  }

  private startElapsedTimer(startedAt: number): void {
    if (this.extractTimer) clearInterval(this.extractTimer);
    this.extractElapsedSeconds.set(Math.floor((Date.now() - startedAt) / 1000));
    this.extractTimer = setInterval(() => this.extractElapsedSeconds.set(Math.floor((Date.now() - startedAt) / 1000)), 1000);
  }

  async startExtraction(companyId: string, file: File, year: number): Promise<void> {
    this.extracting.set(true);
    this.extractError.set('');
    this.extractResult.set(null);
    this.extractFileName.set(file.name);
    const startedAt = Date.now();
    this.startElapsedTimer(startedAt);

    try {
      const { data } = await this.supabase.client.auth.getSession();
      const form = new FormData();
      form.append('file', file);
      form.append('year', String(year));
      const response = await fetch(`${environment.apiBaseUrl}/peers/${companyId}/extract`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${data.session?.access_token ?? ''}` },
        body: form
      });
      if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(body?.detail ?? 'Could not extract this PDF.');
      }
      const job: PeerExtractJob = await response.json();
      const stored: StoredExtractJob = { jobId: job.job_id, companyId, fileName: file.name, startedAt };
      localStorage.setItem(EXTRACT_JOB_STORAGE_KEY, JSON.stringify(stored));
      this.pollJob(companyId, job.job_id);
    } catch (err: any) {
      this.extractError.set(err?.message ?? 'Could not read this PDF.');
      this.finishJob();
    }
  }

  private pollJob(companyId: string, jobId: string): void {
    if (this.pollTimer) clearInterval(this.pollTimer);
    const check = async () => {
      try {
        const headers = await this.authHeaders();
        const job = await firstValueFrom(
          this.http.get<PeerExtractJob>(`${environment.apiBaseUrl}/peers/${companyId}/extract/${jobId}`, { headers })
        );
        if (job.status === 'done') {
          this.extractResult.set(job.result ?? null);
          this.finishJob();
        } else if (job.status === 'error') {
          this.extractError.set(job.error ?? 'Could not read this PDF.');
          this.finishJob();
        }
        // "processing" -- keep polling, the interval below will fire again
      } catch {
        this.extractError.set('Lost track of the extraction job -- please try uploading again.');
        this.finishJob();
      }
    };
    void check();
    this.pollTimer = setInterval(check, 4000);
  }

  private finishJob(): void {
    this.extracting.set(false);
    if (this.extractTimer) {
      clearInterval(this.extractTimer);
      this.extractTimer = null;
    }
    if (this.pollTimer) {
      clearInterval(this.pollTimer);
      this.pollTimer = null;
    }
    localStorage.removeItem(EXTRACT_JOB_STORAGE_KEY);
  }

  clearExtraction(): void {
    this.finishJob();
    this.extractError.set('');
    this.extractResult.set(null);
    this.extractFileName.set('');
    this.extractElapsedSeconds.set(0);
  }

  // Comparison results are cached by year once built (either fetched or
  // assembled straight from a just-confirmed save) so revisiting a year
  // -- including after navigating away and back -- reads from memory
  // instead of re-hitting the server, until a re-upload invalidates it.
  private compareCache = new Map<string, PeerCompareYearResult>();

  private compareCacheKey(companyId: string, year: number): string {
    return `${companyId}:${year}`;
  }

  async compareYear(companyId: string, year: number): Promise<PeerCompareYearResult> {
    const key = this.compareCacheKey(companyId, year);
    const cached = this.compareCache.get(key);
    if (cached) return cached;

    const headers = await this.authHeaders();
    const result = await firstValueFrom(
      this.http.get<PeerCompareYearResult>(`${environment.apiBaseUrl}/peers/${companyId}/compare-year`, { headers, params: { year } })
    );
    this.compareCache.set(key, result);
    return result;
  }

  setCachedCompare(companyId: string, year: number, result: PeerCompareYearResult): void {
    this.compareCache.set(this.compareCacheKey(companyId, year), result);
  }

  invalidateCompare(companyId: string, year: number): void {
    this.compareCache.delete(this.compareCacheKey(companyId, year));
  }
}
