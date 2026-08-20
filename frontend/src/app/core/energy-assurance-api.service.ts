import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../environments/environment';
import { SupabaseService } from './supabase.service';

export interface AssuranceSite { id: string; name: string; description: string | null; is_synthetic: boolean; }
export interface AssuranceSource {
  id: string; site_id: string; name: string; source_type: string; supplier: string | null;
  renewable: boolean; active: boolean; meter_count: number;
}
export interface AssuranceMeter {
  id: string; site_id: string; source_id: string; source_name: string; meter_code: string;
  name: string; unit: string; direction: string; active: boolean;
}
export interface AssuranceReading {
  id: string; site_id: string; source_id: string; source_name: string; source_type: string;
  meter_id: string; meter_code: string; meter_name: string; period: string; value: number;
  normalized_kwh: number | null; unit: string; evidence_reference: string | null; status: string;
  quality_flags: string[]; source_row: number | null;
}
export interface Reconciliation {
  source_id: string; source_name: string; source_type: string; meter_total_kwh: number;
  reference_type: string | null; reference_value_kwh: number | null; variance_kwh: number | null;
  variance_pct: number | null; status: 'passed' | 'warning' | 'failed'; message: string;
  evidence_reference: string | null;
}
export interface TraceInput {
  reading_id: string; meter_code: string; source_name: string; value_kwh: number;
  evidence_reference: string | null; source_row: number | null;
}
export interface AssuranceWorkspace {
  period: string;
  sites: AssuranceSite[];
  active_site: AssuranceSite;
  summary: {
    completeness_pct: number; evidence_coverage_pct: number; readings_received: number;
    readings_expected: number; sources_reconciled: number; sources_total: number;
    open_exceptions: number; reporting_status: string;
  };
  sources: AssuranceSource[];
  meters: AssuranceMeter[];
  readings: AssuranceReading[];
  reconciliations: Reconciliation[];
  trace: {
    metric_name: string; result_value: number; unit: string; activity_value_kwh: number;
    factor_value: number; factor_unit: string; factor_source: string; formula: string; inputs: TraceInput[];
  };
  latest_import_at: string | null;
}
export interface ImportRow {
  row_index: number; meter_code: string; period: string; value: string; unit: string; evidence_reference?: string | null;
}
export interface ImportResult {
  rows: Array<{ row_index: number; status: string; meter_code: string; meter_name: string | null; period: string | null; value: number | null; normalized_kwh: number | null; message: string | null }>;
  valid_count: number; error_count: number; imported_count: number;
}

@Injectable({ providedIn: 'root' })
export class EnergyAssuranceApiService {
  private http = inject(HttpClient);
  private supabase = inject(SupabaseService);

  private async headers(): Promise<{ Authorization: string }> {
    const { data } = await this.supabase.client.auth.getSession();
    return { Authorization: `Bearer ${data.session?.access_token ?? ''}` };
  }

  async seedDemo(): Promise<AssuranceSite> {
    return firstValueFrom(this.http.post<AssuranceSite>(`${environment.apiBaseUrl}/energy-assurance/demo-seed`, {}, { headers: await this.headers() }));
  }

  async workspace(siteId?: string, period = '2026-08-01'): Promise<AssuranceWorkspace> {
    const params: Record<string, string> = { period };
    if (siteId) params['site_id'] = siteId;
    return firstValueFrom(this.http.get<AssuranceWorkspace>(`${environment.apiBaseUrl}/energy-assurance/workspace`, { headers: await this.headers(), params }));
  }

  async createSource(payload: Record<string, unknown>): Promise<AssuranceSource> {
    return firstValueFrom(this.http.post<AssuranceSource>(`${environment.apiBaseUrl}/energy-assurance/sources`, payload, { headers: await this.headers() }));
  }

  async updateSource(id: string, payload: Record<string, unknown>): Promise<AssuranceSource> {
    return firstValueFrom(this.http.patch<AssuranceSource>(`${environment.apiBaseUrl}/energy-assurance/sources/${id}`, payload, { headers: await this.headers() }));
  }

  async createMeter(payload: Record<string, unknown>): Promise<AssuranceMeter> {
    return firstValueFrom(this.http.post<AssuranceMeter>(`${environment.apiBaseUrl}/energy-assurance/meters`, payload, { headers: await this.headers() }));
  }

  async updateMeter(id: string, payload: Record<string, unknown>): Promise<AssuranceMeter> {
    return firstValueFrom(this.http.patch<AssuranceMeter>(`${environment.apiBaseUrl}/energy-assurance/meters/${id}`, payload, { headers: await this.headers() }));
  }

  async updateReading(id: string, payload: Record<string, unknown>): Promise<AssuranceReading> {
    return firstValueFrom(this.http.patch<AssuranceReading>(`${environment.apiBaseUrl}/energy-assurance/readings/${id}`, payload, { headers: await this.headers() }));
  }

  async importReadings(siteId: string, filename: string, rows: ImportRow[], commit: boolean): Promise<ImportResult> {
    return firstValueFrom(this.http.post<ImportResult>(`${environment.apiBaseUrl}/energy-assurance/imports`, {
      site_id: siteId, filename, rows, commit
    }, { headers: await this.headers() }));
  }
}
