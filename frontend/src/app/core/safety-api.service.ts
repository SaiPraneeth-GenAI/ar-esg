import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../environments/environment';
import { SupabaseService } from './supabase.service';

export interface SafetyMetric {
  name: string;
  value: number | null;
  unit: string;
  prior_value: number | null;
}

export interface SafetyOverview {
  period: string;
  metrics: SafetyMetric[];
}

@Injectable({ providedIn: 'root' })
export class SafetyApiService {
  private http = inject(HttpClient);
  private supabase = inject(SupabaseService);

  private async authHeaders(): Promise<{ Authorization: string }> {
    const { data } = await this.supabase.client.auth.getSession();
    return { Authorization: `Bearer ${data.session?.access_token ?? ''}` };
  }

  async getOverview(period: string, locationId?: string): Promise<SafetyOverview> {
    const headers = await this.authHeaders();
    const params: Record<string, string> = { period };
    if (locationId) params['location_id'] = locationId;
    return firstValueFrom(this.http.get<SafetyOverview>(`${environment.apiBaseUrl}/safety/overview`, { headers, params }));
  }
}
