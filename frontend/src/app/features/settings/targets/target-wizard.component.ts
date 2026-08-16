import { DecimalPipe } from '@angular/common';
import { Component, EventEmitter, OnInit, Output, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { AdminLocation, AdminUser, ApiService } from '../../../core/api.service';
import {
  BaselinePreviewResponse,
  MonthlyPhaseEntry,
  TargetApiService,
  TargetMetricType,
  TargetScope
} from '../../../core/target-api.service';

interface Preset {
  label: string;
  description: string;
  scope: TargetScope;
  calculationMethod: string | null;
  metricType: TargetMetricType;
}

const PRESETS: Preset[] = [
  {
    label: 'Intensity by production',
    description: 'Scope 1+2 location-based, per Mn Ah of battery production -- the primary target most tenants track',
    scope: '1_2_combined',
    calculationMethod: 'location_based',
    metricType: 'intensity_tco2e_per_mnah'
  },
  {
    label: 'Intensity by revenue',
    description: 'Scope 1+2 location-based, per INR crore of revenue',
    scope: '1_2_combined',
    calculationMethod: 'location_based',
    metricType: 'intensity_tco2e_per_revenue'
  },
  {
    label: 'Absolute guardrail',
    description: 'Scope 1+2 location-based total (tCO2e) -- so production growth alone can\'t hide an absolute increase',
    scope: '1_2_combined',
    calculationMethod: 'location_based',
    metricType: 'absolute_tco2e'
  },
  {
    label: 'Disclosure target',
    description: 'Scope 2 market-based total (tCO2e) -- shown beside, never instead of, location-based',
    scope: '2',
    calculationMethod: 'market_based',
    metricType: 'absolute_tco2e'
  }
];

function monthStr(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
}

function addMonths(base: string, delta: number): string {
  const [y, m] = base.split('-').map(Number);
  const d = new Date(y, m - 1 + delta, 1);
  return monthStr(d);
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

  presets = PRESETS;
  step = signal<1 | 2 | 3>(1);
  submitting = signal(false);
  errorMessage = signal('');

  locations = signal<AdminLocation[]>([]);
  users = signal<AdminUser[]>([]);

  // Step 1
  locationId = signal<string>('');
  scope = signal<TargetScope>('1_2_combined');
  calculationMethod = signal<string | null>('location_based');
  metricType = signal<TargetMetricType>('intensity_tco2e_per_mnah');

  intensityDisabled = computed(() => this.scope() !== '1_2_combined');
  customizeBoundary = signal(false);
  showAdvanced = signal(false);
  showBaselineMonths = signal(false);

  metricUnit(): string {
    if (this.metricType() === 'intensity_tco2e_per_mnah') return 'tCO2e/MnAh';
    if (this.metricType() === 'intensity_tco2e_per_revenue') return 'tCO2e/Cr';
    return 'tCO2e';
  }

  // Step 2
  today = new Date();
  baselineEnd = signal<string>(monthStr(new Date(this.today.getFullYear(), this.today.getMonth() - 1, 1)));
  baselineStart = signal<string>(addMonths(monthStr(new Date(this.today.getFullYear(), this.today.getMonth() - 1, 1)), -11));
  baselinePreview = signal<BaselinePreviewResponse | null>(null);
  baselineLoading = signal(false);

  // Step 3
  targetStart = signal<string>(monthStr(this.today));
  targetEnd = signal<string>(addMonths(monthStr(this.today), 11));
  reductionPercentage = signal<number | null>(10);
  targetValueOverride = signal<number | null>(null);
  ownerId = signal<string>('');
  rationale = signal('');
  phaseMonthly = signal(false);
  phasedMonths = signal<MonthlyPhaseEntry[]>([]);

  computedTargetValue = computed<number | null>(() => {
    if (this.targetValueOverride() !== null) return this.targetValueOverride();
    const baseline = this.baselinePreview()?.baseline_value;
    const pct = this.reductionPercentage();
    if (baseline === null || baseline === undefined || pct === null) return null;
    return baseline * (1 - pct / 100);
  });

  phasedTotal = computed(() => this.phasedMonths().reduce((sum, m) => sum + (m.value || 0), 0));
  phasedMismatch = computed(() => {
    const target = this.computedTargetValue();
    if (target === null) return false;
    return Math.abs(this.phasedTotal() - target) > 0.01;
  });

  async ngOnInit(): Promise<void> {
    const [locations, users] = await Promise.all([this.api.listLocations(), this.api.listUsers()]);
    this.locations.set(locations);
    this.users.set(users);
  }

  selectedPresetLabel = signal<string | null>(null);

  async applyPreset(preset: Preset): Promise<void> {
    this.scope.set(preset.scope);
    this.calculationMethod.set(preset.calculationMethod);
    this.metricType.set(preset.metricType);
    this.selectedPresetLabel.set(preset.label);
    // A preset already fully specifies the boundary -- jump straight to
    // the baseline instead of making the user click through a form
    // they've already answered via the card they just picked.
    await this.goToStep2();
  }

  onScopeChange(scope: TargetScope): void {
    this.scope.set(scope);
    this.selectedPresetLabel.set(null);
    if (scope !== '1_2_combined' && this.metricType() !== 'absolute_tco2e') {
      this.metricType.set('absolute_tco2e');
    }
    if (scope === '1') {
      this.calculationMethod.set(null);
    } else if (this.calculationMethod() === null) {
      this.calculationMethod.set('location_based');
    }
  }

  async goToStep2(): Promise<void> {
    this.step.set(2);
    await this.refreshBaseline();
  }

  async refreshBaseline(): Promise<void> {
    this.baselineLoading.set(true);
    this.errorMessage.set('');
    try {
      this.baselinePreview.set(
        await this.targetApi.baselinePreview({
          location_id: this.locationId() || null,
          scope: this.scope(),
          calculation_method: this.calculationMethod(),
          metric_type: this.metricType(),
          baseline_period_start: `${this.baselineStart()}-01`,
          baseline_period_end: `${this.baselineEnd()}-01`
        })
      );
    } catch {
      this.errorMessage.set('Could not compute the baseline for this boundary.');
    } finally {
      this.baselineLoading.set(false);
    }
  }

  goToStep3(): void {
    this.step.set(3);
    this.regeneratePhasing();
  }

  backToStep(step: 1 | 2): void {
    this.step.set(step);
  }

  togglePhasing(): void {
    this.phaseMonthly.set(!this.phaseMonthly());
    if (this.phaseMonthly()) this.regeneratePhasing();
  }

  private monthsInTargetPeriod(): string[] {
    const months: string[] = [];
    let cursor = this.targetStart();
    while (cursor <= this.targetEnd()) {
      months.push(cursor);
      cursor = addMonths(cursor, 1);
    }
    return months;
  }

  regeneratePhasing(): void {
    const months = this.monthsInTargetPeriod();
    const target = this.computedTargetValue();
    const even = target !== null ? target / months.length : 0;
    this.phasedMonths.set(months.map((m) => ({ period: `${m}-01`, value: Math.round(even * 1000) / 1000 })));
  }

  updatePhaseValue(index: number, value: number): void {
    const months = [...this.phasedMonths()];
    months[index] = { ...months[index], value };
    this.phasedMonths.set(months);
  }

  canActivate(): boolean {
    const target = this.computedTargetValue();
    if (target === null || !this.rationale().trim()) return false;
    if (this.phaseMonthly() && this.phasedMismatch()) return false;
    return this.baselinePreview()?.ready ?? false;
  }

  private buildPayload() {
    return {
      location_id: this.locationId() || null,
      scope: this.scope(),
      calculation_method: this.calculationMethod(),
      metric_type: this.metricType(),
      baseline_period_start: `${this.baselineStart()}-01`,
      baseline_period_end: `${this.baselineEnd()}-01`,
      target_period_start: `${this.targetStart()}-01`,
      target_period_end: `${this.targetEnd()}-01`,
      reduction_percentage: this.reductionPercentage(),
      target_value: this.computedTargetValue(),
      monthly_phasing: this.phaseMonthly() ? this.phasedMonths() : [],
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
