import { Component, OnDestroy, OnInit, computed, inject, signal } from '@angular/core';
import { NavigationEnd, Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { Subscription, filter } from 'rxjs';
import { SupabaseService } from '../../core/supabase.service';

@Component({
  selector: 'app-admin-layout',
  standalone: true,
  imports: [RouterOutlet, RouterLink, RouterLinkActive],
  templateUrl: './admin-layout.component.html',
  styleUrl: './admin-layout.component.css'
})
export class AdminLayoutComponent implements OnInit, OnDestroy {
  private supabase = inject(SupabaseService);
  private router = inject(Router);
  private routerSub?: Subscription;

  userEmail = signal('');
  roles = signal<string[]>([]);
  currentUrl = signal(this.router.url);

  isSettingsRoute = computed(() => this.currentUrl().startsWith('/admin/settings'));
  isDataEntryRoute = computed(() => this.currentUrl().startsWith('/admin/data-entry'));
  isEmissionFactorsRoute = computed(() => this.currentUrl().startsWith('/admin/emission-factors'));
  isDashboardRoute = computed(
    () => !this.isSettingsRoute() && !this.isDataEntryRoute() && !this.isEmissionFactorsRoute()
  );
  canAccessDataEntry = computed(() => {
    const r = this.roles();
    return r.includes('Manager') || r.includes('Approver') || r.includes('Admin');
  });
  canAccessSettings = computed(() => {
    const r = this.roles();
    return r.includes('Approver') || r.includes('Admin');
  });
  canAccessEmissionFactors = this.canAccessSettings;

  settingsOpen = signal(this.isSettingsRoute());

  constructor() {
    this.routerSub = this.router.events.pipe(filter((e) => e instanceof NavigationEnd)).subscribe(() => {
      this.currentUrl.set(this.router.url);
      this.settingsOpen.set(this.isSettingsRoute());
    });
  }

  async ngOnInit(): Promise<void> {
    const { data } = await this.supabase.client.auth.getSession();
    this.userEmail.set(data.session?.user?.email ?? '');
    this.roles.set((data.session?.user?.app_metadata?.['roles'] as string[]) ?? []);
  }

  ngOnDestroy(): void {
    this.routerSub?.unsubscribe();
  }

  goToDashboard(): void {
    this.settingsOpen.set(false);
    this.router.navigateByUrl('/admin/dashboard');
  }

  goToDataEntry(): void {
    this.settingsOpen.set(false);
    this.router.navigateByUrl('/admin/data-entry');
  }

  goToEmissionFactors(): void {
    this.settingsOpen.set(false);
    this.router.navigateByUrl('/admin/emission-factors');
  }

  openSettings(): void {
    this.settingsOpen.set(true);
    if (!this.isSettingsRoute()) {
      this.router.navigateByUrl('/admin/settings/users');
    }
  }

  async logout(): Promise<void> {
    await this.supabase.client.auth.signOut();
    await this.router.navigateByUrl('/login');
  }
}
