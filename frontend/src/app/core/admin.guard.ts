import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { SupabaseService } from './supabase.service';

export const adminGuard: CanActivateFn = async () => {
  const supabase = inject(SupabaseService);
  const router = inject(Router);

  const { data } = await supabase.client.auth.getSession();
  const roles: string[] = (data.session?.user?.app_metadata?.['roles'] as string[]) ?? [];

  if (data.session && roles.includes('Admin')) {
    return true;
  }
  return router.parseUrl(data.session ? '/home' : '/login');
};
