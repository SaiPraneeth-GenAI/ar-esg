import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../environments/environment';
import { PeriodMode } from './intensity-api.service';
import { SupabaseService } from './supabase.service';

export interface ChartMetric {
  key: string;
  label: string;
  unit: string;
  group: string;
}

export interface ChartMetricPoint {
  period: string;
  bucket_start: string | null;
  bucket_end: string | null;
  value: number | null;
  prior_year_value: number | null;
}

export interface ChartMetricData {
  metric: string;
  label: string;
  unit: string;
  period_mode: PeriodMode;
  points: ChartMetricPoint[];
}

export type QuestionType = 'trend' | 'breakdown' | 'comparison';

export interface BreakdownDimension {
  key: string;
  label: string;
}

export interface BreakdownSlice {
  label: string;
  value: number;
}

export interface BreakdownData {
  dimension: string;
  label: string;
  unit: string;
  period_mode: PeriodMode;
  slices: BreakdownSlice[];
}

export interface ChartConfig {
  question_type: QuestionType;
  // trend
  metric: string | null;
  chart_kind: 'bar' | 'line';
  period_mode: PeriodMode;
  months: number;
  // breakdown
  dimension: string | null;
  // comparison
  metrics: string[] | null;
  location_id: string | null;
}

export interface SavedChart {
  id: string;
  name: string;
  description: string | null;
  config: ChartConfig;
  owner_id: string;
  owner_email: string | null;
  created_at: string;
  updated_at: string;
}

export interface SavedChartCreate {
  name: string;
  description: string | null;
  config: ChartConfig;
}

@Injectable({ providedIn: 'root' })
export class ChartApiService {
  private http = inject(HttpClient);
  private supabase = inject(SupabaseService);

  private async authHeaders(): Promise<{ Authorization: string }> {
    const { data } = await this.supabase.client.auth.getSession();
    return { Authorization: `Bearer ${data.session?.access_token ?? ''}` };
  }

  async listMetrics(): Promise<ChartMetric[]> {
    const headers = await this.authHeaders();
    return firstValueFrom(this.http.get<ChartMetric[]>(`${environment.apiBaseUrl}/charts/metrics`, { headers }));
  }

  async getMetricData(metric: string, period: string, periodMode: PeriodMode, months: number, locationId?: string): Promise<ChartMetricData> {
    const headers = await this.authHeaders();
    const params: Record<string, string> = { metric, period, period_mode: periodMode, months: String(months) };
    if (locationId) params['location_id'] = locationId;
    return firstValueFrom(this.http.get<ChartMetricData>(`${environment.apiBaseUrl}/charts/metric-data`, { headers, params }));
  }

  async listBreakdownDimensions(): Promise<BreakdownDimension[]> {
    const headers = await this.authHeaders();
    return firstValueFrom(this.http.get<BreakdownDimension[]>(`${environment.apiBaseUrl}/charts/breakdown-dimensions`, { headers }));
  }

  async getBreakdownData(dimension: string, period: string, periodMode: PeriodMode, locationId?: string): Promise<BreakdownData> {
    const headers = await this.authHeaders();
    const params: Record<string, string> = { dimension, period, period_mode: periodMode };
    if (locationId) params['location_id'] = locationId;
    return firstValueFrom(this.http.get<BreakdownData>(`${environment.apiBaseUrl}/charts/breakdown-data`, { headers, params }));
  }

  async list(): Promise<SavedChart[]> {
    const headers = await this.authHeaders();
    return firstValueFrom(this.http.get<SavedChart[]>(`${environment.apiBaseUrl}/charts`, { headers }));
  }

  async create(payload: SavedChartCreate): Promise<SavedChart> {
    const headers = await this.authHeaders();
    return firstValueFrom(this.http.post<SavedChart>(`${environment.apiBaseUrl}/charts`, payload, { headers }));
  }

  async update(id: string, payload: Partial<SavedChartCreate>): Promise<SavedChart> {
    const headers = await this.authHeaders();
    return firstValueFrom(this.http.put<SavedChart>(`${environment.apiBaseUrl}/charts/${id}`, payload, { headers }));
  }

  async remove(id: string): Promise<void> {
    const headers = await this.authHeaders();
    await firstValueFrom(this.http.delete<void>(`${environment.apiBaseUrl}/charts/${id}`, { headers }));
  }
}
