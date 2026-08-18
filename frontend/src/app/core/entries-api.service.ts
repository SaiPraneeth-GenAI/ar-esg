import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../environments/environment';
import { SupabaseService } from './supabase.service';

export interface DataPoint {
  id: string;
  name: string;
  unit: string | null;
  input_type: string | null;
  is_provisional: boolean;
  tooltip: string | null;
  example: string | null;
}

export interface EntryCategory {
  id: string;
  name: string;
  display_order: number | null;
  is_provisional: boolean;
  data_points: DataPoint[];
}

export interface EntryRecord {
  id: string;
  data_point_id: string;
  data_point_name: string;
  category_name: string;
  location_id: string;
  location_name: string;
  period: string;
  value: number | null;
  status: string;
  note: string | null;
  submitted_by: string | null;
  submitted_by_email: string | null;
  latest_rejection_note: string | null;
}

export interface LastValue {
  value: number | null;
  period: string | null;
}

export interface LastValueEntry {
  data_point_id: string;
  value: number | null;
  period: string | null;
}

export interface EntryUpsert {
  data_point_id: string;
  location_id: string;
  period: string;
  value: number | null;
  note?: string | null;
  meter_id?: string | null;
}

export interface AuditEntry {
  id: string;
  actor: string | null;
  action: string;
  old_value: string | null;
  new_value: string | null;
  timestamp: string;
}

export interface AttachmentRecord {
  id: string;
  file_url: string;
  file_type: string | null;
  uploaded_by: string | null;
  uploaded_at: string;
}

export interface BulkImportRowIn {
  row_index: number;
  category?: string | null;
  data_point_name: string;
  period_iso: string;
  value_raw: string;
  unit_raw?: string | null;
  note?: string | null;
}

export interface BulkImportRowResult {
  row_index: number;
  status: 'valid' | 'error' | 'created';
  data_point_name: string;
  period: string | null;
  value: number | null;
  message: string | null;
  entry_id: string | null;
  unit_note: string | null;
  suggested_unit: string | null;
  category: string | null;
}

export interface BulkImportResponse {
  rows: BulkImportRowResult[];
  valid_count: number;
  error_count: number;
  created_count: number;
}

export interface BulkDecisionSkip {
  entry_id: string;
  reason: string;
}

export interface BulkDecisionResponse {
  processed_count: number;
  skipped: BulkDecisionSkip[];
}

@Injectable({ providedIn: 'root' })
export class EntriesApiService {
  private http = inject(HttpClient);
  private supabase = inject(SupabaseService);

  private async authHeaders(): Promise<{ Authorization: string }> {
    const { data } = await this.supabase.client.auth.getSession();
    return { Authorization: `Bearer ${data.session?.access_token ?? ''}` };
  }

  async listCategories(): Promise<EntryCategory[]> {
    const headers = await this.authHeaders();
    return firstValueFrom(this.http.get<EntryCategory[]>(`${environment.apiBaseUrl}/entries/categories`, { headers }));
  }

  async getLastValuesBatch(category: string, locationId: string, beforePeriod: string): Promise<LastValueEntry[]> {
    const headers = await this.authHeaders();
    return firstValueFrom(
      this.http.get<LastValueEntry[]>(`${environment.apiBaseUrl}/entries/last-values`, {
        headers,
        params: { category, location_id: locationId, before_period: beforePeriod }
      })
    );
  }

  async getCurrentEntries(category: string, period: string, locationId: string): Promise<EntryRecord[]> {
    const headers = await this.authHeaders();
    return firstValueFrom(
      this.http.get<EntryRecord[]>(`${environment.apiBaseUrl}/entries/current`, {
        headers,
        params: { category, period, location_id: locationId }
      })
    );
  }

  async saveDrafts(items: EntryUpsert[]): Promise<EntryRecord[]> {
    const headers = await this.authHeaders();
    return firstValueFrom(this.http.post<EntryRecord[]>(`${environment.apiBaseUrl}/entries`, items, { headers }));
  }

