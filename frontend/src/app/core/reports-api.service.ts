import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../environments/environment';
import { PeriodMode } from './intensity-api.service';
import { SupabaseService } from './supabase.service';

export type ReportFormat = 'pdf' | 'pptx';

@Injectable({ providedIn: 'root' })
export class ReportsApiService {
  private http = inject(HttpClient);
  private supabase = inject(SupabaseService);

  private async authHeaders(): Promise<{ Authorization: string }> {
    const { data } = await this.supabase.client.auth.getSession();
    return { Authorization: `Bearer ${data.session?.access_token ?? ''}` };
  }

  /** Fetches the export as a blob and triggers a normal browser download --
   * no separate confirmation step, matching a plain "Download" button. */
  async downloadDashboardReport(
    format: ReportFormat,
    period: string,
    periodMode: PeriodMode,
    locationId?: string
  ): Promise<void> {
    const headers = await this.authHeaders();
    const params: Record<string, string> = { period, period_mode: periodMode, format };
    if (locationId) params['location_id'] = locationId;

    const blob = await firstValueFrom(
      this.http.get(`${environment.apiBaseUrl}/reports/dashboard-export`, { headers, params, responseType: 'blob' })
    );

    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `amara_raja_esg_dashboard_${period}.${format}`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }
}
