import { DecimalPipe } from '@angular/common';
import { Component, EventEmitter, OnInit, Output, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { AdminLocation, AdminUser, ApiService } from '../../../core/api.service';
import { BaselinePreviewResponse, MonthlyPhaseEntry, TargetableMetric, TargetApiService } from '../../../core/target-api.service';

function currentYear(): number {
  return new Date().getFullYear();
}

@Component({
  selector: 'app-target-wizard',
  standalone: true,
  imports: [FormsModule, DecimalPipe],
  templateUrl: './target-wizard.component.html',
  styleUrl: './target-wizard.component.css'
})
export class TargetWizardComponent implements OnInit {
  private targetApi = inject(TargetApiService);
  private api = inject(ApiService);

  @Output() closed = new EventEmitter<void>();
  @Output() saved = new EventEmitter<void>();

  // Two screens: pick a metric, then set its value. Baseline is computed
  // and locked underneath (the backend needs it to score performance
  // later), but it's fetched automatically the instant a metric+year is
  // picked instead of being a step the user has to read and understand.
  step = signal<1 | 2>(1);
  submitting = signal(false);
  errorMessage = signal('');

  locations = signal<AdminLocation[]>([]);
  users = signal<AdminUser[]>([]);
  metrics = signal<TargetableMetric[]>([]);

  metricGroups(): string[] {
    return Array.from(new Set(this.metrics().map((m) => m.group)));
  }

  metricsInGroup(group: string): TargetableMetric[] {
    return this.metrics().filter((m) => m.group === group);
  }

  locationId = signal<string>('');
  metricKey = signal<string>('');
  selectedMetric = computed(() => this.metrics().find((m) => m.key === this.metricKey()));

  /** A GHG metric (Scope 1/2/1+2) is a budget -- a plain total, spread
   * evenly across months by default. Every intensity metric is a rate --
   * the same figure applies every month, so there's nothing to "spread". */
  isRateMetric = computed(() => this.selectedMetric()?.group !== 'GHG');

  today = new Date();
  baselineYear = signal<number>(currentYear() - 1);
  targetYear = signal<number>(currentYear() + 1);
  baselinePreview = signal<BaselinePreviewResponse | null>(null);
  baselineLoading = signal(false);

  reductionPercentage = signal<number | null>(10);
  targetValue = signal<number | null>(null);
  ownerId = signal<string>('');
  rationale = signal('');
  phaseMonthly = signal(false);
  phasedMonths = signal<MonthlyPhaseEntry[]>([]);
  showReductionHelper = signal(false);

  /** What the % helper would produce -- shown as a suggestion, only
   * written into targetValue() when the user explicitly applies it. */
  suggestedFromReduction = computed<number | null>(() => {
    const baseline = this.baselinePreview()?.baseline_value;
    const pct = this.reductionPercentage();
    if (baseline === null || baseline === undefined || pct === null) return null;
    return baseline * (1 - pct / 100);
  });

  phasedTotal = computed(() => this.phasedMonths().reduce((sum, m) => sum + (m.value || 0), 0));
  phasedMismatch = computed(() => {
    const target = this.targetValue();
    if (target === null) return false;
    return Math.abs(this.phasedTotal() - target) > 0.01;
  });

  async ngOnInit(): Promise<void> {
    const [locations, users, metrics] = await Promise.all([
      this.api.listLocations(),
      this.api.listUsers(),
      this.targetApi.listMetrics()
    ]);
    this.locations.set(locations);
    this.users.set(users);
    this.metrics.set(metrics);
  }

  yearOptions(fromOffset: number, toOffset: number): number[] {
    const y = currentYear();
    const years: number[] = [];
    for (let i = fromOffset; i <= toOffset; i++) years.push(y + i);
    return years;
  }

  async selectMetric(key: string): Promise<void> {
    this.metricKey.set(key);
    this.step.set(2);
    this.phaseMonthly.set(false);
    this.regeneratePhasing();
    await this.refreshBaseline();
  }

  backToStep1(): void {
    this.step.set(1);
  }

  async onBaselineYearChange(year: number): Promise<void> {
    this.baselineYear.set(year);
    await this.refreshBaseline();
  }

  onTargetYearChange(year: number): void {
    this.targetYear.set(year);
    this.regeneratePhasing();
  }

  async refreshBaseline(): Promise<void> {
    if (!this.metricKey()) return;
    this.baselineLoading.set(true);
    this.errorMessage.set('');
    try {
      this.baselinePreview.set(
        await this.targetApi.baselinePreview({
          location_id: this.locationId() || null,
          metric_key: this.metricKey(),
          baseline_period_start: `${this.baselineYear()}-01-01`,
          baseline_period_end: `${this.baselineYear()}-12-01`
        })
      );
    } catch {
      this.errorMessage.set('Could not compute the baseline for this metric.');
    } finally {
      this.baselineLoading.set(false);
    }
  }

  applySuggestedValue(): void {
    const suggested = this.suggestedFromReduction();
    if (suggested !== null) {
      this.targetValue.set(Math.round(suggested * 1000) / 1000);
      this.regeneratePhasing();
    }
  }

  togglePhasing(): void {
    this.phaseMonthly.set(!this.phaseMonthly());
    if (this.phaseMonthly()) this.regeneratePhasing();
  }

  regeneratePhasing(): void {
    const year = this.targetYear();
    const target = this.targetValue();
    const rate = this.isRateMetric();
    const perMonth = target !== null ? (rate ? target : target / 12) : 0;
    this.phasedMonths.set(
      Array.from({ length: 12 }, (_, i) => ({
        period: `${year}-${String(i + 1).padStart(2, '0')}-01`,
        value: Math.round(perMonth * 1000) / 1000
      }))
    );
  }

  updatePhaseValue(index: number, value: number): void {
    const months = [...this.phasedMonths()];
    months[index] = { ...months[index], value };
    this.phasedMonths.set(months);
  }

  canActivate(): boolean {
    if (this.targetValue() === null || !this.rationale().trim()) return false;
    if (this.phaseMonthly() && this.phasedMismatch()) return false;
    return this.baselinePreview()?.ready ?? false;
  }

  private buildPayload() {
    return {
      location_id: this.locationId() || null,
      metric_key: this.metricKey(),
      baseline_period_start: `${this.baselineYear()}-01-01`,
      baseline_period_end: `${this.baselineYear()}-12-01`,
      target_period_start: `${this.targetYear()}-01-01`,
      target_period_end: `${this.targetYear()}-12-01`,
      reduction_percentage: this.reductionPercentage(),
      target_value: this.targetValue(),
      monthly_phasing: this.phaseMonthly() && !this.isRateMetric() ? this.phasedMonths() : [],
      owner_id: this.ownerId() || null,
      rationale: this.rationale() || null
    };
  }

  async saveDraft(): Promise<void> {
    this.submitting.set(true);
    this.errorMessage.set('');
    try {
      await this.targetApi.create(this.buildPayload());
      this.saved.emit();
    } catch {
      this.errorMessage.set('Could not save this target as a draft.');
    } finally {
      this.submitting.set(false);
    }
  }

  async saveAndActivate(): Promise<void> {
    this.submitting.set(true);
    this.errorMessage.set('');
    try {
      const created = await this.targetApi.create(this.buildPayload());
      await this.targetApi.activate(created.id, this.rationale());
      this.saved.emit();
    } catch (err: any) {
      this.errorMessage.set(err?.error?.detail ?? 'Could not activate this target.');
    } finally {
      this.submitting.set(false);
    }
  }

  close(): void {
    this.closed.emit();
  }
}
