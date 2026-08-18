import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { AdminDemoApiService } from '../../../core/admin-demo-api.service';
import { SupabaseService } from '../../../core/supabase.service';
import { TargetApiService, TargetBulkRowIn } from '../../../core/target-api.service';
import { TenantSettingsApiService } from '../../../core/tenant-settings-api.service';

type ClearStep = 'idle' | 'confirming' | 'clearing' | 'done';
type PopulateStep = 'idle' | 'confirming' | 'running' | 'done';

@Component({
  selector: 'app-approval-settings',
  standalone: true,
  imports: [FormsModule],
  templateUrl: './approval-settings.component.html',
  styleUrl: './approval-settings.component.css'
})
export class ApprovalSettingsComponent implements OnInit {
  private api = inject(TenantSettingsApiService);
  private demoApi = inject(AdminDemoApiService);
  private targetApi = inject(TargetApiService);
  private supabase = inject(SupabaseService);

  loading = signal(true);
  saving = signal(false);
  errorMessage = signal('');
  successMessage = signal('');
  autoApprove = signal(false);

  // -- Simulate Sample -----------------------------------------------

  simulateSampleOpen = signal(false);
  userEmail = signal('');

  clearStep = signal<ClearStep>('idle');
  clearPassword = signal('');
  clearError = signal('');
  clearResult = signal<{ entries_deleted: number; targets_deleted: number; peer_data_deleted: number } | null>(null);

  // One-click alternative to the download/upload x3 flow below: clears
  // whatever's there and repopulates factors + all entries (auto-approved)
  // + all targets (activated) in one request, so a demo never gets left
  // mid-way through Draft/Submitted rows waiting on a separate approval
  // pass. Password-gated the same as Clear, since it's just as destructive.
  populateStep = signal<PopulateStep>('idle');
  populatePassword = signal('');
  populateError = signal('');
  populateResult = signal<{ entries_created: number; targets_activated: number; entries_rejected: number; entries_pending: number } | null>(
    null
  );
  // Demo-only: pull this many of the most recent month's entries back out
  // of auto-approved so there's real material to show tracking/closing a
  // rejection and approving something live, instead of a dataset where
  // everything already happened. 0/0 keeps the original all-approved behavior.
  rejectedSampleCount = signal(0);
  pendingSampleCount = signal(0);

  downloadingEntries = signal(false);
  downloadingFactors = signal(false);
  downloadingTargets = signal(false);
  downloadError = signal('');

  targetsFileName = signal('');
  targetsUploading = signal(false);
  targetsUploadError = signal('');
  targetsUploadResult = signal<{ activated: number; errors: number } | null>(null);

  async ngOnInit(): Promise<void> {
    this.loading.set(true);
    try {
      const [settings, session] = await Promise.all([this.api.get(), this.supabase.client.auth.getSession()]);
      this.autoApprove.set(settings.auto_approve_entries);
      this.userEmail.set(session.data.session?.user?.email ?? '');
    } catch {
      this.errorMessage.set('Could not load approval settings.');
    } finally {
      this.loading.set(false);
    }
  }

  async toggle(): Promise<void> {
    const next = !this.autoApprove();
    this.saving.set(true);
    this.errorMessage.set('');
    this.successMessage.set('');
    try {
      const settings = await this.api.update({ auto_approve_entries: next });
      this.autoApprove.set(settings.auto_approve_entries);
      this.successMessage.set(next ? 'Auto-approval turned on.' : 'Auto-approval turned off.');
    } catch {
      this.errorMessage.set('Could not update this setting.');
    } finally {
      this.saving.set(false);
    }
  }

  toggleSimulateSample(): void {
    this.simulateSampleOpen.set(!this.simulateSampleOpen());
    if (!this.simulateSampleOpen()) {
      this.resetClearFlow();
      this.cancelPopulateAll();
    }
  }

  resetClearFlow(): void {
    this.clearStep.set('idle');
    this.clearPassword.set('');
    this.clearError.set('');
  }

  startClear(): void {
    this.clearStep.set('confirming');
    this.clearPassword.set('');
    this.clearError.set('');
  }

  cancelClear(): void {
    this.clearStep.set('idle');
    this.clearPassword.set('');
    this.clearError.set('');
  }

  /** Re-authenticates with the typed password before doing anything
   * destructive -- a stray click on "Clear data" can't wipe a tenant's
   * entries/targets/peer data without the Admin proving it's really them,
   * right now, not just relying on an already-open session. */
  async confirmClear(): Promise<void> {
    if (!this.clearPassword()) {
      this.clearError.set('Enter your password to confirm.');
      return;
    }
    this.clearStep.set('clearing');
    this.clearError.set('');
    try {
      const { error } = await this.supabase.client.auth.signInWithPassword({
        email: this.userEmail(),
        password: this.clearPassword()
      });
      if (error) {
        this.clearError.set('Incorrect password.');
        this.clearStep.set('confirming');
        return;
      }
      const result = await this.demoApi.clearDemoData();
      this.clearResult.set(result);
      this.clearStep.set('done');
      this.targetsUploadResult.set(null);
    } catch {
      this.clearError.set('Could not clear data -- please try again.');
      this.clearStep.set('confirming');
    } finally {
      this.clearPassword.set('');
    }
  }

  startPopulateAll(): void {
    this.populateStep.set('confirming');
    this.populatePassword.set('');
    this.populateError.set('');
  }

