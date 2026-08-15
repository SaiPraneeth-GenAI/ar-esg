import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { AdminUser, ApiService } from '../../../core/api.service';

interface RoleInfo {
  key: string;
  label: string;
  description: string;
}

const ROLE_INFO: RoleInfo[] = [
  {
    key: 'Admin',
    label: 'Admin',
    description: 'Full platform access. Can manage users, roles, and plants, and sees everything across the tenant.'
  },
  {
    key: 'Manager',
    label: 'Manager',
    description: 'Oversees plant-level data entry and reporting for the plants they are assigned to.'
  },
  {
    key: 'Approver',
    label: 'Approver',
    description: 'Reviews submitted data entries and approves or rejects them before they count toward rollups.'
  }
];

@Component({
  selector: 'app-user-roles',
  standalone: true,
  imports: [FormsModule],
  templateUrl: './user-roles.component.html',
  styleUrl: './user-roles.component.css'
})
export class UserRolesComponent implements OnInit {
  private api = inject(ApiService);

  roles = ROLE_INFO;
  users = signal<AdminUser[]>([]);
  loading = signal(true);
  errorMessage = signal('');
  successMessage = signal('');
  addSelection = signal<Record<string, string>>({});

  usersByRole = computed(() => {
    const map: Record<string, AdminUser[]> = {};
    for (const role of this.roles) {
      map[role.key] = this.users().filter((u) => u.roles.includes(role.key));
    }
    return map;
  });

  candidatesByRole = computed(() => {
    const map: Record<string, AdminUser[]> = {};
    for (const role of this.roles) {
      map[role.key] = this.users().filter((u) => !u.roles.includes(role.key));
    }
    return map;
  });

  async ngOnInit(): Promise<void> {
    await this.refresh();
  }

  async refresh(): Promise<void> {
    this.loading.set(true);
    this.errorMessage.set('');
    try {
      this.users.set(await this.api.listUsers());
    } catch {
      this.errorMessage.set('Could not load users.');
    } finally {
      this.loading.set(false);
    }
  }

  selectedCandidate(roleKey: string): string {
    return this.addSelection()[roleKey] ?? '';
  }

  setSelectedCandidate(roleKey: string, userId: string): void {
    this.addSelection.set({ ...this.addSelection(), [roleKey]: userId });
  }

  async addToRole(roleKey: string): Promise<void> {
    const userId = this.selectedCandidate(roleKey);
    if (!userId) {
      return;
    }
    const user = this.users().find((u) => u.id === userId);
    if (!user) {
      return;
    }
    this.errorMessage.set('');
    this.successMessage.set('');
    try {
      await this.api.updateUser(userId, { roles: [...user.roles, roleKey] });
      this.setSelectedCandidate(roleKey, '');
      this.successMessage.set(`${user.email} now has the ${roleKey} role.`);
      await this.refresh();
    } catch (err) {
      this.errorMessage.set(this.extractError(err));
    }
  }

  async removeFromRole(user: AdminUser, roleKey: string): Promise<void> {
    const remaining = user.roles.filter((r) => r !== roleKey);
    if (remaining.length === 0) {
      this.errorMessage.set(`${user.email} needs at least one role -- assign another role before removing ${roleKey}.`);
      return;
    }
    if (!confirm(`Remove the ${roleKey} role from ${user.email}?`)) {
      return;
    }
    this.errorMessage.set('');
    this.successMessage.set('');
    try {
      await this.api.updateUser(user.id, { roles: remaining });
      this.successMessage.set(`Removed ${roleKey} from ${user.email}.`);
      await this.refresh();
    } catch (err) {
      this.errorMessage.set(this.extractError(err));
    }
  }

  private extractError(err: unknown): string {
    return (err as { error?: { detail?: string } })?.error?.detail ?? 'Something went wrong.';
  }
}
