import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../environments/environment';
import { PeriodMode } from './intensity-api.service';
import { SupabaseService } from './supabase.service';

export interface PeerCompany {
  id: string;
  name: string;
  industry: string | null;
  country: string | null;
  created_at: string;
  period_count: number;
}

export interface PeerCompanyCreate {
  name: string;
  industry: string | null;
  country: string | null;
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

export interface PeerCompareEntry {
  name: string;
  is_self: boolean;
  value: number | null;
  period: string | null;
}

export interface PeerCompareData {
  metric: string;
  label: string;
  unit: string;
  period: string;
  entries: PeerCompareEntry[];
}

@Injectable({ providedIn: 'root' })
export class PeerApiService {
  private http = inject(HttpClient);
  private supabase = inject(SupabaseService);

  private async authHeaders(): Promise<{ Authorization: string }> {
    const { data } = await this.supabase.client.auth.getSession();
    return { Authorization: `Bearer ${data.session?.access_token ?? ''}` };
  }

  async listCompanies(): Promise<PeerCompany[]> {
    const headers = await this.authHeaders();
    return firstValueFrom(this.http.get<PeerCompany[]>(`${environment.apiBaseUrl}/peers`, { headers }));
  }

  async createCompany(payload: PeerCompanyCreate): Promise<PeerCompany> {
    const headers = await this.authHeaders();
    return firstValueFrom(this.http.post<PeerCompany>(`${environment.apiBaseUrl}/peers`, payload, { headers }));
  }

  async deleteCompany(id: string): Promise<void> {
    const headers = await this.authHeaders();
    await firstValueFrom(this.http.delete<void>(`${environment.apiBaseUrl}/peers/${id}`, { headers }));
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

  async compare(metric: string, period: string, periodMode: PeriodMode, peerIds: string[], locationId?: string): Promise<PeerCompareData> {
    const headers = await this.authHeaders();
    const params: Record<string, string> = { metric, period, period_mode: periodMode, peer_ids: peerIds.join(',') };
    if (locationId) params['location_id'] = locationId;
    return firstValueFrom(this.http.get<PeerCompareData>(`${environment.apiBaseUrl}/peers/compare`, { headers, params }));
  }
}
