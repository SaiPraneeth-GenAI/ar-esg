from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from fastapi import HTTPException


GRID_FACTOR_KGCO2E_PER_KWH = Decimal("0.710")


def assert_tenant(record_tenant_id, current_tenant_id, label: str = "Record") -> None:
    """Shared IDOR guard for every Energy Assurance record lookup."""
    if record_tenant_id != current_tenant_id:
        raise HTTPException(status_code=404, detail=f"{label} not found")


def normalize_energy(value, unit: str) -> Decimal | None:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    normalized = unit.strip().lower().replace(" ", "")
    if normalized == "kwh":
        return amount
    if normalized == "mwh":
        return amount * Decimal("1000")
    if normalized == "wh":
        return amount / Decimal("1000")
    return None


@dataclass(frozen=True)
class ReconciliationResult:
    actual_kwh: Decimal
    reference_kwh: Decimal | None
    variance_kwh: Decimal | None
    variance_pct: Decimal | None
    status: str
    message: str


def reconcile_energy(actual_values_kwh: list[Decimal], reference_value_kwh: Decimal | None) -> ReconciliationResult:
    actual = sum(actual_values_kwh, Decimal("0"))
    if reference_value_kwh is None:
        return ReconciliationResult(actual, None, None, None, "warning", "No independent reference is attached.")
    variance = actual - reference_value_kwh
    variance_pct = (abs(variance) / reference_value_kwh * Decimal("100")) if reference_value_kwh else None
    if variance_pct is None:
        return ReconciliationResult(actual, reference_value_kwh, variance, None, "warning", "Reference value is zero.")
    if variance_pct <= Decimal("2"):
        status, message = "passed", "Meter total is within the 2% demonstration tolerance."
    elif variance_pct <= Decimal("5"):
        status, message = "warning", "Variance needs review before reporting."
    else:
        status, message = "failed", "Variance exceeds the 5% demonstration tolerance."
    return ReconciliationResult(actual, reference_value_kwh, variance, variance_pct, status, message)


def location_scope2(grid_kwh: list[Decimal], factor: Decimal = GRID_FACTOR_KGCO2E_PER_KWH) -> tuple[Decimal, str]:
    activity = sum(grid_kwh, Decimal("0"))
    tonnes = activity * factor / Decimal("1000")
    return tonnes, f"{activity} kWh × {factor} kgCO2e/kWh ÷ 1000"
