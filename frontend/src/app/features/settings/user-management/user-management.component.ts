import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { AdminLocation, AdminUser, ApiService } from '../../../core/api.service';
import { SupabaseService } from '../../../core/supabase.service';

@Component({
  selector: 'app-user-management',
  standalone: true,
  imports: [FormsModule],
  templateUrl: './user-management.component.html',
  styleUrl: './user-management.component.css'
})
export class UserManagementComponent implements OnInit {
  private api = inject(ApiService);
  private supabase = inject(SupabaseService);

  users = signal<AdminUser[]>([]);
  locations = signal<AdminLocation[]>([]);
  loading = signal(true);
  errorMessage = signal('');
  successMessage = signal('');
  submitting = signal(false);
  currentUserId = signal('');

  newEmail = '';
  newPassword = '';
  newLocationId = '';
  newRoles = signal<Set<string>>(new Set());

  editingUserId = signal<string | null>(null);
  editRoles = signal<Set<string>>(new Set());
  editLocationId = '';

  async ngOnInit(): Promise<void> {
    const { data } = await this.supabase.client.auth.getSession();
    this.currentUserId.set(data.session?.user?.id ?? '');
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
      this.errorMessage.set(this.extractError(err));
    } finally {
      this.submitting.set(false);
    }
  }

  startEdit(user: AdminUser): void {
    this.errorMessage.set('');
    this.successMessage.set('');
    this.editingUserId.set(user.id);
    this.editRoles.set(new Set(user.roles));
    const match = this.locations().find((loc) => loc.name === user.location_name);
    this.editLocationId = match?.id ?? '';
  }

  cancelEdit(): void {
    this.editingUserId.set(null);
  }

  toggleEditRole(role: string, checked: boolean): void {
    const roles = new Set(this.editRoles());
    if (checked) {
      if (role === 'Admin' && !confirm('Grant Admin access? Admins can manage every user and setting for this tenant.')) {
        return;
      }
      roles.add(role);
    } else {
      roles.delete(role);
    }
    this.editRoles.set(roles);
  }

  async saveEdit(userId: string): Promise<void> {
    const roles = Array.from(this.editRoles());
    if (roles.length === 0) {
      this.errorMessage.set('A user needs at least one role.');
      return;
    }
    this.submitting.set(true);
    this.errorMessage.set('');
    try {
      await this.api.updateUser(userId, { roles, location_id: this.editLocationId || undefined });
      this.editingUserId.set(null);
      this.successMessage.set('User updated.');
      await this.refresh();
    } catch (err) {
      this.errorMessage.set(this.extractError(err));
    } finally {
      this.submitting.set(false);
    }
  }

  async removeUser(user: AdminUser): Promise<void> {
    if (!confirm(`Remove ${user.email}? They will lose access immediately.`)) {
      return;
    }
    this.errorMessage.set('');
    this.successMessage.set('');
    try {
      await this.api.removeUser(user.id);
      this.successMessage.set(`${user.email} was removed.`);
      await this.refresh();
    } catch (err) {
      this.errorMessage.set(this.extractError(err));
    }
  }

  private extractError(err: unknown): string {
    return (err as { error?: { detail?: string } })?.error?.detail ?? 'Something went wrong.';
  }
}
