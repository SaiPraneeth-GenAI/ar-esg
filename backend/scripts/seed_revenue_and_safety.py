"""Seeds the "Business Performance" category + "Revenue" data point (and
its revenue_mapping row, the twin of production_volume_mapping) that
revenue-intensity KPIs need, plus a "Safety" category with the five
non-GHG metrics the reference ESG report tracks alongside environmental
performance. Idempotent -- mirrors seed_production_category.py exactly.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.models import Category, DataPoint, RevenueMapping, Tenant  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402

TENANT_NAME = "Amara Raja"

REVENUE_CATEGORY = "Business Performance"
REVENUE_DATA_POINT = "Revenue"
REVENUE_UNIT = "INR Cr"

SAFETY_CATEGORY = "Safety"
SAFETY_DATA_POINTS = [
    ("Fatality", "Nos"),
    ("LTIFR", "Rate"),
    ("Defensive Driving Training", "%"),
    ("Unsafe Conditions", "Nos"),
    ("Near Miss", "Nos"),
]


def get_or_create_category(db, tenant_id, name: str, display_order: int) -> Category:
    category = db.query(Category).filter(Category.tenant_id == tenant_id, Category.name == name).first()
    if category is None:
        category = Category(tenant_id=tenant_id, name=name, industry_pack="battery manufacturing", display_order=display_order)
        db.add(category)
        db.commit()
        db.refresh(category)
        print(f"created category {name}")
    return category


def get_or_create_data_point(db, category_id, name: str, unit: str) -> DataPoint:
    dp = db.query(DataPoint).filter(DataPoint.category_id == category_id, DataPoint.name == name).first()
    if dp is None:
        dp = DataPoint(category_id=category_id, name=name, unit=unit, input_type="number")
        db.add(dp)
        db.commit()
        db.refresh(dp)
        print(f"created data point {name}")
    return dp


def main() -> None:
    db = SessionLocal()
    try:
        tenant = db.query(Tenant).filter(Tenant.name == TENANT_NAME).first()
        if tenant is None:
            raise SystemExit(f"Tenant '{TENANT_NAME}' not found -- run scripts/seed_admin.py first")

        revenue_category = get_or_create_category(db, tenant.id, REVENUE_CATEGORY, display_order=9)
        revenue_dp = get_or_create_data_point(db, revenue_category.id, REVENUE_DATA_POINT, REVENUE_UNIT)

        mapping = (
            db.query(RevenueMapping)
            .filter(RevenueMapping.tenant_id == tenant.id, RevenueMapping.data_point_id == revenue_dp.id)
            .first()
        )
        if mapping is None:
            mapping = RevenueMapping(
                tenant_id=tenant.id,
                location_id=None,
                data_point_id=revenue_dp.id,
                native_unit=REVENUE_UNIT,
                canonical_unit=REVENUE_UNIT,
                conversion_multiplier=1,
                is_active=True,
            )
            db.add(mapping)
            db.commit()
            print("created revenue_mapping row")

        safety_category = get_or_create_category(db, tenant.id, SAFETY_CATEGORY, display_order=10)
        for name, unit in SAFETY_DATA_POINTS:
            get_or_create_data_point(db, safety_category.id, name, unit)

        print("done")
    finally:
        db.close()


if __name__ == "__main__":
    main()
