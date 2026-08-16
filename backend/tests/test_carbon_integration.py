"""Integration tests against a real database (the same one app.db.session
connects to via DATABASE_URL / .env). Skipped automatically when no
database is configured, e.g. in an environment with no .env and no
DATABASE_URL set -- these need a real Postgres with the schema and the
Amara Raja tenant's seeded data (see backend/scripts/seed_*.py) to mean
anything; a mocked/sqlite DB wouldn't exercise the real CHECK constraints
and partial unique index this table relies on.

Uses a safe, clearly-marked test period and cleans up every row it
creates in a finally block, regardless of pass/fail.
"""

from datetime import date
from decimal import Decimal

import pytest

from app.core.config import get_settings

pytestmark = pytest.mark.skipif(not get_settings().database_url, reason="no DATABASE_URL configured for integration tests")

TEST_PERIOD = date(2026, 3, 1)


@pytest.fixture
def db_session():
    from app.db.session import SessionLocal

    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def tenant_context(db_session):
    from app.db.models import Location, Tenant, User

    tenant = db_session.query(Tenant).filter(Tenant.name == "Amara Raja").first()
    if tenant is None:
        pytest.skip("Amara Raja tenant not seeded in this database")
    location = db_session.query(Location).filter(Location.tenant_id == tenant.id).first()
    admin = db_session.query(User).filter(User.email == "saipraneeth836@gmail.com").first()
    return tenant, location, admin


def _make_entry(db, tenant, location, admin, data_point_name, value):
    from app.db.models import Category, DataPoint, Entry

    dp = (
        db.query(DataPoint)
        .join(Category, Category.id == DataPoint.category_id)
        .filter(Category.tenant_id == tenant.id, DataPoint.name == data_point_name)
        .first()
    )
    assert dp is not None, f"data point {data_point_name} not seeded"
    entry = Entry(
        data_point_id=dp.id,
        location_id=location.id,
        period=TEST_PERIOD,
        value=value,
        method_of_entry="Manual",
        status="Approved",
        submitted_by=admin.id,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@pytest.fixture
def cleanup_entries(db_session):
    entry_ids = []
    yield entry_ids
    from app.db.models import EmissionCalculation, Entry

    if entry_ids:
        db_session.query(EmissionCalculation).filter(EmissionCalculation.entry_id.in_(entry_ids)).delete(synchronize_session=False)
        db_session.query(Entry).filter(Entry.id.in_(entry_ids)).delete(synchronize_session=False)
        db_session.commit()


def test_diesel_uses_tenant_factor_and_calculates_correctly(db_session, tenant_context, cleanup_entries):
    from app.services.carbon_calculation import calculate_entry

    tenant, location, admin = tenant_context
    entry = _make_entry(db_session, tenant, location, admin, "Diesel Consumed", 500)
    cleanup_entries.append(entry.id)

    calc = calculate_entry(db_session, entry, tenant.id, admin.id)
    db_session.commit()
    db_session.refresh(calc)

    assert calc.status == "calculated"
    assert calc.scope == 1
    assert calc.factor_id is not None  # tenant factor, not the reference fallback
    assert calc.emissions_kgco2e == Decimal("500") * calc.factor_value


def test_refrigerant_leakage_is_scope_1_gwp(db_session, tenant_context, cleanup_entries):
    from app.services.carbon_calculation import calculate_entry

    tenant, location, admin = tenant_context
    entry = _make_entry(db_session, tenant, location, admin, "Refrigerant Leakage — R-134a", 2.5)
    cleanup_entries.append(entry.id)

    calc = calculate_entry(db_session, entry, tenant.id, admin.id)
    db_session.commit()
    db_session.refresh(calc)

    assert calc.status == "calculated"
    assert calc.scope == 1  # fugitive emissions, not Scope 2 -- see fix_refrigerant_scope.py
    assert calc.emissions_kgco2e == Decimal("2.5") * calc.factor_value


def test_coal_has_no_factor_and_stays_unresolved(db_session, tenant_context, cleanup_entries):
    """Coal was dropped from the reference table in the verified Prompt 3f
    reseed -- this should show as missing_factor, never a guess."""
    from app.services.carbon_calculation import calculate_entry

    tenant, location, admin = tenant_context
    entry = _make_entry(db_session, tenant, location, admin, "Coal Consumed", 200)
    cleanup_entries.append(entry.id)

    calc = calculate_entry(db_session, entry, tenant.id, admin.id)
    db_session.commit()
    db_session.refresh(calc)

    assert calc.status == "unresolved"
    assert "missing_factor" in (calc.resolution_reason or "")


def test_water_entry_is_not_a_carbon_source_and_writes_no_row(db_session, tenant_context, cleanup_entries):
    from app.db.models import Category, DataPoint, EmissionCalculation
    from app.services.carbon_calculation import calculate_entry

    tenant, location, admin = tenant_context
    dp = (
        db_session.query(DataPoint)
        .join(Category, Category.id == DataPoint.category_id)
        .filter(Category.tenant_id == tenant.id, DataPoint.name == "Surface Water Withdrawal")
        .first()
    )
    from app.db.models import Entry

    entry = Entry(
        data_point_id=dp.id, location_id=location.id, period=TEST_PERIOD,
        value=100, method_of_entry="Manual", status="Approved", submitted_by=admin.id,
    )
    db_session.add(entry)
    db_session.commit()
    db_session.refresh(entry)
    cleanup_entries.append(entry.id)

    calc = calculate_entry(db_session, entry, tenant.id, admin.id)
    db_session.commit()

    assert calc is None
    assert db_session.query(EmissionCalculation).filter(EmissionCalculation.entry_id == entry.id).count() == 0


def test_recalculation_supersedes_prior_row_and_keeps_it_reproducible(db_session, tenant_context, cleanup_entries):
    """An old approved footprint must stay reproducible with its original
    factor version even after a recalculation (rule #6)."""
    from app.services.carbon_calculation import calculate_entry

    tenant, location, admin = tenant_context
    entry = _make_entry(db_session, tenant, location, admin, "Diesel Consumed", 500)
    cleanup_entries.append(entry.id)

    first = calculate_entry(db_session, entry, tenant.id, admin.id)
    db_session.commit()
    db_session.refresh(first)
    first_id, first_value, first_factor = first.id, first.emissions_kgco2e, first.factor_value

    entry.value = 600
    db_session.commit()
    second = calculate_entry(db_session, entry, tenant.id, admin.id)
    db_session.commit()
    db_session.refresh(second)
    db_session.refresh(first)

    assert first.status == "superseded"
    assert second.supersedes_calculation_id == first_id
    assert second.emissions_kgco2e == Decimal("600") * second.factor_value
    # the original row is untouched -- still reflects the original activity/value
    assert first.emissions_kgco2e == first_value
    assert first.factor_value == first_factor