  async submit(category: string, period: string, locationId: string): Promise<EntryRecord[]> {
    const headers = await this.authHeaders();
    return firstValueFrom(
      this.http.post<EntryRecord[]>(
        `${environment.apiBaseUrl}/entries/submit`,
        { category, period, location_id: locationId },
        { headers }
      )
    );
  }

  async getQueue(): Promise<EntryRecord[]> {
    const headers = await this.authHeaders();
    return firstValueFrom(this.http.get<EntryRecord[]>(`${environment.apiBaseUrl}/entries/queue`, { headers }));
  }

  async approve(entryId: string): Promise<EntryRecord> {
    const headers = await this.authHeaders();
    return firstValueFrom(
      this.http.post<EntryRecord>(`${environment.apiBaseUrl}/entries/${entryId}/approve`, {}, { headers })
    );
  }

  async reject(entryId: string, rejectNote: string): Promise<EntryRecord> {
    const headers = await this.authHeaders();
    return firstValueFrom(
      this.http.post<EntryRecord>(
        `${environment.apiBaseUrl}/entries/${entryId}/reject`,
        { reject_note: rejectNote },
        { headers }
      )
    );
  }

  async bulkApprove(entryIds: string[]): Promise<BulkDecisionResponse> {
    const headers = await this.authHeaders();
    return firstValueFrom(
      this.http.post<BulkDecisionResponse>(
        `${environment.apiBaseUrl}/entries/bulk-approve`,
        { entry_ids: entryIds },
        { headers }
      )
    );
  }

  async bulkReject(entryIds: string[], rejectNote: string): Promise<BulkDecisionResponse> {
    const headers = await this.authHeaders();
    return firstValueFrom(
      this.http.post<BulkDecisionResponse>(
        `${environment.apiBaseUrl}/entries/bulk-reject`,
        { entry_ids: entryIds, reject_note: rejectNote },
        { headers }
      )
    );
  }

  async getHistory(entryId: string): Promise<AuditEntry[]> {
    const headers = await this.authHeaders();
    return firstValueFrom(this.http.get<AuditEntry[]>(`${environment.apiBaseUrl}/entries/${entryId}/history`, { headers }));
  }

  async listAttachments(entryId: string): Promise<AttachmentRecord[]> {
    const headers = await this.authHeaders();
    return firstValueFrom(
      this.http.get<AttachmentRecord[]>(`${environment.apiBaseUrl}/entries/${entryId}/attachments`, { headers })
    );
  }

  async downloadCsvTemplate(category: string | null): Promise<void> {
    const { data } = await this.supabase.client.auth.getSession();
    const params = category ? `?${new URLSearchParams({ category })}` : '';
    const response = await fetch(`${environment.apiBaseUrl}/entries/csv-template${params}`, {
      headers: { Authorization: `Bearer ${data.session?.access_token ?? ''}` }
    });
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = category ? `${category.replace(/\s+/g, '_')}_template.csv` : 'all_categories_template.csv';
    link.click();
    URL.revokeObjectURL(url);
  }

  async bulkImport(
    category: string | null,
    locationId: string,
    rows: BulkImportRowIn[],
    commit: boolean,
    defaultPeriod?: string
  ): Promise<BulkImportResponse> {
    const headers = await this.authHeaders();
    return firstValueFrom(
      this.http.post<BulkImportResponse>(
        `${environment.apiBaseUrl}/entries/bulk-import`,
        { category, location_id: locationId, commit, rows, default_period: defaultPeriod ?? null },
        { headers }
      )
    );
  }

  async uploadAttachment(entryId: string, file: File): Promise<AttachmentRecord> {
    const { data } = await this.supabase.client.auth.getSession();
    const form = new FormData();
    form.append('file', file);
    return firstValueFrom(
      this.http.post<AttachmentRecord>(`${environment.apiBaseUrl}/entries/${entryId}/attachments`, form, {
        headers: { Authorization: `Bearer ${data.session?.access_token ?? ''}` }
      })
    );
  }
}
