import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../environments/environment';
import { SupabaseService } from './supabase.service';

export interface EmissionFactorOut {
  id: string;
  scope: number;
  gas_type: string | null;
  method: string | null;
  scope3_category: string | null;
  description: string | null;
  unit: string;
  factor_value: number;
  effective_year: number;
  version: string;
  source: string | null;
  source_reference: string | null;
  ipcc_reference_key: string | null;
  is_active: boolean;
  created_by: string | null;
}

export interface EmissionFactorCreate {
  scope: number;
  gas_type?: string | null;
  method?: string | null;
  scope3_category?: string | null;
  description?: string | null;
  unit: string;
  factor_value: number;
  effective_year: number;
  source?: string | null;
  source_reference: string;
  ipcc_reference_key?: string | null;
}

export interface EmissionFactorUpdate extends EmissionFactorCreate {
  is_active: boolean;
}

export interface IpccSearchResult {
  substance_name: string;
  scope: number;
  factor_type: string;
  scope3_category: string | null;
  latest_effective_year: number;
  latest_publication: string;
}

export interface IpccVersionOut {
  id: string;
  substance_name: string;
  scope: number;
  factor_type: string;
  scope3_category: string | null;
  publication: string;
  effective_year: number;
  ncv_mj_per_unit: number | null;
  density_kg_per_unit: number | null;
  co2_ef_per_tj: number | null;
  oxidation_factor: number | null;
  derived_factor_value: number;
  unit: string;
  source_reference: string;
}

export interface IpccMatch {
  substance_name: string;
  publication: string;
  effective_year: number;
  reference_value: number;
  unit: string;
  delta_pct: number | null;
}

export interface EFSheetInput {
  name: string;
  filename: string;
  headers: string[];
  rows: string[][];
  column_overrides?: Record<string, string> | null;
}

export interface EFColumnSuggestion {
  header: string;
  index: number;
  role: string;
  year_label: string | null;
  score: number;
  rule: string;
}

export interface EFFactorDraft {
  sheet_name: string;
  block_index: number;
  row_index: number;
  scope: number;
  gas_type: string | null;
  method: string | null;
  scope3_category: string | null;
  description: string | null;
  unit: string | null;
  factor_value: number | null;
  effective_year: number | null;
  version: string | null;
  source: string | null;
  source_reference: string | null;
  included: boolean;
  status: string;
  message: string | null;
  raw_cell_text: string | null;
  ipcc_match: IpccMatch | null;
}

export interface EFSheetDetectionResult {
  sheet_name: string;
  block_index: number;
  scope: number | null;
  scope_score: number;
  scope_rule: string;
  columns: EFColumnSuggestion[];
  factors: EFFactorDraft[];
  factor_count: number;
}

export interface EFDetectResponse {
  sheets: EFSheetDetectionResult[];
}

export interface EFBulkImportResult {
  sheet_name: string;
  row_index: number;
  status: string;
  message: string | null;
  factor_id: string | null;
}

export interface EFBulkImportResponse {
  results: EFBulkImportResult[];
  ready_count: number;
  error_count: number;
  created_count: number;
}

@Injectable({ providedIn: 'root' })
export class EmissionFactorsApiService {
  private http = inject(HttpClient);
  private supabase = inject(SupabaseService);

  private async authHeaders(): Promise<{ Authorization: string }> {
    const { data } = await this.supabase.client.auth.getSession();
    return { Authorization: `Bearer ${data.session?.access_token ?? ''}` };
  }

  async list(scope?: number, includeInactive = false): Promise<EmissionFactorOut[]> {
    const headers = await this.authHeaders();
    const params: Record<string, string> = {};
    if (scope) params['scope'] = String(scope);
    if (includeInactive) params['include_inactive'] = 'true';
    return firstValueFrom(
      this.http.get<EmissionFactorOut[]>(`${environment.apiBaseUrl}/admin/emission-factors`, { headers, params })
    );
  }

  async create(payload: EmissionFactorCreate): Promise<EmissionFactorOut> {
    const headers = await this.authHeaders();
    return firstValueFrom(
      this.http.post<EmissionFactorOut>(`${environment.apiBaseUrl}/admin/emission-factors`, payload, { headers })
    );
  }

  async update(id: string, payload: EmissionFactorUpdate): Promise<EmissionFactorOut> {
    const headers = await this.authHeaders();
    return firstValueFrom(
      this.http.patch<EmissionFactorOut>(`${environment.apiBaseUrl}/admin/emission-factors/${id}`, payload, { headers })
    );
  }

  async searchIpccReference(q: string, scope?: number): Promise<IpccSearchResult[]> {
    const headers = await this.authHeaders();
    const params: Record<string, string> = { q };
    if (scope) params['scope'] = String(scope);
    return firstValueFrom(
      this.http.get<IpccSearchResult[]>(`${environment.apiBaseUrl}/admin/emission-factors/ipcc-reference/search`, {
        headers,
        params
      })
    );
  }

  async listIpccVersions(substanceName: string): Promise<IpccVersionOut[]> {
    const headers = await this.authHeaders();
    return firstValueFrom(
      this.http.get<IpccVersionOut[]>(`${environment.apiBaseUrl}/admin/emission-factors/ipcc-reference/versions`, {
        headers,
        params: { substance_name: substanceName }
      })
    );
  }

  async bulkDetect(
    sheets: EFSheetInput[],
    defaultEffectiveYear: number | null,
    defaultMethod: string | null
  ): Promise<EFDetectResponse> {
    const headers = await this.authHeaders();
    return firstValueFrom(
      this.http.post<EFDetectResponse>(
        `${environment.apiBaseUrl}/admin/emission-factors/bulk-detect`,
        { sheets, default_effective_year: defaultEffectiveYear, default_method: defaultMethod },
        { headers }
      )
    );
  }

  async bulkImport(factors: EFFactorDraft[], commit: boolean): Promise<EFBulkImportResponse> {
    const headers = await this.authHeaders();
    return firstValueFrom(
      this.http.post<EFBulkImportResponse>(
        `${environment.apiBaseUrl}/admin/emission-factors/bulk-import`,
        { commit, factors },
        { headers }
      )
    );
  }
}
