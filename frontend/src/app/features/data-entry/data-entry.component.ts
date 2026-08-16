import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { ActivatedRoute } from '@angular/router';
import { ApiService } from '../../core/api.service';
import { EntriesApiService, EntryCategory } from '../../core/entries-api.service';
import { SupabaseService } from '../../core/supabase.service';
import { ApprovalQueueComponent } from './approval-queue/approval-queue.component';
import { BulkUploadWizardComponent } from './bulk-upload-wizard/bulk-upload-wizard.component';
import { CategoryPickerComponent } from './category-picker/category-picker.component';
import { EntryFormComponent } from './entry-form/entry-form.component';

function currentMonthValue(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-01`;
}

@Component({
  selector: 'app-data-entry',
  standalone: true,
  imports: [CategoryPickerComponent, EntryFormComponent, ApprovalQueueComponent, BulkUploadWizardComponent],
  templateUrl: './data-entry.component.html',
  styleUrl: './data-entry.component.css'
})
export class DataEntryComponent implements OnInit {
  private entriesApi = inject(EntriesApiService);
  private api = inject(ApiService);
  private supabase = inject(SupabaseService);
  private route = inject(ActivatedRoute);

  loading = signal(true);
  errorMessage = signal('');

  roles = signal<string[]>([]);
  canSubmit = computed(() => this.roles().includes('Manager') || this.roles().includes('Admin'));
  canApprove = computed(() => this.roles().includes('Approver') || this.roles().includes('Admin'));
  showTabs = computed(() => this.canSubmit() && this.canApprove());

  activeTab = signal<'submit' | 'approve'>('submit');
  categories = signal<EntryCategory[]>([]);
  selectedCategory = signal<EntryCategory | null>(null);
  locationId = signal('');
  initialPeriod = signal<string | null>(null);
  showBulkUploadAll = signal(false);
  bulkUploadPeriod = signal(currentMonthValue());

  async ngOnInit(): Promise<void> {
    this.loading.set(true);
    try {
      const { data } = await this.supabase.client.auth.getSession();
      const roles = (data.session?.user?.app_metadata?.['roles'] as string[]) ?? [];
      this.roles.set(roles);
      this.activeTab.set(roles.includes('Manager') || roles.includes('Admin') ? 'submit' : 'approve');

      const [categories, locations] = await Promise.all([this.entriesApi.listCategories(), this.api.listLocations()]);
      this.categories.set(categories);
      if (locations.length) {
        this.locationId.set(locations[0].id);
      }

      const params = this.route.snapshot.queryParamMap;
      const categoryName = params.get('category');
      const period = params.get('period');
      if (period) {
        this.initialPeriod.set(period.length === 7 ? `${period}-01` : period);
      }
      if (categoryName) {
        const match = categories.find((c) => c.name === categoryName);
        if (match) {
          this.activeTab.set('submit');
          this.selectedCategory.set(match);
        }
      }
    } catch {
      this.errorMessage.set('Could not load the data entry module.');
    } finally {
      this.loading.set(false);
    }
  }

  pickCategory(category: EntryCategory): void {
    this.selectedCategory.set(category);
  }

  backToCategories(): void {
    this.selectedCategory.set(null);
  }

  openBulkUploadAll(): void {
    this.showBulkUploadAll.set(true);
  }

  closeBulkUploadAll(): void {
    this.showBulkUploadAll.set(false);
  }
}
