import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../environments/environment';
import { SupabaseService } from './supabase.service';

export interface ClearDemoDataResponse {
  entries_deleted: number;
  targets_deleted: number;
  peer_data_deleted: number;
}

@Injectable({ providedIn: 'root' })
export class AdminDemoApiService {
  private http = inject(HttpClient);
  private supabase = inject(SupabaseService);

  private async authHeaders(): Promise<{ Authorization: string }> {
    const { data } = await this.supabase.client.auth.getSession();
    return { Authorization: `Bearer ${data.session?.access_token ?? ''}` };
  }

  async clearDemoData(): Promise<ClearDemoDataResponse> {
    const headers = await this.authHeaders();
    return firstValueFrom(
      this.http.post<ClearDemoDataResponse>(`${environment.apiBaseUrl}/admin/demo/clear`, {}, { headers })
    );
  }

  private async downloadFile(path: string, filename: string): Promise<void> {
    const headers = await this.authHeaders();
    const blob = await firstValueFrom(
      this.http.get(`${environment.apiBaseUrl}${path}`, { headers, responseType: 'blob' })
    );
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    link.click();
    URL.revokeObjectURL(url);
  }

  downloadEntriesWorkbook(): Promise<void> {
    return this.downloadFile('/admin/demo/entries-workbook', 'demo_entries_aug2024_aug2026.xlsx');
  }

  downloadEmissionFactorsWorkbook(): Promise<void> {
    return this.downloadFile('/admin/demo/emission-factors-workbook', 'demo_emission_factors.xlsx');
  }

  downloadTargetsWorkbook(): Promise<void> {
    return this.downloadFile('/admin/demo/targets-workbook', 'demo_targets.xlsx');
  }
}
