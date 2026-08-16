import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../environments/environment';
import { PeriodMode } from './intensity-api.service';
import { SupabaseService } from './supabase.service';

export interface SafetyMetric {
  name: string;
  value: number | null;
  unit: string;
  prior_value: number | null;
  prior_year_value: number | null;
}

export interface SafetyOverview {
  period: string;
  period_mode: PeriodMode;
  period_start: string | null;
  period_end: string | null;
  metrics: SafetyMetric[];
}

export interface SafetyTrendPoint {
  period: string;
  bucket_start: string | null;
  bucket_end: string | null;
  values: Record<string, number | null>;
  prior_year_values: Record<string, number | null>;
}

@Injectable({ providedIn: 'root' })
export class SafetyApiService {
  private http = inject(HttpClient);
  private supabase = inject(SupabaseService);

  private async authHeaders(): Promise<{ Authorization: string }> {
    const { data } = await this.supabase.client.auth.getSession();
    return { Authorization: `Bearer ${data.session?.access_token ?? ''}` };
  }

  async getOverview(period: string, locationId?: string, periodMode: PeriodMode = 'month'): Promise<SafetyOverview> {
    const headers = await this.authHeaders();
    const params: Record<string, string> = { period, period_mode: periodMode };
    if (locationId) params['location_id'] = locationId;
    return firstValueFrom(this.http.get<SafetyOverview>(`${environment.apiBaseUrl}/safety/overview`, { headers, params }));
  }

  async getTrend(period: string, months = 6, locationId?: string, periodMode: PeriodMode = 'month'): Promise<SafetyTrendPoint[]> {
    const headers = await this.authHeaders();
    const params: Record<string, string> = { period, months: String(months), period_mode: periodMode };
    if (locationId) params['location_id'] = locationId;
    return firstValueFrom(this.http.get<SafetyTrendPoint[]>(`${environment.apiBaseUrl}/safety/trend`, { headers, params }));
  }
}
