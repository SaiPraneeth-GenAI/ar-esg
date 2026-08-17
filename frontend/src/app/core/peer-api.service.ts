import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
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

@Injectable({ providedIn: 'root' })
export class PeerApiService {
  private http = inject(HttpClient);
  private supabase = inject(SupabaseService);

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

  async extractPdf(companyId: string, file: File, year: number): Promise<PeerExtractResult> {
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
    return response.json();
  }

  async compareYear(companyId: string, year: number): Promise<PeerCompareYearResult> {
    const headers = await this.authHeaders();
    return firstValueFrom(
      this.http.get<PeerCompareYearResult>(`${environment.apiBaseUrl}/peers/${companyId}/compare-year`, { headers, params: { year } })
    );
  }
}
