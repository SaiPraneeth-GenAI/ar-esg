import { Component, HostListener, OnDestroy, OnInit, computed, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { EntriesApiService } from '../../core/entries-api.service';
import { NotificationRecord, NotificationsApiService } from '../../core/notifications-api.service';
import { ToastService } from '../../core/toast.service';

// "approval_queue" (new entries awaiting approval) and "entries_approved"
// (an FYI that a decision was already made) both point at state that can
// go stale between the notification firing and the click -- someone else
// clears the queue, or there's simply nothing further to do about an
// approval that already happened. "entries_rejected" is the one kind that
// always still needs the submitter to act (fix and resubmit), so it never
// gets the "already completed" treatment.
const STALE_CHECK_KINDS = new Set(['approval_queue', 'entries_approved']);

const POLL_MS = 45_000;

@Component({
  selector: 'app-notification-bell',
  standalone: true,
  templateUrl: './notification-bell.component.html',
  styleUrl: './notification-bell.component.css'
})
export class NotificationBellComponent implements OnInit, OnDestroy {
  private api = inject(NotificationsApiService);
  private entriesApi = inject(EntriesApiService);
  private toast = inject(ToastService);
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

    if (STALE_CHECK_KINDS.has(n.kind) && (await this.isAlreadyDone(n))) {
      this.toast.show('Workflow already completed.', 'info');
      this.router.navigateByUrl('/admin/data-entry');
      return;
    }

    if (n.link) {
      this.router.navigateByUrl(n.link);
    }
  }

  // "entries_approved" is itself the record of a finished decision -- no
  // live check needed, an approval doesn't un-approve itself. "approval_queue"
  // depends on whether anything is still actually waiting -- someone else
  // may have cleared it since the notification fired.
  private async isAlreadyDone(n: NotificationRecord): Promise<boolean> {
    if (n.kind === 'entries_approved') return true;
    if (n.kind === 'approval_queue') {
      try {
        const queue = await this.entriesApi.getQueue();
        return queue.length === 0;
      } catch {
        return false; // can't tell -- fall through to the normal link rather than block navigation
      }
    }
    return false;
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
