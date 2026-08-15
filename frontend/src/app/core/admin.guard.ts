import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { SupabaseService } from './supabase.service';

// Guards the Settings section. Deliberately Approver + Admin, not Manager --
// Managers only ever need Data Entry.
export const adminGuard: CanActivateFn = async () => {
  const supabase = inject(SupabaseService);
  const router = inject(Router);

  const { data } = await supabase.client.auth.getSession();
  const roles: string[] = (data.session?.user?.app_metadata?.['roles'] as string[]) ?? [];

  if (data.session && (roles.includes('Admin') || roles.includes('Approver'))) {
    return true;
  }
  return router.parseUrl(data.session ? '/home' : '/login');
};
