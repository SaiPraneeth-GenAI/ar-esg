"""Unit tests for the DB-free unit_conversion module. No database required."""

from app.core.unit_conversion import convert_unit, units_equivalent


def test_units_equivalent_exact_match():
    assert units_equivalent("litres", "litres")


def test_units_equivalent_spelling_variant():
    assert units_equivalent("Liters", "litres")
    assert units_equivalent("KG", "kg")


def test_units_equivalent_false_for_different_families():
    assert not units_equivalent("litres", "kg")


def test_units_equivalent_false_for_unknown_unit():
    assert not units_equivalent("Rate", "litres")


def test_convert_unit_same_family_kilolitres_to_litres():
    assert convert_unit(1.5, "KL", "litres") == 1500.0


def test_convert_unit_same_family_tonnes_to_kg():
    assert convert_unit(2, "MT", "kg") == 2000.0


def test_convert_unit_mwh_to_kwh():
    assert convert_unit(1, "MWh", "kWh") == 1000.0


def test_convert_unit_identical_unit_returns_value_unchanged():
    assert convert_unit(42.0, "litres", "litres") == 42.0


def test_convert_unit_returns_none_for_different_families():
    assert convert_unit(1, "litres", "kg") is None


def test_convert_unit_returns_none_for_unrecognized_unit():
    assert convert_unit(1, "Rate", "litres") is None


def test_convert_unit_round_trip():
    litres = convert_unit(2000, "kg", "MT")
    assert litres == 2.0
