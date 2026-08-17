import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../environments/environment';
import { SupabaseService } from './supabase.service';

export interface TenantSettings {
  auto_approve_entries: boolean;
}

@Injectable({ providedIn: 'root' })
export class TenantSettingsApiService {
  private http = inject(HttpClient);
  private supabase = inject(SupabaseService);

  private async authHeaders(): Promise<{ Authorization: string }> {
    const { data } = await this.supabase.client.auth.getSession();
    return { Authorization: `Bearer ${data.session?.access_token ?? ''}` };
  }

  async get(): Promise<TenantSettings> {
    const headers = await this.authHeaders();
    return firstValueFrom(this.http.get<TenantSettings>(`${environment.apiBaseUrl}/admin/tenant-settings`, { headers }));
  }

  async update(payload: TenantSettings): Promise<TenantSettings> {
    const headers = await this.authHeaders();
    return firstValueFrom(this.http.patch<TenantSettings>(`${environment.apiBaseUrl}/admin/tenant-settings`, payload, { headers }));
  }
}
