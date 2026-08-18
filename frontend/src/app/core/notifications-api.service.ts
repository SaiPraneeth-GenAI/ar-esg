import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../environments/environment';
import { SupabaseService } from './supabase.service';

export interface NotificationRecord {
  id: string;
  kind: string;
  title: string;
  body: string | null;
  link: string | null;
  read_at: string | null;
  created_at: string;
}

export interface NotificationListResponse {
  notifications: NotificationRecord[];
  unread_count: number;
}

@Injectable({ providedIn: 'root' })
export class NotificationsApiService {
  private http = inject(HttpClient);
  private supabase = inject(SupabaseService);

  private async authHeaders(): Promise<{ Authorization: string }> {
    const { data } = await this.supabase.client.auth.getSession();
    return { Authorization: `Bearer ${data.session?.access_token ?? ''}` };
  }

  async list(): Promise<NotificationListResponse> {
    const headers = await this.authHeaders();
    return firstValueFrom(this.http.get<NotificationListResponse>(`${environment.apiBaseUrl}/notifications`, { headers }));
  }

  async markRead(id: string): Promise<void> {
    const headers = await this.authHeaders();
    await firstValueFrom(this.http.post(`${environment.apiBaseUrl}/notifications/${id}/read`, {}, { headers }));
  }

  async markAllRead(): Promise<void> {
    const headers = await this.authHeaders();
    await firstValueFrom(this.http.post(`${environment.apiBaseUrl}/notifications/read-all`, {}, { headers }));
  }
}
