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
  elapsed_seconds: number | null;
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

  /** Every peer company this tenant tracks -- not just the one
   * auto-provisioned default. Backs the multi-peer picker (up to 4 at
   * once): the comparison algorithm itself never changes per company,
   * only which company_id it's pointed at. */
  async listCompanies(): Promise<PeerCompany[]> {
    const headers = await this.authHeaders();
    return firstValueFrom(this.http.get<PeerCompany[]>(`${environment.apiBaseUrl}/peers`, { headers }));
  }

  async createCompany(payload: { name: string; industry: string | null; country: string | null }): Promise<PeerCompany> {
    const headers = await this.authHeaders();
    return firstValueFrom(this.http.post<PeerCompany>(`${environment.apiBaseUrl}/peers`, payload, { headers }));
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
  // The server-side work runs as a background job there too -- this just
  // starts it and polls, so there's no single long-held HTTP request for
  // a flaky connection or a proxy timeout to kill.
  //
  // Two distinct phases, tracked separately and never conflated: uploading
  // (the browser sending the file over the user's own connection -- for a
  // ~30MB BRSR PDF this can genuinely take 30-60+ seconds on an average
  // connection, and no backend fix changes that) and extracting (the
  // server actually reading it, which after a data-race with a bad
  // deploy is confirmed independently at ~10-15s). Showing one merged
  // "Reading report... Xs" timer across both made a slow home connection
  // look identical to a slow extraction, which it never was.
  uploading = signal(false);
  uploadProgressPct = signal(0);
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

  /** Returns the final result directly once the whole thing finishes (or
   * null on error/timeout) -- a caller still on the page can await this
   * and act immediately, rather than depending solely on a separate
   * effect() noticing the extracting()/extractResult() signals change
   * later, which is exactly the kind of two-signals-plus-a-phase-guard
   * timing that's fragile to get right. The signals are still updated
   * throughout (see pollJob/finishJob) so a caller that navigates away
   * and back still recovers state from them alone, same as before. */
  async startExtraction(companyId: string, file: File, year: number): Promise<PeerExtractResult | null> {
    this.uploading.set(true);
    this.uploadProgressPct.set(0);
    this.extracting.set(false);
    this.extractError.set('');
    this.extractResult.set(null);
    this.extractFileName.set(file.name);

    try {
      const { data } = await this.supabase.client.auth.getSession();
      const form = new FormData();
      form.append('file', file);
      form.append('year', String(year));
      const job = await this.uploadWithProgress(companyId, form, data.session?.access_token ?? '');

      this.uploading.set(false);
      this.extracting.set(true);
      const startedAt = Date.now(); // processing timer starts once the upload itself is done
      this.startElapsedTimer(startedAt);

      const stored: StoredExtractJob = { jobId: job.job_id, companyId, fileName: file.name, startedAt };
      localStorage.setItem(EXTRACT_JOB_STORAGE_KEY, JSON.stringify(stored));
      return await this.pollJob(companyId, job.job_id);
    } catch (err: any) {
      this.uploading.set(false);
      this.extractError.set(err?.message ?? 'Could not read this PDF.');
      this.finishJob();
      return null;
    }
  }

  /** fetch() doesn't expose upload progress -- XMLHttpRequest is the only
   * browser API that does, needed here specifically because a ~30MB PDF's
   * upload time is the dominant, user-visible cost on an average
   * connection, and showing nothing for 30-60s reads as broken. */
  private uploadWithProgress(companyId: string, form: FormData, token: string): Promise<PeerExtractJob> {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open('POST', `${environment.apiBaseUrl}/peers/${companyId}/extract`);
      xhr.setRequestHeader('Authorization', `Bearer ${token}`);
      xhr.upload.onprogress = (event) => {
        if (event.lengthComputable) {
          this.uploadProgressPct.set(Math.round((event.loaded / event.total) * 100));
        }
      };
      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          try {
            resolve(JSON.parse(xhr.responseText));
          } catch {
            reject(new Error('Unexpected response from the server.'));
          }
          return;
        }
        let detail = 'Could not extract this PDF.';
        try {
          detail = JSON.parse(xhr.responseText)?.detail ?? detail;
        } catch {
          // response wasn't JSON -- keep the default message
        }
        reject(new Error(detail));
      };
      xhr.onerror = () => reject(new Error('Upload failed — check your connection and try again.'));
      xhr.send(form);
    });
  }

  /** Resolves once the job reaches done/error/gives-up -- with the result
   * (or null). Callers that are still on the page can `await` this
   * directly instead of relying purely on the signals + a separate
   * effect() to notice the state changed later; a caller that navigates
   * away doesn't need the promise at all since the signals themselves
   * (extracting/extractResult) already carry the state independently. */
  private pollJob(companyId: string, jobId: string): Promise<PeerExtractResult | null> {
    if (this.pollTimer) clearInterval(this.pollTimer);
    return new Promise((resolve) => {
      let consecutiveFailures = 0;
      // A single poll can fail transiently (a network blip, a momentary
      // 5xx during a backend redeploy) -- giving up on the very first
      // failed poll turned a one-off hiccup into "extraction silently
      // abandoned, no error shown, no result, just stuck". Tolerate a few
      // in a row (the job itself is unaffected server-side either way)
      // before actually surfacing an error.
      const MAX_CONSECUTIVE_FAILURES = 5;
      const check = async () => {
        try {
          const headers = await this.authHeaders();
          const job = await firstValueFrom(
            this.http.get<PeerExtractJob>(`${environment.apiBaseUrl}/peers/${companyId}/extract/${jobId}`, { headers })
          );
          consecutiveFailures = 0;
          if (job.status === 'done') {
            console.info('[peer-extraction] job done', jobId, job.result);
            this.extractResult.set(job.result ?? null);
            this.finishJob();
            resolve(job.result ?? null);
          } else if (job.status === 'error') {
            console.warn('[peer-extraction] job error', jobId, job.error);
            this.extractError.set(job.error ?? 'Could not read this PDF.');
            this.finishJob();
            resolve(null);
          }
          // "processing" -- keep polling, the interval below will fire again
        } catch (err) {
          consecutiveFailures++;
          console.warn(`[peer-extraction] poll failed (${consecutiveFailures}/${MAX_CONSECUTIVE_FAILURES})`, jobId, err);
          if (consecutiveFailures < MAX_CONSECUTIVE_FAILURES) return; // try again on the next tick
          this.extractError.set('Lost track of the extraction job — please try uploading again.');
          this.finishJob();
          resolve(null);
        }
      };
      void check();
      this.pollTimer = setInterval(check, 4000);
    });
  }

  private finishJob(): void {
    this.uploading.set(false);
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
    this.uploadProgressPct.set(0);
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
