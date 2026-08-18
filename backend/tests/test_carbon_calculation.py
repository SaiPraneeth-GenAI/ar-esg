"""Unit tests for the DB-free pure functions in carbon_calculation.py --
unit normalization and formula execution. No database required."""

from decimal import Decimal

from app.services.carbon_calculation import (
    UnresolvedResult,
    compute_fuel_emissions,
    compute_grid_emissions,
    compute_gwp_emissions,
    normalize_fuel_activity,
    normalize_grid_activity,
    normalize_gwp_activity,
    to_decimal,
)


def test_to_decimal_avoids_float_binary_imprecision():
    # 0.1 + 0.2 != 0.3 in binary float -- to_decimal must route through
    # str() so this never leaks into a stored calculation value.
    d = to_decimal(0.1) + to_decimal(0.2)
    assert d == Decimal("0.3")


def test_normalize_fuel_activity_matching_unit_no_conversion():
    result = normalize_fuel_activity(Decimal("100"), "litres", "kg CO2e/litre", density_kg_per_unit=None)
    assert result == (Decimal("100"), "litre")


def test_normalize_fuel_activity_kg_unit_matches_kg_factor():
    result = normalize_fuel_activity(Decimal("50"), "kg", "kg CO2e/kg", density_kg_per_unit=None)
    assert result == (Decimal("50"), "kg")


def test_normalize_fuel_activity_kg_to_litre_with_density():
    # 84.8 kg at density 0.848 kg/L -> 100 litres
    result = normalize_fuel_activity(Decimal("84.8"), "kg", "kg CO2e/litre", density_kg_per_unit=Decimal("0.848"))
    assert result == (Decimal("100"), "litre")


def test_normalize_fuel_activity_mismatch_without_density_is_unresolved():
    result = normalize_fuel_activity(Decimal("100"), "kg", "kg CO2e/litre", density_kg_per_unit=None)
    assert isinstance(result, UnresolvedResult)
    assert result.reason_code == "unit_mismatch"


def test_normalize_fuel_activity_unrecognized_unit_is_unresolved():
    result = normalize_fuel_activity(Decimal("100"), "MWh", "kg CO2e/litre", density_kg_per_unit=None)
    assert isinstance(result, UnresolvedResult)


def test_normalize_fuel_activity_tco2e_per_tonne_factor_matches_kg_activity():
    # Coal (and other solid fuels) are conventionally factored as tCO2e/t --
    # dimensionally identical to kgCO2e/kg, so a kg-recorded entry resolves
    # against it directly with no scaling.
    result = normalize_fuel_activity(Decimal("500"), "kg", "tCO2e/t", density_kg_per_unit=None)
    assert result == (Decimal("500"), "kg")


def test_normalize_grid_activity_kwh_to_mwh():
    value, unit = normalize_grid_activity(Decimal("5000"), "kWh")
    assert value == Decimal("5")
    assert unit == "MWh"


def test_normalize_grid_activity_already_mwh():
    value, unit = normalize_grid_activity(Decimal("5"), "MWh")
    assert value == Decimal("5")
    assert unit == "MWh"


def test_normalize_grid_activity_unrecognized_unit():
    result = normalize_grid_activity(Decimal("5"), "kg")
    assert isinstance(result, UnresolvedResult)


def test_normalize_gwp_activity_kg_ok():
    value, unit = normalize_gwp_activity(Decimal("2.5"), "kg")
    assert value == Decimal("2.5")
    assert unit == "kg"


def test_normalize_gwp_activity_non_kg_unresolved():
    result = normalize_gwp_activity(Decimal("2.5"), "litres")
    assert isinstance(result, UnresolvedResult)


def test_compute_fuel_emissions():
    kgco2e, formula = compute_fuel_emissions(Decimal("100"), Decimal("2.697"), "litre")
    assert kgco2e == Decimal("269.700")
    assert "100" in formula and "2.697" in formula


def test_compute_gwp_emissions():
    # 2.5 kg of R-134a leaked, GWP-100 = 1530 -> 3825 kgCO2e
    kgco2e, formula = compute_gwp_emissions(Decimal("2.5"), Decimal("1530"))
    assert kgco2e == Decimal("3825.0")


def test_compute_grid_emissions_matches_shortcut_identity():
    # 5000 kWh = 5 MWh; at 0.710 tCO2e/MWh -> 3.55 tCO2e = 3550 kgCO2e.
    # Also confirms the kWh-in/kgCO2e-out numeric identity noted in the
    # design: kgCO2e == raw_kWh_value * factor_value(t/MWh).
    mwh, _ = normalize_grid_activity(Decimal("5000"), "kWh")
    kgco2e, formula = compute_grid_emissions(mwh, Decimal("0.710"))
    assert kgco2e == Decimal("3550.000")
    assert kgco2e == Decimal("5000") * Decimal("0.710")


def test_emissions_are_decimal_not_float():
    kgco2e, _ = compute_fuel_emissions(Decimal("100"), Decimal("2.697"), "litre")
    assert isinstance(kgco2e, Decimal)
    assert not isinstance(kgco2e, float)