  cancelPopulateAll(): void {
    this.populateStep.set('idle');
    this.populatePassword.set('');
    this.populateError.set('');
  }

  /** Same re-authentication gate as confirmClear() -- this both deletes
   * existing entries/targets and recreates them, so it gets no less
   * protection than Clear alone does. */
  async confirmPopulateAll(): Promise<void> {
    if (!this.populatePassword()) {
      this.populateError.set('Enter your password to confirm.');
      return;
    }
    this.populateStep.set('running');
    this.populateError.set('');
    try {
      const { error } = await this.supabase.client.auth.signInWithPassword({
        email: this.userEmail(),
        password: this.populatePassword()
      });
      if (error) {
        this.populateError.set('Incorrect password.');
        this.populateStep.set('confirming');
        return;
      }
      const result = await this.demoApi.populateAll(this.rejectedSampleCount(), this.pendingSampleCount());
      this.populateResult.set({
        entries_created: result.entries_created,
        targets_activated: result.targets_activated,
        entries_rejected: result.entries_rejected,
        entries_pending: result.entries_pending
      });
      this.populateStep.set('done');
      this.clearResult.set(null);
      this.targetsUploadResult.set(null);
      if (result.entries_errors > 0 || result.targets_errors > 0) {
        this.populateError.set(
          `${result.entries_errors} entry row(s) and ${result.targets_errors} target row(s) could not be created -- everything else is in.`
        );
      }
    } catch {
      this.populateError.set('Could not populate demo data -- please try again.');
      this.populateStep.set('confirming');
    } finally {
      this.populatePassword.set('');
    }
  }

  async downloadEntries(): Promise<void> {
    this.downloadError.set('');
    this.downloadingEntries.set(true);
    try {
      await this.demoApi.downloadEntriesWorkbook();
    } catch {
      this.downloadError.set('Could not download the entries sample workbook.');
    } finally {
      this.downloadingEntries.set(false);
    }
  }

  async downloadFactors(): Promise<void> {
    this.downloadError.set('');
    this.downloadingFactors.set(true);
    try {
      await this.demoApi.downloadEmissionFactorsWorkbook();
    } catch {
      this.downloadError.set('Could not download the emission factors sample workbook.');
    } finally {
      this.downloadingFactors.set(false);
    }
  }

  async downloadTargets(): Promise<void> {
    this.downloadError.set('');
    this.downloadingTargets.set(true);
    try {
      await this.demoApi.downloadTargetsWorkbook();
    } catch {
      this.downloadError.set('Could not download the targets sample workbook.');
    } finally {
      this.downloadingTargets.set(false);
    }
  }

  async onTargetsFileSelected(event: Event): Promise<void> {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) return;
    this.targetsFileName.set(file.name);
    this.targetsUploadError.set('');
    this.targetsUploadResult.set(null);
    this.targetsUploading.set(true);
    try {
      const { parseSpreadsheet } = await import('../../data-entry/bulk-upload-wizard/bulk-upload-wizard.utils');
      const { headers, rows } = await parseSpreadsheet(file);
      const idx = (name: string) => headers.findIndex((h) => h.trim().toLowerCase() === name);
      const iMetric = idx('metric_key');
      const iLocation = idx('location_name');
      const iBaselineStart = idx('baseline_period_start');
      const iBaselineEnd = idx('baseline_period_end');
      const iTargetStart = idx('target_period_start');
      const iTargetEnd = idx('target_period_end');
      const iReduction = idx('reduction_percentage');
      const iRationale = idx('rationale');

      if (iMetric === -1 || iBaselineStart === -1 || iBaselineEnd === -1 || iTargetStart === -1 || iTargetEnd === -1) {
        this.targetsUploadError.set('This file is missing expected columns -- use the downloaded sample workbook as-is.');
        return;
      }

      const asDateStr = (v: unknown): string => {
        if (v instanceof Date) return `${v.getFullYear()}-${String(v.getMonth() + 1).padStart(2, '0')}-${String(v.getDate()).padStart(2, '0')}`;
        return String(v ?? '').trim();
      };

      const bulkRows: TargetBulkRowIn[] = rows.map((row, i) => ({
        row_index: i + 1,
        metric_key: String(row[iMetric] ?? '').trim(),
        location_name: iLocation !== -1 ? String(row[iLocation] ?? '').trim() || null : null,
        baseline_period_start: asDateStr(row[iBaselineStart]),
        baseline_period_end: asDateStr(row[iBaselineEnd]),
        target_period_start: asDateStr(row[iTargetStart]),
        target_period_end: asDateStr(row[iTargetEnd]),
        reduction_percentage: iReduction !== -1 && row[iReduction] !== '' ? Number(row[iReduction]) : null,
        rationale: iRationale !== -1 ? String(row[iRationale] ?? '').trim() || null : null
      }));

      const response = await this.targetApi.bulkImport({ commit: true, rows: bulkRows });
      const errors = response.rows.filter((r) => r.status === 'error');
      this.targetsUploadResult.set({ activated: response.activated_count, errors: response.error_count });
      if (errors.length > 0) {
        this.targetsUploadError.set(errors.map((e) => `Row ${e.row_index} (${e.metric_key}): ${e.message}`).join(' · '));
      }
    } catch {
      this.targetsUploadError.set('Could not upload this file -- please try again.');
    } finally {
      this.targetsUploading.set(false);
      input.value = '';
    }
  }
}
