import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { AdminLocation, ApiService } from '../../../core/api.service';

@Component({
  selector: 'app-assigned-plants',
  standalone: true,
  imports: [FormsModule],
  templateUrl: './assigned-plants.component.html',
  styleUrl: './assigned-plants.component.css'
})
export class AssignedPlantsComponent implements OnInit {
  private api = inject(ApiService);

  plants = signal<AdminLocation[]>([]);
  loading = signal(true);
  errorMessage = signal('');
  successMessage = signal('');
  submitting = signal(false);

  newName = '';

  editingId = signal<string | null>(null);
  editName = '';

  async ngOnInit(): Promise<void> {
    await this.refresh();
  }

  async refresh(): Promise<void> {
    this.loading.set(true);
    this.errorMessage.set('');
    try {
      this.plants.set(await this.api.listLocations());
    } catch {
      this.errorMessage.set('Could not load plants.');
    } finally {
      this.loading.set(false);
    }
  }

  async addPlant(): Promise<void> {
    if (!this.newName.trim()) {
      return;
    }
    this.errorMessage.set('');
    this.successMessage.set('');
    this.submitting.set(true);
    try {
      await this.api.createLocation(this.newName.trim());
      this.successMessage.set(`${this.newName.trim()} was added.`);
      this.newName = '';
      await this.refresh();
    } catch (err) {
      this.errorMessage.set(this.extractError(err));
    } finally {
      this.submitting.set(false);
    }
  }

  startEdit(plant: AdminLocation): void {
    this.editingId.set(plant.id);
    this.editName = plant.name;
  }

  cancelEdit(): void {
    this.editingId.set(null);
  }

  async saveEdit(id: string): Promise<void> {
    if (!this.editName.trim()) {
      return;
    }
    this.errorMessage.set('');
    try {
      await this.api.renameLocation(id, this.editName.trim());
      this.editingId.set(null);
      await this.refresh();
    } catch (err) {
      this.errorMessage.set(this.extractError(err));
    }
  }

  async removePlant(plant: AdminLocation): Promise<void> {
    if (!confirm(`Remove ${plant.name}? This can't be undone.`)) {
      return;
    }
    this.errorMessage.set('');
    this.successMessage.set('');
    try {
      await this.api.removeLocation(plant.id);
      this.successMessage.set(`${plant.name} was removed.`);
      await this.refresh();
    } catch (err) {
      this.errorMessage.set(this.extractError(err));
    }
  }

  private extractError(err: unknown): string {
    return (err as { error?: { detail?: string } })?.error?.detail ?? 'Something went wrong.';
  }
}
