import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../environments/environment';
import { SupabaseService } from './supabase.service';

export type PeriodMode = 'month' | 'quarter' | 'ytd';

// Comparison wording for the "prior" figure a card shows alongside the
// current one. For YTD, the prior-period range and the prior-year range
// are the same thing (both "same months, one year back") -- showing both
// lines would just repeat the same number twice, so callers should hide
// the plain "prior" line entirely in that mode and keep only the
// prior-year one.
export function priorPeriodLabel(mode: PeriodMode): string {
  if (mode === 'quarter') return 'last quarter';
  return 'last month';
}

export function priorYearLabel(mode: PeriodMode): string {
  if (mode === 'quarter') return 'same quarter last year';
  if (mode === 'ytd') return 'same period last year';
  return 'last year';
}

export function showsPriorPeriod(mode: PeriodMode): boolean {
  return mode !== 'ytd';
}

/** A trend chart's x-axis label for one bucket, shaped to match the
 * granularity the bucket represents -- "Aug" for a month, "Q3 '26" for a
 * quarter, "2026" for a year (YTD trend). */
export function formatBucketLabel(bucketStart: string, bucketEnd: string, mode: PeriodMode): string {
  const end = new Date(`${bucketEnd}T00:00:00`);
  if (mode === 'ytd') return `${end.getFullYear()}`;
  if (mode === 'quarter') {
    const quarter = Math.floor(end.getMonth() / 3) + 1;
    return `Q${quarter} '${String(end.getFullYear()).slice(2)}`;
  }
  return end.toLocaleDateString('en-US', { month: 'short' });
}

export interface IntensityOverview {
  period: string;
  period_mode: PeriodMode;
  period_start: string | null;
  period_end: string | null;
  energy_gj: number | null;
  ghg_tco2e: number | null;
  water_kl: number | null;
  waste_mt: number | null;
  production_mnah: number | null;
  revenue_inr_cr: number | null;
  energy_per_production: number | null;
  ghg_per_production: number | null;
  water_per_production: number | null;
  waste_per_production: number | null;
  energy_per_revenue: number | null;
  ghg_per_revenue: number | null;
  water_per_revenue: number | null;
  waste_per_revenue: number | null;
  prior_energy_per_production: number | null;
  prior_ghg_per_production: number | null;
  prior_water_per_production: number | null;
  prior_waste_per_production: number | null;
  prior_energy_per_revenue: number | null;
  prior_ghg_per_revenue: number | null;
  prior_water_per_revenue: number | null;
  prior_waste_per_revenue: number | null;
  prior_energy_gj: number | null;
  prior_ghg_tco2e: number | null;
  prior_water_kl: number | null;
  prior_waste_mt: number | null;
  prior_production_mnah: number | null;
  prior_revenue_inr_cr: number | null;
  prior_year_energy_per_production: number | null;
  prior_year_ghg_per_production: number | null;
  prior_year_water_per_production: number | null;
  prior_year_waste_per_production: number | null;
  prior_year_energy_per_revenue: number | null;
  prior_year_ghg_per_revenue: number | null;
  prior_year_water_per_revenue: number | null;
  prior_year_waste_per_revenue: number | null;
  prior_year_energy_gj: number | null;
  prior_year_ghg_tco2e: number | null;
  prior_year_water_kl: number | null;
  prior_year_waste_mt: number | null;
  prior_year_production_mnah: number | null;
  prior_year_revenue_inr_cr: number | null;
}

export interface IntensityTrendPoint {
  period: string;
  bucket_start: string | null;
  bucket_end: string | null;
  ghg_per_production: number | null;
  energy_per_production: number | null;
  water_per_production: number | null;
  waste_per_production: number | null;
  ghg_per_revenue: number | null;
  energy_per_revenue: number | null;
  water_per_revenue: number | null;
  waste_per_revenue: number | null;
  prior_year_ghg_per_production: number | null;
  prior_year_energy_per_production: number | null;
  prior_year_water_per_production: number | null;
  prior_year_waste_per_production: number | null;
  prior_year_ghg_per_revenue: number | null;
  prior_year_energy_per_revenue: number | null;
  prior_year_water_per_revenue: number | null;
  prior_year_waste_per_revenue: number | null;
}

@Injectable({ providedIn: 'root' })
export class IntensityApiService {
  private http = inject(HttpClient);
  private supabase = inject(SupabaseService);

  private async authHeaders(): Promise<{ Authorization: string }> {
    const { data } = await this.supabase.client.auth.getSession();
    return { Authorization: `Bearer ${data.session?.access_token ?? ''}` };
  }

  async getOverview(period: string, locationId?: string, periodMode: PeriodMode = 'month'): Promise<IntensityOverview> {
    const headers = await this.authHeaders();
    const params: Record<string, string> = { period, period_mode: periodMode };
    if (locationId) params['location_id'] = locationId;
    return firstValueFrom(this.http.get<IntensityOverview>(`${environment.apiBaseUrl}/intensity/overview`, { headers, params }));
  }

  async getTrend(period: string, months = 6, locationId?: string, periodMode: PeriodMode = 'month'): Promise<IntensityTrendPoint[]> {
    const headers = await this.authHeaders();
    const params: Record<string, string> = { period, months: String(months), period_mode: periodMode };
    if (locationId) params['location_id'] = locationId;
    return firstValueFrom(this.http.get<IntensityTrendPoint[]>(`${environment.apiBaseUrl}/intensity/trend`, { headers, params }));
  }
}
