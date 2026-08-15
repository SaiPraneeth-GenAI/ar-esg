import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { AdminLocation, AdminUser, ApiService } from '../../core/api.service';

@Component({
  selector: 'app-admin-users',
  standalone: true,
  imports: [FormsModule],
  templateUrl: './admin-users.component.html',
  styleUrl: './admin-users.component.css'
})
export class AdminUsersComponent implements OnInit {
  private api = inject(ApiService);

  users = signal<AdminUser[]>([]);
  locations = signal<AdminLocation[]>([]);
  loading = signal(true);
  errorMessage = signal('');
  successMessage = signal('');
  submitting = signal(false);

  newEmail = '';
  newPassword = '';
  newLocationId = '';
  newRoles = signal<Set<string>>(new Set());

  async ngOnInit(): Promise<void> {
    await this.refresh();
  }

  async refresh(): Promise<void> {
    this.loading.set(true);
    this.errorMessage.set('');
    try {
      const [users, locations] = await Promise.all([this.api.listUsers(), this.api.listLocations()]);
      this.users.set(users);
      this.locations.set(locations);
      if (!this.newLocationId && locations.length) {
        this.newLocationId = locations[0].id;
      }
    } catch {
      this.errorMessage.set('Could not load users.');
    } finally {
      this.loading.set(false);
    }
  }

  toggleRole(role: string, checked: boolean): void {
    const roles = new Set(this.newRoles());
    if (checked) {
      if (role === 'Admin' && !confirm('Grant Admin access? Admins can manage every user and setting for this tenant.')) {
        return;
      }
      roles.add(role);
    } else {
      roles.delete(role);
    }
    this.newRoles.set(roles);
  }

  async addUser(): Promise<void> {
    this.errorMessage.set('');
    this.successMessage.set('');

    const roles = Array.from(this.newRoles());
    if (!this.newEmail || !this.newPassword || roles.length === 0 || !this.newLocationId) {
      this.errorMessage.set('Fill in email, password, at least one role, and a plant.');
      return;
    }

    this.submitting.set(true);
    try {
      await this.api.createUser({
        email: this.newEmail,
        password: this.newPassword,
        roles,
        location_id: this.newLocationId
      });
      this.successMessage.set(`${this.newEmail} was added and can sign in immediately.`);
      this.newEmail = '';
      this.newPassword = '';
      this.newRoles.set(new Set());
      await this.refresh();
    } catch (err) {
      const detail = (err as { error?: { detail?: string } })?.error?.detail;
      this.errorMessage.set(detail ?? 'Could not create user.');
    } finally {
      this.submitting.set(false);
    }
  }
}
