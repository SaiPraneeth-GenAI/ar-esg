import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { ApiService } from '../../core/api.service';
import { EntriesApiService, EntryCategory } from '../../core/entries-api.service';
import { SupabaseService } from '../../core/supabase.service';
import { ApprovalQueueComponent } from './approval-queue/approval-queue.component';
import { CategoryPickerComponent } from './category-picker/category-picker.component';
import { EntryFormComponent } from './entry-form/entry-form.component';

@Component({
  selector: 'app-data-entry',
  standalone: true,
  imports: [CategoryPickerComponent, EntryFormComponent, ApprovalQueueComponent],
  templateUrl: './data-entry.component.html',
  styleUrl: './data-entry.component.css'
})
export class DataEntryComponent implements OnInit {
  private entriesApi = inject(EntriesApiService);
  private api = inject(ApiService);
  private supabase = inject(SupabaseService);

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
}
