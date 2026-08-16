import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../environments/environment';
import { SupabaseService } from './supabase.service';

export interface IntensityOverview {
  period: string;
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
}

@Injectable({ providedIn: 'root' })
export class IntensityApiService {
  private http = inject(HttpClient);
  private supabase = inject(SupabaseService);

  private async authHeaders(): Promise<{ Authorization: string }> {
    const { data } = await this.supabase.client.auth.getSession();
    return { Authorization: `Bearer ${data.session?.access_token ?? ''}` };
  }

  async getOverview(period: string, locationId?: string): Promise<IntensityOverview> {
    const headers = await this.authHeaders();
    const params: Record<string, string> = { period };
    if (locationId) params['location_id'] = locationId;
    return firstValueFrom(this.http.get<IntensityOverview>(`${environment.apiBaseUrl}/intensity/overview`, { headers, params }));
  }
}
