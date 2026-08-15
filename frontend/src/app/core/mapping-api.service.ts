import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../environments/environment';
import { SupabaseService } from './supabase.service';

export interface SheetInput {
  name: string;
  filename: string;
  headers: string[];
}

export interface ColumnSuggestion {
  header: string;
  target: string | null;
  target_type: 'metadata' | 'data_point' | 'unmatched';
  data_point_name: string | null;
  score: number;
  rule: 'exact_alias' | 'fuzzy' | 'no_match' | 'template';
}

export interface SheetDetectionResult {
  sheet_name: string;
  header_fingerprint: string;
  category_id: string | null;
  category_name: string | null;
  category_score: number;
  category_rule: string;
  columns: ColumnSuggestion[];
  inferred_period: string | null;
  from_template: boolean;
  template_id: string | null;
}

export interface DetectResponse {
  sheets: SheetDetectionResult[];
}

export interface MappingTemplateOut {
  id: string;
  category_id: string;
  category_name: string;
  header_fingerprint: string;
  column_mapping: Record<string, string>;
  created_at: string;
  updated_at: string;
}

@Injectable({ providedIn: 'root' })
export class MappingApiService {
  private http = inject(HttpClient);
  private supabase = inject(SupabaseService);

  private async authHeaders(): Promise<{ Authorization: string }> {
    const { data } = await this.supabase.client.auth.getSession();
    return { Authorization: `Bearer ${data.session?.access_token ?? ''}` };
  }

  async detect(sheets: SheetInput[]): Promise<DetectResponse> {
    const headers = await this.authHeaders();
    return firstValueFrom(
      this.http.post<DetectResponse>(`${environment.apiBaseUrl}/entries/bulk-import/detect`, { sheets }, { headers })
    );
  }

  async saveTemplate(categoryId: string, headerFingerprint: string, columnMapping: Record<string, string>): Promise<MappingTemplateOut> {
    const headers = await this.authHeaders();
    return firstValueFrom(
      this.http.post<MappingTemplateOut>(
        `${environment.apiBaseUrl}/entries/bulk-import/save-template`,
        { category_id: categoryId, header_fingerprint: headerFingerprint, column_mapping: columnMapping },
        { headers }
      )
    );
  }

  async listTemplates(): Promise<MappingTemplateOut[]> {
    const headers = await this.authHeaders();
    return firstValueFrom(
      this.http.get<MappingTemplateOut[]>(`${environment.apiBaseUrl}/admin/mapping-templates`, { headers })
    );
  }

  async deleteTemplate(id: string): Promise<void> {
    const headers = await this.authHeaders();
    await firstValueFrom(this.http.delete<void>(`${environment.apiBaseUrl}/admin/mapping-templates/${id}`, { headers }));
  }
}
