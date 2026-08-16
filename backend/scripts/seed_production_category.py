"""Seeds the "Production" category + "Battery Production Volume" data
point that the intensity KPI (tCO2e/MnAh) needs, and the
production_volume_mapping row that points the carbon engine at it.

This data point didn't exist before Prompt 4 -- dashboard.py already
referenced a PRODUCTION_CATEGORY = "Production" constant, but nothing had
ever created the category or data point behind it. Seeded directly in the
canonical unit (MnAh) since there's no prior history to reconcile;
conversion_multiplier is 1 here but the mapping table supports a real
multiplier for a tenant that records production in Ah or MWh instead.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.models import Category, DataPoint, ProductionVolumeMapping, Tenant  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402

TENANT_NAME = "Amara Raja"
CATEGORY_NAME = "Production"
DATA_POINT_NAME = "Battery Production Volume"
CANONICAL_UNIT = "MnAh"


def main() -> None:
    db = SessionLocal()
    try:
        tenant = db.query(Tenant).filter(Tenant.name == TENANT_NAME).first()
        if tenant is None:
            raise SystemExit(f"Tenant '{TENANT_NAME}' not found -- run scripts/seed_admin.py first")

        category = db.query(Category).filter(Category.tenant_id == tenant.id, Category.name == CATEGORY_NAME).first()
        if category is None:
            category = Category(tenant_id=tenant.id, name=CATEGORY_NAME, industry_pack="battery manufacturing", display_order=8)
            db.add(category)
            db.commit()
            db.refresh(category)
            print(f"created category {CATEGORY_NAME}")

        dp = db.query(DataPoint).filter(DataPoint.category_id == category.id, DataPoint.name == DATA_POINT_NAME).first()
        if dp is None:
            dp = DataPoint(category_id=category.id, name=DATA_POINT_NAME, unit=CANONICAL_UNIT, input_type="number")
            db.add(dp)
            db.commit()
            db.refresh(dp)
            print(f"created data point {DATA_POINT_NAME}")

        mapping = (
            db.query(ProductionVolumeMapping)
            .filter(ProductionVolumeMapping.tenant_id == tenant.id, ProductionVolumeMapping.data_point_id == dp.id)
            .first()
        )
        if mapping is None:
            mapping = ProductionVolumeMapping(
                tenant_id=tenant.id,
                location_id=None,  # applies to every location for this tenant
                data_point_id=dp.id,
                native_unit=CANONICAL_UNIT,
                canonical_unit=CANONICAL_UNIT,
                conversion_multiplier=1,
                is_active=True,
            )
            db.add(mapping)
            db.commit()
            print("created production_volume_mapping row")

        print("done")
    finally:
        db.close()


if __name__ == "__main__":
    main()
