import uuid
from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.services.energy_assurance import assert_tenant, location_scope2, normalize_energy, reconcile_energy


def test_tenant_guard_accepts_same_tenant():
    tenant_id = uuid.uuid4()
    assert_tenant(tenant_id, tenant_id)


def test_tenant_guard_hides_cross_tenant_record():
    with pytest.raises(HTTPException) as exc:
        assert_tenant(uuid.uuid4(), uuid.uuid4(), "Reading")
    assert exc.value.status_code == 404
    assert exc.value.detail == "Reading not found"


def test_multiple_meters_are_summed_without_overwrite():
    result = reconcile_energy([Decimal("11000"), Decimal("10500")], Decimal("24000"))
    assert result.actual_kwh == Decimal("21500")
    assert result.variance_kwh == Decimal("-2500")
    assert result.status == "failed"


def test_mwh_is_normalized_before_reconciliation():
    assert normalize_energy("1.5", "MWh") == Decimal("1500.0")
    assert normalize_energy("1500", "kWh") == Decimal("1500")


def test_scope2_lineage_uses_every_grid_meter():
    result, formula = location_scope2([Decimal("50000"), Decimal("48400")])
    assert result == Decimal("69.864")
    assert "98400" in formula
    assert "0.710" in formula
