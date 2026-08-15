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
  currentUrl = signal(this.router.url);
  isSettingsRoute = computed(() => this.currentUrl().startsWith('/admin/settings'));
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
  }

  ngOnDestroy(): void {
    this.routerSub?.unsubscribe();
  }

  goToDashboard(): void {
    this.settingsOpen.set(false);
    this.router.navigateByUrl('/admin/dashboard');
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
