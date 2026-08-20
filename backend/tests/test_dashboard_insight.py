"""Unit tests for the DB-free parts of dashboard_insight.py -- the input
hash that decides whether the AI must be called again. No database or
OpenAI call required."""

from app.services.dashboard_insight import hash_context


def test_hash_context_deterministic_for_identical_input():
    context = {"scope1_tco2e": 7.28, "targets": [{"metric": "Scope 1", "status": "Exceeded"}]}
    assert hash_context(context) == hash_context(dict(context))


def test_hash_context_ignores_key_order():
    a = {"scope1_tco2e": 7.28, "unresolved_count": 0}
    b = {"unresolved_count": 0, "scope1_tco2e": 7.28}
    assert hash_context(a) == hash_context(b)


def test_hash_context_changes_when_a_figure_changes():
    a = {"scope1_tco2e": 7.28, "unresolved_count": 0}
    b = {"scope1_tco2e": 7.30, "unresolved_count": 0}
    assert hash_context(a) != hash_context(b)


def test_hash_context_changes_when_targets_change():
    a = {"scope1_tco2e": 7.28, "targets": [{"metric": "Scope 1", "status": "Within safe limits"}]}
    b = {"scope1_tco2e": 7.28, "targets": [{"metric": "Scope 1", "status": "Exceeded"}]}
    assert hash_context(a) != hash_context(b)
