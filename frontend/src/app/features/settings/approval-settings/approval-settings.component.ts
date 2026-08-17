import { Component, OnInit, inject, signal } from '@angular/core';
import { TenantSettingsApiService } from '../../../core/tenant-settings-api.service';

@Component({
  selector: 'app-approval-settings',
  standalone: true,
  imports: [],
  templateUrl: './approval-settings.component.html',
  styleUrl: './approval-settings.component.css'
})
export class ApprovalSettingsComponent implements OnInit {
  private api = inject(TenantSettingsApiService);

  loading = signal(true);
  saving = signal(false);
  errorMessage = signal('');
  successMessage = signal('');
  autoApprove = signal(false);

  async ngOnInit(): Promise<void> {
    this.loading.set(true);
    try {
      const settings = await this.api.get();
      this.autoApprove.set(settings.auto_approve_entries);
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
}
