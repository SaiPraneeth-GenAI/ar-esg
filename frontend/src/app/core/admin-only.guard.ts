import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { SupabaseService } from './supabase.service';

// Stricter than adminGuard -- for the handful of Settings pages the backend
// itself restricts to Admin only (Users, Roles, Sites, Approval Settings).
// Without this, an Approver could reach the page (adminGuard lets them into
// the Settings section) only to have every API call 403 underneath them,
// landing on a broken shell instead of being kept out in the first place.
export const adminOnlyGuard: CanActivateFn = async () => {
  const supabase = inject(SupabaseService);
  const router = inject(Router);

  const { data } = await supabase.client.auth.getSession();
  const roles: string[] = (data.session?.user?.app_metadata?.['roles'] as string[]) ?? [];

  if (data.session && roles.includes('Admin')) {
    return true;
  }
  return router.parseUrl(data.session ? '/admin/dashboard' : '/login');
};
