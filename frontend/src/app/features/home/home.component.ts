import { Component, inject } from '@angular/core';
import { SupabaseService } from '../../core/supabase.service';

@Component({
  selector: 'app-home',
  standalone: true,
  template: `
    <div style="max-width: 480px; margin: 4rem auto; text-align: center; font-family: inherit;">
      <h1>Welcome to Enviqo</h1>
      <p>You're signed in. This module is coming soon.</p>
      <button (click)="signOut()" style="margin-top: 1rem; cursor: pointer;">Sign out</button>
    </div>
  `
})
export class HomeComponent {
  private supabase = inject(SupabaseService);

  async signOut(): Promise<void> {
    await this.supabase.client.auth.signOut();
    window.location.href = '/login';
  }
}
