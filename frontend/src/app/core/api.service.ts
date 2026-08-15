import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../environments/environment';
import { SupabaseService } from './supabase.service';

export interface AdminUser {
  id: string;
  email: string;
  roles: string[];
  location_name: string | null;
  status: string;
}

export interface AdminLocation {
  id: string;
  name: string;
}

export interface CreateUserPayload {
  email: string;
  password: string;
  roles: string[];
  location_id: string;
}

export interface UpdateUserPayload {
  roles?: string[];
  location_id?: string;
}

export interface DashboardCard {
  category: string;
  metric_type: 'total' | 'intensity';
  label: string;
  value: number;
  unit: string;
  status: 'green' | 'amber' | 'red' | 'neutral';
  comparison_label: string;
  period: string;
}

export interface DashboardSummary {
  period: string | null;
  cards: DashboardCard[];
}

export interface DrilldownEntry {
  location_name: string;
  data_point_name: string;
  value: number;
  unit: string;
  period: string;
  method_of_entry: string;
}

export interface DrilldownResponse {
  category: string;
  metric_type: string;
  period: string;
  entries: DrilldownEntry[];
  production_entries: DrilldownEntry[];
}

@Injectable({ providedIn: 'root' })
export class ApiService {
  private http = inject(HttpClient);
  private supabase = inject(SupabaseService);

  private async authHeaders(): Promise<{ Authorization: string }> {
    const { data } = await this.supabase.client.auth.getSession();
    return { Authorization: `Bearer ${data.session?.access_token ?? ''}` };
  }

  async listUsers(): Promise<AdminUser[]> {
    const headers = await this.authHeaders();
    return firstValueFrom(this.http.get<AdminUser[]>(`${environment.apiBaseUrl}/admin/users`, { headers }));
  }

  async createUser(payload: CreateUserPayload): Promise<AdminUser> {
    const headers = await this.authHeaders();
    return firstValueFrom(this.http.post<AdminUser>(`${environment.apiBaseUrl}/admin/users`, payload, { headers }));
  }

  async updateUser(id: string, payload: UpdateUserPayload): Promise<AdminUser> {
    const headers = await this.authHeaders();
    return firstValueFrom(this.http.patch<AdminUser>(`${environment.apiBaseUrl}/admin/users/${id}`, payload, { headers }));
  }

  async removeUser(id: string): Promise<void> {
    const headers = await this.authHeaders();
    await firstValueFrom(this.http.delete<void>(`${environment.apiBaseUrl}/admin/users/${id}`, { headers }));
  }

  async listLocations(): Promise<AdminLocation[]> {
    const headers = await this.authHeaders();
    return firstValueFrom(this.http.get<AdminLocation[]>(`${environment.apiBaseUrl}/admin/locations`, { headers }));
  }

  async createLocation(name: string): Promise<AdminLocation> {
    const headers = await this.authHeaders();
    return firstValueFrom(
      this.http.post<AdminLocation>(`${environment.apiBaseUrl}/admin/locations`, { name }, { headers })
    );
  }

  async renameLocation(id: string, name: string): Promise<AdminLocation> {
    const headers = await this.authHeaders();
    return firstValueFrom(
      this.http.patch<AdminLocation>(`${environment.apiBaseUrl}/admin/locations/${id}`, { name }, { headers })
    );
  }

  async removeLocation(id: string): Promise<void> {
    const headers = await this.authHeaders();
    await firstValueFrom(this.http.delete<void>(`${environment.apiBaseUrl}/admin/locations/${id}`, { headers }));
  }

  async getDashboardSummary(): Promise<DashboardSummary> {
    const headers = await this.authHeaders();
    return firstValueFrom(this.http.get<DashboardSummary>(`${environment.apiBaseUrl}/dashboard/summary`, { headers }));
  }

  async getDashboardDrilldown(category: string, period: string, metricType: string): Promise<DrilldownResponse> {
    const headers = await this.authHeaders();
    return firstValueFrom(
      this.http.get<DrilldownResponse>(`${environment.apiBaseUrl}/dashboard/drilldown`, {
        headers,
        params: { category, period, metric_type: metricType }
      })
    );
  }
}
