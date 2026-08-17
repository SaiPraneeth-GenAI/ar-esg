import { Component, OnDestroy, OnInit, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router } from '@angular/router';
import { SupabaseService } from '../../core/supabase.service';

// Short, concrete claims -- each one names an actual capability of the
// platform (not generic marketing filler), cycled like a live product
// ticker on the sign-in screen's brand panel.
const PITCH_LINES = [
  'Scope 1+2 emissions tracked to the exact calculation snapshot',
  'One-click BRSR-ready PDF & PPTX exports, every dashboard tab',
  'AI insights, guardrailed to your real numbers -- never invented',
  'Live target tracking against every site, every metric'
];

@Component({
  selector: 'app-login',
  standalone: true,
  imports: [ReactiveFormsModule],
  templateUrl: './login.component.html',
  styleUrl: './login.component.css'
})
export class LoginComponent implements OnInit, OnDestroy {
  private fb = inject(FormBuilder);
  private supabase = inject(SupabaseService);
  private router = inject(Router);

  form = this.fb.nonNullable.group({
    email: ['', [Validators.required, Validators.email]],
    password: ['', [Validators.required]]
  });

  loading = signal(false);
  errorMessage = signal('');

  pitchLines = PITCH_LINES;
  pitchIndex = signal(0);
  private pitchTimer?: ReturnType<typeof setInterval>;

  ngOnInit(): void {
    this.pitchTimer = setInterval(() => {
      this.pitchIndex.set((this.pitchIndex() + 1) % this.pitchLines.length);
    }, 3600);
  }

  ngOnDestroy(): void {
    if (this.pitchTimer) clearInterval(this.pitchTimer);
  }

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
    const hasTenantRole = roles.includes('Admin') || roles.includes('Manager') || roles.includes('Approver');
    await this.router.navigateByUrl(hasTenantRole ? '/admin/dashboard' : '/home');
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
