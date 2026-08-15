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

  async listLocations(): Promise<AdminLocation[]> {
    const headers = await this.authHeaders();
    return firstValueFrom(this.http.get<AdminLocation[]>(`${environment.apiBaseUrl}/admin/locations`, { headers }));
  }

  async createUser(payload: CreateUserPayload): Promise<AdminUser> {
    const headers = await this.authHeaders();
    return firstValueFrom(this.http.post<AdminUser>(`${environment.apiBaseUrl}/admin/users`, payload, { headers }));
  }
}
