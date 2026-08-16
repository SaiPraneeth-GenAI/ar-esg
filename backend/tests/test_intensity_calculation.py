"""Unit tests for the DB-free pure functions in intensity_calculation.py --
fuel-to-energy conversion and the ratio() no-invented-numbers guard. No
database required."""

from decimal import Decimal

from app.services.intensity_calculation import fuel_energy_mj, ratio


def test_fuel_energy_mj_kg_basis_no_density_needed():
    # LPG is recorded in kg -- NCV applies directly, no density conversion.
    mj = fuel_energy_mj(Decimal("100"), "kg", ncv_mj_per_unit=Decimal("46.3"), density_kg_per_unit=None)
    assert mj == Decimal("4630.0")


def test_fuel_energy_mj_litre_basis_converts_via_density():
    # Diesel: 100 litres at density 0.832 kg/L = 83.2 kg, x NCV 45.4 MJ/kg.
    mj = fuel_energy_mj(Decimal("100"), "litres", ncv_mj_per_unit=Decimal("45.4"), density_kg_per_unit=Decimal("0.832"))
    assert mj == Decimal("83.2") * Decimal("45.4")


def test_fuel_energy_mj_litre_basis_without_density_is_excluded_not_guessed():
    mj = fuel_energy_mj(Decimal("100"), "litres", ncv_mj_per_unit=Decimal("45.4"), density_kg_per_unit=None)
    assert mj is None


def test_fuel_energy_mj_unrecognized_unit_is_excluded():
    mj = fuel_energy_mj(Decimal("100"), "MWh", ncv_mj_per_unit=Decimal("45.4"), density_kg_per_unit=None)
    assert mj is None


def test_ratio_divides_when_both_present():
    assert ratio(45.0, 10.0) == 4.5


def test_ratio_none_when_numerator_missing():
    assert ratio(None, 10.0) is None


def test_ratio_none_when_denominator_missing():
    assert ratio(45.0, None) is None


def test_ratio_none_when_denominator_zero():
    assert ratio(45.0, 0) is None


def test_ratio_avoids_float_binary_imprecision():
    # 0.1 tCO2e / 3 shouldn't pick up float-division drift beyond what
    # Decimal division would produce.
    result = ratio(0.3, 0.1)
    assert abs(result - 3.0) < 1e-9
