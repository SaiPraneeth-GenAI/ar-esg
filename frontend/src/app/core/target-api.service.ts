import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../environments/environment';
import { SupabaseService } from './supabase.service';

export type TargetStatus = 'draft' | 'active' | 'archived';

export interface MonthlyPhaseEntry {
  period: string;
  value: number;
}

export interface TargetableMetric {
  key: string;
  label: string;
  unit: string;
  group: string;
  aggregation: 'budget' | 'rate';
  direction: 'lower' | 'higher';
}

export interface BaselinePreviewRequest {
  location_id?: string | null;
  metric_key: string;
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
  metric_key: string;
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
  metric_key: string;
  metric_label: string;
  metric_unit: string;
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
  metric_key: string;
  months: TargetMonthPerformance[];
}

export interface TargetBulkRowIn {
  row_index: number;
  metric_key: string;
  location_name?: string | null;
  baseline_period_start: string;
  baseline_period_end: string;
  target_period_start: string;
  target_period_end: string;
  reduction_percentage?: number | null;
  target_value?: number | null;
  rationale?: string | null;
}

export interface TargetBulkImportRequest {
  commit: boolean;
  rows: TargetBulkRowIn[];
}

export interface TargetBulkRowResult {
  row_index: number;
  status: 'valid' | 'error' | 'created' | 'activated';
  metric_key: string;
  message: string | null;
  target_id: string | null;
}

export interface TargetBulkImportResponse {
  rows: TargetBulkRowResult[];
  activated_count: number;
  error_count: number;
}

@Injectable({ providedIn: 'root' })
export class TargetApiService {
  private http = inject(HttpClient);
  private supabase = inject(SupabaseService);

  private async authHeaders(): Promise<{ Authorization: string }> {
    const { data } = await this.supabase.client.auth.getSession();
    return { Authorization: `Bearer ${data.session?.access_token ?? ''}` };
  }

  async listMetrics(): Promise<TargetableMetric[]> {
    const headers = await this.authHeaders();
    return firstValueFrom(this.http.get<TargetableMetric[]>(`${environment.apiBaseUrl}/targets/metrics`, { headers }));
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

  async activate(id: string): Promise<TargetOut> {
    const headers = await this.authHeaders();
    return firstValueFrom(
      this.http.post<TargetOut>(`${environment.apiBaseUrl}/targets/${id}/activate`, {}, { headers })
    );
  }

  async bulkImport(payload: TargetBulkImportRequest): Promise<TargetBulkImportResponse> {
    const headers = await this.authHeaders();
    return firstValueFrom(
      this.http.post<TargetBulkImportResponse>(`${environment.apiBaseUrl}/targets/bulk-import`, payload, { headers })
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
