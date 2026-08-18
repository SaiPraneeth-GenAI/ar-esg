import { Injectable, signal } from '@angular/core';

export type ToastType = 'success' | 'error' | 'info';

export interface Toast {
  id: number;
  message: string;
  type: ToastType;
}

/** App-wide "did it work" feedback -- mounted once (see ToastContainerComponent
 * in admin-layout) so any component can fire a toast without owning UI for it,
 * which matters most for long-running actions (large bulk uploads) where the
 * user may have already moved to another tab by the time the result lands. */
@Injectable({ providedIn: 'root' })
export class ToastService {
  private nextId = 1;
  toasts = signal<Toast[]>([]);

  show(message: string, type: ToastType = 'info', durationMs = 6000): void {
    const id = this.nextId++;
    this.toasts.update((list) => [...list, { id, message, type }]);
    setTimeout(() => this.dismiss(id), durationMs);
  }

  dismiss(id: number): void {
    this.toasts.update((list) => list.filter((t) => t.id !== id));
  }
}
