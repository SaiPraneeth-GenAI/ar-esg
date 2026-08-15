import { Component, OnInit, inject, signal } from '@angular/core';
import { Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { SupabaseService } from '../../core/supabase.service';

@Component({
  selector: 'app-admin-layout',
  standalone: true,
  imports: [RouterOutlet, RouterLink, RouterLinkActive],
  templateUrl: './admin-layout.component.html',
  styleUrl: './admin-layout.component.css'
})
export class AdminLayoutComponent implements OnInit {
  private supabase = inject(SupabaseService);
  private router = inject(Router);

  userEmail = signal('');

  async ngOnInit(): Promise<void> {
    const { data } = await this.supabase.client.auth.getSession();
    this.userEmail.set(data.session?.user?.email ?? '');
  }

  async logout(): Promise<void> {
    await this.supabase.client.auth.signOut();
    await this.router.navigateByUrl('/login');
  }
}
