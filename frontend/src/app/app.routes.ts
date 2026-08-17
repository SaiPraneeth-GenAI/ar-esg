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
    canActivate: [authGuard],
    loadComponent: () => import('./layout/admin-layout/admin-layout.component').then((m) => m.AdminLayoutComponent),
    children: [
      { path: '', pathMatch: 'full', redirectTo: 'dashboard' },
      {
        path: 'dashboard',
        loadComponent: () => import('./features/dashboard/dashboard.component').then((m) => m.DashboardComponent)
      },
      {
        path: 'data-entry',
        loadComponent: () => import('./features/data-entry/data-entry.component').then((m) => m.DataEntryComponent)
      },
      {
        path: 'methodology',
        loadComponent: () => import('./features/methodology/methodology.component').then((m) => m.MethodologyComponent)
      },
      {
        path: 'emission-factors',
        canActivate: [adminGuard],
        loadComponent: () =>
          import('./features/settings/emission-factors/emission-factors.component').then(
            (m) => m.EmissionFactorsComponent
          )
      },
      {
        path: 'targets',
        canActivate: [adminGuard],
        loadComponent: () => import('./features/settings/targets/targets.component').then((m) => m.TargetsComponent)
      },
      {
        path: 'charts',
        loadComponent: () => import('./features/charts/charts.component').then((m) => m.ChartsComponent)
      },
      {
        path: 'settings/users',
        canActivate: [adminGuard],
        loadComponent: () =>
          import('./features/settings/user-management/user-management.component').then(
            (m) => m.UserManagementComponent
          )
      },
      {
        path: 'settings/roles',
        canActivate: [adminGuard],
        loadComponent: () =>
          import('./features/settings/user-roles/user-roles.component').then((m) => m.UserRolesComponent)
      },
      {
        path: 'settings/plants',
        canActivate: [adminGuard],
        loadComponent: () =>
          import('./features/settings/assigned-plants/assigned-plants.component').then(
            (m) => m.AssignedPlantsComponent
          )
      },
      {
        path: 'settings/mapping-templates',
        canActivate: [adminGuard],
        loadComponent: () =>
          import('./features/settings/mapping-templates/mapping-templates.component').then(
            (m) => m.MappingTemplatesComponent
          )
      },
      {
        path: 'settings/approvals',
        canActivate: [adminGuard],
        loadComponent: () =>
          import('./features/settings/approval-settings/approval-settings.component').then(
            (m) => m.ApprovalSettingsComponent
          )
      }
    ]
  },
  { path: '**', redirectTo: 'login' }
];
