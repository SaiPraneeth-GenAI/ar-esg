"""Unit tests for the DB-free pure functions in target_calculation.py --
boundary hashing, metric extraction, monthly phasing validation and
actual-vs-target status classification. No database required."""

from datetime import date

from app.services.target_calculation import (
    boundary_config_hash,
    classify_status,
    extract_metric_value,
    months_between,
    target_value_for_month,
    validate_metric_scope,
    validate_monthly_phasing,
)


def test_months_between_inclusive():
    months = months_between(date(2026, 1, 1), date(2026, 3, 1))
    assert months == [date(2026, 1, 1), date(2026, 2, 1), date(2026, 3, 1)]


def test_months_between_crosses_year_boundary():
    months = months_between(date(2025, 11, 1), date(2026, 2, 1))
    assert months == [date(2025, 11, 1), date(2025, 12, 1), date(2026, 1, 1), date(2026, 2, 1)]


def test_boundary_config_hash_is_stable():
    h1 = boundary_config_hash("t1", "l1", "1_2_combined", "location_based", "intensity_tco2e_per_mnah", "p1")
    h2 = boundary_config_hash("t1", "l1", "1_2_combined", "location_based", "intensity_tco2e_per_mnah", "p1")
    assert h1 == h2


def test_boundary_config_hash_changes_with_boundary():
    h1 = boundary_config_hash("t1", "l1", "1_2_combined", "location_based", "intensity_tco2e_per_mnah", "p1")
    h2 = boundary_config_hash("t1", "l2", "1_2_combined", "location_based", "intensity_tco2e_per_mnah", "p1")
    assert h1 != h2


def test_boundary_config_hash_changes_with_production_mapping():
    # A later change to which data point feeds the intensity denominator
    # must be detectable, not silently absorbed into "the same" target.
    h1 = boundary_config_hash("t1", None, "1_2_combined", "location_based", "intensity_tco2e_per_mnah", "p1")
    h2 = boundary_config_hash("t1", None, "1_2_combined", "location_based", "intensity_tco2e_per_mnah", "p2")
    assert h1 != h2


def test_validate_metric_scope_rejects_intensity_outside_combined_boundary():
    error = validate_metric_scope("1", "intensity_tco2e_per_mnah")
    assert error is not None
    assert "Intensity" in error


def test_validate_metric_scope_allows_intensity_for_combined_boundary():
    assert validate_metric_scope("1_2_combined", "intensity_tco2e_per_mnah") is None


def test_validate_metric_scope_allows_absolute_for_any_boundary():
    assert validate_metric_scope("2", "absolute_tco2e") is None


def test_extract_metric_value_combined_boundary():
    totals = {"scope1_2_loc_tco2e": 42.5, "scope1_tco2e": 10.0, "scope2_loc_tco2e": 32.5, "scope2_mkt_tco2e": 30.0}
    value, error = extract_metric_value(totals, "1_2_combined", None)
    assert value == 42.5
    assert error is None


def test_extract_metric_value_scope2_market_based():
    totals = {"scope1_2_loc_tco2e": 42.5, "scope1_tco2e": 10.0, "scope2_loc_tco2e": 32.5, "scope2_mkt_tco2e": 30.0}
    value, error = extract_metric_value(totals, "2", "market_based")
    assert value == 30.0
    assert error is None


def test_extract_metric_value_scope2_location_based_is_default():
    totals = {"scope1_2_loc_tco2e": 42.5, "scope1_tco2e": 10.0, "scope2_loc_tco2e": 32.5, "scope2_mkt_tco2e": 30.0}
    value, error = extract_metric_value(totals, "2", None)
    assert value == 32.5


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


def test_target_value_for_month_spreads_evenly_without_phasing():
    assert target_value_for_month([], date(2026, 1, 1), 120.0, 12) == 10.0


def test_classify_status_on_track_when_at_or_below_target():
    assert classify_status(9.5, 10.0) == "On track"
    assert classify_status(10.0, 10.0) == "On track"


def test_classify_status_watch_within_margin():
    assert classify_status(10.4, 10.0) == "Watch"


def test_classify_status_off_track_beyond_margin():
    assert classify_status(12.0, 10.0) == "Off track"


def test_classify_status_not_enough_data_when_actual_missing():
    assert classify_status(None, 10.0) == "Not enough data"


def test_classify_status_not_enough_data_when_target_missing():
    assert classify_status(9.0, None) == "Not enough data"
