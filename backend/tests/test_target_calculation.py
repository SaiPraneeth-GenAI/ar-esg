"""Unit tests for the DB-free pure functions in target_calculation.py --
boundary hashing, monthly phasing validation, month-spreading, and
actual-vs-target status classification. extract_metric_value/compute_baseline
now delegate to compute_range_totals/compute_intensity_overview_range (real
queries) so they're exercised via the API test suite instead, not here."""

from datetime import date

from app.services.target_calculation import (
    RATE_METRIC_KEYS,
    TARGETABLE_METRIC_KEYS,
    _GHG_ABSOLUTE_FIELD,
    _GHG_RATE_FIELD,
    _OTHER_RATE_FIELD,
    boundary_config_hash,
    classify_status,
    months_between,
    target_value_for_month,
    validate_monthly_phasing,
)


def test_months_between_inclusive():
    months = months_between(date(2026, 1, 1), date(2026, 3, 1))
    assert months == [date(2026, 1, 1), date(2026, 2, 1), date(2026, 3, 1)]


def test_months_between_crosses_year_boundary():
    months = months_between(date(2025, 11, 1), date(2026, 2, 1))
    assert months == [date(2025, 11, 1), date(2025, 12, 1), date(2026, 1, 1), date(2026, 2, 1)]


def test_boundary_config_hash_is_stable():
    h1 = boundary_config_hash("t1", "l1", "ghg_intensity_production", "p1")
    h2 = boundary_config_hash("t1", "l1", "ghg_intensity_production", "p1")
    assert h1 == h2


def test_boundary_config_hash_changes_with_location():
    h1 = boundary_config_hash("t1", "l1", "ghg_intensity_production", "p1")
    h2 = boundary_config_hash("t1", "l2", "ghg_intensity_production", "p1")
    assert h1 != h2


def test_boundary_config_hash_changes_with_denominator_mapping():
    # A later change to which data point feeds the intensity denominator
    # must be detectable, not silently absorbed into "the same" target.
    h1 = boundary_config_hash("t1", None, "ghg_intensity_production", "p1")
    h2 = boundary_config_hash("t1", None, "ghg_intensity_production", "p2")
    assert h1 != h2


def test_boundary_config_hash_changes_with_metric():
    h1 = boundary_config_hash("t1", None, "scope1_tco2e", None)
    h2 = boundary_config_hash("t1", None, "scope2_tco2e", None)
    assert h1 != h2


def test_targetable_metric_keys_have_no_gaps_or_overlaps():
    # Every targetable metric must resolve to exactly one field/attribute
    # lookup -- a metric present in more than one map, or in none, is a
    # silent bug in extract_metric_value's dispatch.
    ghg_keys = set(_GHG_ABSOLUTE_FIELD) | set(_GHG_RATE_FIELD)
    other_keys = set(_OTHER_RATE_FIELD)
    assert ghg_keys & other_keys == set()
    assert ghg_keys | other_keys == set(TARGETABLE_METRIC_KEYS)


def test_rate_metric_keys_are_exactly_the_intensity_metrics():
    assert RATE_METRIC_KEYS == set(_GHG_RATE_FIELD) | set(_OTHER_RATE_FIELD)
    assert "scope1_tco2e" not in RATE_METRIC_KEYS
    assert "scope1_2_tco2e" not in RATE_METRIC_KEYS


def test_validate_monthly_phasing_empty_list_is_valid():
    assert validate_monthly_phasing([], 120.0, date(2026, 1, 1), date(2026, 12, 1)) is None


def test_validate_monthly_phasing_matching_sum_is_valid():
    phasing = [{"period": "2026-01-01", "value": 60.0}, {"period": "2026-02-01", "value": 60.0}]
    assert validate_monthly_phasing(phasing, 120.0, date(2026, 1, 1), date(2026, 2, 1)) is None


def test_validate_monthly_phasing_rejects_mismatched_sum():
    phasing = [{"period": "2026-01-01", "value": 60.0}, {"period": "2026-02-01", "value": 50.0}]
    error = validate_monthly_phasing(phasing, 120.0, date(2026, 1, 1), date(2026, 2, 1))
    assert error is not None
    assert "does not match" in error


def test_validate_monthly_phasing_rejects_missing_month():
    phasing = [{"period": "2026-01-01", "value": 120.0}]
    error = validate_monthly_phasing(phasing, 120.0, date(2026, 1, 1), date(2026, 2, 1))
    assert error is not None
    assert "missing" in error


def test_validate_monthly_phasing_rejects_month_outside_period():
    phasing = [{"period": "2025-12-01", "value": 120.0}]
    error = validate_monthly_phasing(phasing, 120.0, date(2026, 1, 1), date(2026, 1, 1))
    assert error is not None
    assert "outside" in error


def test_target_value_for_month_uses_phasing_when_present():
    phasing = [{"period": "2026-01-01", "value": 60.0}, {"period": "2026-02-01", "value": 60.0}]
    assert target_value_for_month(phasing, date(2026, 1, 1), 120.0, 2) == 60.0


def test_target_value_for_month_spreads_budget_metric_evenly_without_phasing():
    assert target_value_for_month([], date(2026, 1, 1), 120.0, 12, "scope1_2_tco2e") == 10.0


def test_target_value_for_month_uses_rate_target_as_is_not_divided():
    # A rate target (tCO2e/MnAh, GJ/Cr, ...) isn't a budget -- dividing
    # 0.53 tCO2e/MnAh by 12 months would compare each month against a
    # twelfth of the rate, which is meaningless.
    assert target_value_for_month([], date(2026, 1, 1), 0.53, 12, "ghg_intensity_production") == 0.53
    assert target_value_for_month([], date(2026, 1, 1), 4.2, 12, "energy_per_revenue") == 4.2


def test_classify_status_is_within_safe_limits_when_at_or_below_target():
    assert classify_status(9.5, 10.0) == "Within safe limits"
    assert classify_status(10.0, 10.0) == "Within safe limits"


def test_classify_status_is_exceeded_above_target():
    assert classify_status(10.4, 10.0) == "Exceeded"
    assert classify_status(12.0, 10.0) == "Exceeded"


def test_classify_status_not_enough_data_when_actual_missing():
    assert classify_status(None, 10.0) == "Not enough data"


def test_classify_status_not_enough_data_when_target_missing():
    assert classify_status(9.0, None) == "Not enough data"
