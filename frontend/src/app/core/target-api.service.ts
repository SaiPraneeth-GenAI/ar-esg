import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../environments/environment';
import { SupabaseService } from './supabase.service';

export type TargetScope = '1' | '2' | '1_2_combined';
export type TargetMetricType = 'absolute_tco2e' | 'intensity_tco2e_per_mnah' | 'intensity_tco2e_per_revenue';
export type TargetStatus = 'draft' | 'active' | 'archived';

export interface MonthlyPhaseEntry {
  period: string;
  value: number;
}

export interface BaselinePreviewRequest {
  location_id?: string | null;
  scope: TargetScope;
  calculation_method?: string | null;
  metric_type: TargetMetricType;
  baseline_period_start: string;
  baseline_period_end: string;
}

export interface BaselineMonthOut {
  period: string;
  value: number | null;
  completeness_pct: number | null;
}

export interface BaselinePreviewResponse {
  ready: boolean;
  provisional: boolean;
  baseline_value: number | null;
  completeness_pct: number | null;
  message: string;
  months: BaselineMonthOut[];
}

export interface TargetCreate {
  location_id?: string | null;
  scope: TargetScope;
  calculation_method?: string | null;
  metric_type: TargetMetricType;
  baseline_period_start: string;
  baseline_period_end: string;
  target_period_start: string;
  target_period_end: string;
  reduction_percentage?: number | null;
  target_value?: number | null;
  monthly_phasing?: MonthlyPhaseEntry[];
  owner_id?: string | null;
  rationale?: string | null;
}

export type TargetUpdate = Partial<TargetCreate>;

export interface TargetOut {
  id: string;
  location_id: string | null;
  location_name: string | null;
  scope: TargetScope;
  calculation_method: string | null;
  metric_type: TargetMetricType;
  baseline_period_start: string;
  baseline_period_end: string;
  baseline_value: number | null;
  baseline_completeness_pct: number | null;
  baseline_locked_at: string | null;
  reduction_percentage: number | null;
  target_period_start: string;
  target_period_end: string;
  target_value: number | null;
  monthly_phasing: MonthlyPhaseEntry[];
  status: TargetStatus;
  owner_id: string | null;
  owner_email: string | null;
  rationale: string | null;
  approved_by: string | null;
  approved_by_email: string | null;
  approved_at: string | null;
  boundary_config_hash: string | null;
  created_at: string;
  updated_at: string;
  current_status_label: string | null;
}

export interface TargetMonthPerformance {
  period: string;
  actual: number | null;
  target: number | null;
  variance_pct: number | null;
  status: string;
  completeness_pct: number | null;
}

export interface TargetPerformanceResponse {
  target_id: string;
  metric_type: TargetMetricType;
  months: TargetMonthPerformance[];
}

@Injectable({ providedIn: 'root' })
export class TargetApiService {
  private http = inject(HttpClient);
  private supabase = inject(SupabaseService);

  private async authHeaders(): Promise<{ Authorization: string }> {
    const { data } = await this.supabase.client.auth.getSession();
    return { Authorization: `Bearer ${data.session?.access_token ?? ''}` };
  }

  async baselinePreview(payload: BaselinePreviewRequest): Promise<BaselinePreviewResponse> {
    const headers = await this.authHeaders();
    return firstValueFrom(
      this.http.post<BaselinePreviewResponse>(`${environment.apiBaseUrl}/targets/baseline-preview`, payload, { headers })
    );
  }

  async create(payload: TargetCreate): Promise<TargetOut> {
    const headers = await this.authHeaders();
    return firstValueFrom(this.http.post<TargetOut>(`${environment.apiBaseUrl}/targets`, payload, { headers }));
  }

  async list(status?: TargetStatus): Promise<TargetOut[]> {
    const headers = await this.authHeaders();
    const params: Record<string, string> = {};
    if (status) params['status'] = status;
    return firstValueFrom(this.http.get<TargetOut[]>(`${environment.apiBaseUrl}/targets`, { headers, params }));
  }

  async get(id: string): Promise<TargetOut> {
    const headers = await this.authHeaders();
    return firstValueFrom(this.http.get<TargetOut>(`${environment.apiBaseUrl}/targets/${id}`, { headers }));
  }

  async update(id: string, payload: TargetUpdate): Promise<TargetOut> {
    const headers = await this.authHeaders();
    return firstValueFrom(this.http.patch<TargetOut>(`${environment.apiBaseUrl}/targets/${id}`, payload, { headers }));
  }

  async remove(id: string): Promise<void> {
    const headers = await this.authHeaders();
    await firstValueFrom(this.http.delete<void>(`${environment.apiBaseUrl}/targets/${id}`, { headers }));
  }

  async activate(id: string, rationale: string): Promise<TargetOut> {
    const headers = await this.authHeaders();
    return firstValueFrom(
      this.http.post<TargetOut>(`${environment.apiBaseUrl}/targets/${id}/activate`, { rationale }, { headers })
    );
  }

  async archive(id: string): Promise<TargetOut> {
    const headers = await this.authHeaders();
    return firstValueFrom(this.http.post<TargetOut>(`${environment.apiBaseUrl}/targets/${id}/archive`, {}, { headers }));
  }

  async restore(id: string): Promise<TargetOut> {
    const headers = await this.authHeaders();
    return firstValueFrom(this.http.post<TargetOut>(`${environment.apiBaseUrl}/targets/${id}/restore`, {}, { headers }));
  }

  async performance(id: string): Promise<TargetPerformanceResponse> {
    const headers = await this.authHeaders();
    return firstValueFrom(this.http.get<TargetPerformanceResponse>(`${environment.apiBaseUrl}/targets/${id}/performance`, { headers }));
  }
}
