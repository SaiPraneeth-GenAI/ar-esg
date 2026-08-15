import { Component, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router } from '@angular/router';
import { SupabaseService } from '../../core/supabase.service';

@Component({
  selector: 'app-login',
  standalone: true,
  imports: [ReactiveFormsModule],
  templateUrl: './login.component.html',
  styleUrl: './login.component.css'
})
export class LoginComponent {
  private fb = inject(FormBuilder);
  private supabase = inject(SupabaseService);
  private router = inject(Router);

  form = this.fb.nonNullable.group({
    email: ['', [Validators.required, Validators.email]],
    password: ['', [Validators.required]]
  });

  loading = signal(false);
  errorMessage = signal('');

  async signIn(): Promise<void> {
    if (this.form.invalid) {
      return;
    }
    this.loading.set(true);
    this.errorMessage.set('');

    const { email, password } = this.form.getRawValue();
    const { data, error } = await this.supabase.client.auth.signInWithPassword({ email, password });

    this.loading.set(false);

    if (error || !data.session) {
      this.errorMessage.set(error?.message ?? 'Could not sign in.');
      return;
    }

    const roles = (data.session.user.app_metadata?.['roles'] as string[]) ?? [];
    await this.router.navigateByUrl(roles.includes('Admin') ? '/admin/settings/users' : '/home');
  }

  async forgotPassword(): Promise<void> {
    const email = this.form.get('email')?.value;
    if (!email) {
      this.errorMessage.set('Enter your email above first, then click "Forgot password".');
      return;
    }
    const { error } = await this.supabase.client.auth.resetPasswordForEmail(email);
    this.errorMessage.set(error ? error.message : 'Password reset email sent.');
  }
}
