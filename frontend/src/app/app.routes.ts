import { Routes } from '@angular/router';
import { adminGuard } from './core/admin.guard';
import { authGuard } from './core/auth.guard';

export const routes: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'login' },
  {
    path: 'login',
    loadComponent: () => import('./features/login/login.component').then((m) => m.LoginComponent)
  },
  {
    path: 'home',
    canActivate: [authGuard],
    loadComponent: () => import('./features/home/home.component').then((m) => m.HomeComponent)
  },
  {
    path: 'admin/users',
    canActivate: [adminGuard],
    loadComponent: () =>
      import('./features/admin-users/admin-users.component').then((m) => m.AdminUsersComponent)
  },
  { path: '**', redirectTo: 'login' }
];
