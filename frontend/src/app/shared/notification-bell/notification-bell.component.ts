import { Component, HostListener, OnDestroy, OnInit, computed, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { NotificationRecord, NotificationsApiService } from '../../core/notifications-api.service';

const POLL_MS = 45_000;

@Component({
  selector: 'app-notification-bell',
  standalone: true,
  templateUrl: './notification-bell.component.html',
  styleUrl: './notification-bell.component.css'
})
export class NotificationBellComponent implements OnInit, OnDestroy {
  private api = inject(NotificationsApiService);
  private router = inject(Router);
  private pollHandle?: ReturnType<typeof setInterval>;

  open = signal(false);
  notifications = signal<NotificationRecord[]>([]);
  unreadCount = signal(0);
  loading = signal(false);

  hasUnread = computed(() => this.unreadCount() > 0);
  badgeLabel = computed(() => (this.unreadCount() > 9 ? '9+' : String(this.unreadCount())));

  async ngOnInit(): Promise<void> {
    await this.refresh();
    this.pollHandle = setInterval(() => this.refresh(), POLL_MS);
  }

  ngOnDestroy(): void {
    if (this.pollHandle) clearInterval(this.pollHandle);
  }

  async refresh(): Promise<void> {
    try {
      const result = await this.api.list();
      this.notifications.set(result.notifications);
      this.unreadCount.set(result.unread_count);
    } catch {
      // Silent -- a failed poll shouldn't interrupt whatever else the user is doing.
    }
  }

  toggle(event: Event): void {
    event.stopPropagation();
    this.open.update((v) => !v);
    if (this.open()) {
      this.refresh();
    }
  }

  @HostListener('document:click')
  onDocumentClick(): void {
    this.open.set(false);
  }

  async selectNotification(n: NotificationRecord): Promise<void> {
    this.open.set(false);
    if (n.read_at === null) {
      this.unreadCount.update((c) => Math.max(0, c - 1));
      n.read_at = new Date().toISOString();
      try {
        await this.api.markRead(n.id);
      } catch {
        // Best-effort -- the badge already updated optimistically.
      }
    }
    if (n.link) {
      this.router.navigateByUrl(n.link);
    }
  }

  async markAllRead(event: Event): Promise<void> {
    event.stopPropagation();
    this.notifications.update((list) => list.map((n) => ({ ...n, read_at: n.read_at ?? new Date().toISOString() })));
    this.unreadCount.set(0);
    try {
      await this.api.markAllRead();
    } catch {
      // Best-effort -- optimistic UI already reflects "all read".
    }
  }

  relativeTime(iso: string): string {
    const diffMs = Date.now() - new Date(iso).getTime();
    const minutes = Math.floor(diffMs / 60_000);
    if (minutes < 1) return 'just now';
    if (minutes < 60) return `${minutes}m ago`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours}h ago`;
    const days = Math.floor(hours / 24);
    return `${days}d ago`;
  }
}
