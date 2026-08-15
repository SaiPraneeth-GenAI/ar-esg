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
    path: 'admin',
    canActivate: [adminGuard],
    loadComponent: () => import('./layout/admin-layout/admin-layout.component').then((m) => m.AdminLayoutComponent),
    children: [
      { path: '', pathMatch: 'full', redirectTo: 'settings/users' },
      {
        path: 'settings/users',
        loadComponent: () =>
          import('./features/settings/user-management/user-management.component').then(
            (m) => m.UserManagementComponent
          )
      },
      {
        path: 'settings/roles',
        loadComponent: () =>
          import('./features/settings/user-roles/user-roles.component').then((m) => m.UserRolesComponent)
      },
      {
        path: 'settings/plants',
        loadComponent: () =>
          import('./features/settings/assigned-plants/assigned-plants.component').then(
            (m) => m.AssignedPlantsComponent
          )
      }
    ]
  },
  { path: '**', redirectTo: 'login' }
];
