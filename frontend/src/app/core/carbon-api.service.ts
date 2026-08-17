import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../environments/environment';
import { PeriodMode } from './intensity-api.service';
import { SupabaseService } from './supabase.service';

export interface CarbonOverviewSource {
  data_point_name: string;
  scope: number;
  calculation_method: string | null;
  emissions_tco2e: number;
  entry_count: number;
}

export interface TargetComparison {
  target_id: string;
  target_value: number | null;
  status: string;
}

export interface TargetStatusOut {
  target_id: string;
  metric_key: string;
  label: string;
  unit: string;
  actual: number | null;
  target_value: number;
  status: string;
}

export interface CarbonOverview {
  period: string | null;
  period_mode: PeriodMode;
  period_start: string | null;
  period_end: string | null;
  scope1_tco2e: number | null;
  scope2_location_based_tco2e: number | null;
  scope2_market_based_tco2e: number | null;
  scope1_2_location_based_tco2e: number | null;
  prior_scope1_2_location_based_tco2e: number | null;
  prior_intensity_tco2e_per_mnah: number | null;
  prior_year_scope1_2_location_based_tco2e: number | null;
  prior_year_intensity_tco2e_per_mnah: number | null;
  prior_scope1_tco2e: number | null;
  prior_year_scope1_tco2e: number | null;
  prior_scope2_location_based_tco2e: number | null;
  prior_year_scope2_location_based_tco2e: number | null;
  production_value: number | null;
  production_unit: string | null;
  intensity_tco2e_per_mnah: number | null;
  unresolved_count: number;
  calculated_count: number;
  completeness_pct: number | null;
  sources: CarbonOverviewSource[];
  insight: string | null;
  scope1_2_target: TargetComparison | null;
  intensity_target: TargetComparison | null;
  scope1_target: TargetComparison | null;
  scope2_target: TargetComparison | null;
  all_targets: TargetStatusOut[];
}

export interface CarbonTrendPoint {
  period: string;
  bucket_start: string | null;
  bucket_end: string | null;
  scope1_tco2e: number | null;
  scope2_location_based_tco2e: number | null;
  scope1_2_location_based_tco2e: number | null;
  scope3_tco2e: number | null;
  intensity_tco2e_per_mnah: number | null;
  prior_year_scope1_tco2e: number | null;
  prior_year_scope2_location_based_tco2e: number | null;
  prior_year_scope1_2_location_based_tco2e: number | null;
  prior_year_intensity_tco2e_per_mnah: number | null;
  target_scope1_tco2e: number | null;
  target_scope2_location_based_tco2e: number | null;
  target_scope1_2_location_based_tco2e: number | null;
  target_intensity_tco2e_per_mnah: number | null;
}

export interface EmissionCalculationOut {
  id: string;
  entry_id: string;
  data_point_id: string;
  data_point_name: string;
  location_id: string;
  location_name: string;
  reporting_period: string;
  scope: number;
  calculation_method: string | null;
  status: string;
  activity_value: number;
  activity_unit: string;
  normalized_activity_value: number | null;
  normalized_activity_unit: string | null;
  factor_version: string | null;
  factor_value: number | null;
  factor_unit: string | null;
  factor_source: string | null;
  factor_effective_year: number | null;
  emissions_kgco2e: number | null;
  emissions_tco2e: number | null;
  formula: string | null;
  resolution_reason: string | null;
  calculated_at: string;
  calculated_by_email: string | null;
  supersedes_calculation_id: string | null;
}

@Injectable({ providedIn: 'root' })
export class CarbonApiService {
  private http = inject(HttpClient);
  private supabase = inject(SupabaseService);

  private async authHeaders(): Promise<{ Authorization: string }> {
    const { data } = await this.supabase.client.auth.getSession();
    return { Authorization: `Bearer ${data.session?.access_token ?? ''}` };
  }

  async getOverview(period: string, locationId?: string, periodMode: PeriodMode = 'month'): Promise<CarbonOverview> {
    const headers = await this.authHeaders();
    const params: Record<string, string> = { period, period_mode: periodMode };
    if (locationId) params['location_id'] = locationId;
    return firstValueFrom(this.http.get<CarbonOverview>(`${environment.apiBaseUrl}/carbon/overview`, { headers, params }));
  }

  async getTrend(period: string, months = 6, locationId?: string, periodMode: PeriodMode = 'month'): Promise<CarbonTrendPoint[]> {
    const headers = await this.authHeaders();
    const params: Record<string, string> = { period, months: String(months), period_mode: periodMode };
    if (locationId) params['location_id'] = locationId;
    return firstValueFrom(this.http.get<CarbonTrendPoint[]>(`${environment.apiBaseUrl}/carbon/trend`, { headers, params }));
  }

  async getAiInsight(period: string, locationId?: string, periodMode: PeriodMode = 'month'): Promise<{ insight: string | null }> {
    const headers = await this.authHeaders();
    const params: Record<string, string> = { period, period_mode: periodMode };
    if (locationId) params['location_id'] = locationId;
    return firstValueFrom(this.http.get<{ insight: string | null }>(`${environment.apiBaseUrl}/carbon/ai-insight`, { headers, params }));
  }

  async getCalculations(
    period: string,
    filters: { scope?: number; calculationMethod?: string; dataPointName?: string; locationId?: string; periodMode?: PeriodMode } = {}
  ): Promise<EmissionCalculationOut[]> {
    const headers = await this.authHeaders();
    const params: Record<string, string> = { period, period_mode: filters.periodMode ?? 'month' };
    if (filters.scope) params['scope'] = String(filters.scope);
    if (filters.calculationMethod) params['calculation_method'] = filters.calculationMethod;
    if (filters.dataPointName) params['data_point_name'] = filters.dataPointName;
    if (filters.locationId) params['location_id'] = filters.locationId;
    return firstValueFrom(this.http.get<EmissionCalculationOut[]>(`${environment.apiBaseUrl}/carbon/calculations`, { headers, params }));
  }

  async getUnresolved(locationId?: string): Promise<EmissionCalculationOut[]> {
    const headers = await this.authHeaders();
    const params: Record<string, string> = {};
    if (locationId) params['location_id'] = locationId;
    return firstValueFrom(this.http.get<EmissionCalculationOut[]>(`${environment.apiBaseUrl}/carbon/unresolved`, { headers, params }));
  }
}
