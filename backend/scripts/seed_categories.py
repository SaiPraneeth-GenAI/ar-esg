"""Seeds/updates Category + DataPoint config for all five categories the
entry workflow needs to support. Config only -- no Entry rows here; those
get created by real users through the app now that the entry workflow
exists.

Idempotent: existing rows are reused, not duplicated. One deliberate
exception: the legacy "Municipal Water Purchased" data point (which has
7 months of real approved history from the earlier dashboard seed) is
renamed in place to "Third-Party Water Withdrawal" -- same underlying
concept, and this preserves its history under the correct field name
instead of creating a duplicate.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.models import Category, DataPoint, Tenant  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402

TENANT_NAME = "Amara Raja"
INDUSTRY_PACK = "battery manufacturing"

RENAME_DATA_POINTS = {
    "Municipal Water Purchased": "Third-Party Water Withdrawal",
}

# category name -> (display_order, [(data point name, unit, extra kwargs)])
CATEGORY_SPEC: dict[str, tuple[int, list[tuple[str, str, dict]]]] = {
    "Water": (
        1,
        [
            ("Surface Water Withdrawal", "KL", {}),
            ("Ground Water Withdrawal", "KL", {}),
            ("Third-Party Water Withdrawal", "KL", {}),
            ("Packaging Drinking Water", "KL", {}),
        ],
    ),
    "ETP-Water": (
        2,
        [
            ("Total Treated Effluent Generated", "KL", {}),
            ("Recycled Water Used for Process", "KL", {}),
            ("Recycled Water Used for Irrigation", "KL", {}),
        ],
    ),
    "STP-Water": (
        3,
        [
            ("Total Treated Effluent Generated", "KL", {}),
            ("Recycled Water Used for Process", "KL", {}),
            ("Recycled Water Used for Irrigation", "KL", {}),
        ],
    ),
    "Waste": (
        4,
        [
            (f"{waste_type} — {disposition}", "MT", {})
            for waste_type in [
                "Plastic Waste",
                "Other Hazardous Waste",
                "Biomedical Waste",
                "Construction & Demolition Waste",
                "Battery Waste",
                "E-Waste",
            ]
            for disposition in ["Recycled", "Sent to Landfill", "Incinerated"]
        ],
    ),
    "Ozone": (
        5,
        [(substance, "kg", {}) for substance in ["R-22", "R-134a", "R-32", "Halon"]],
    ),
    "Effluent Monitoring": (
        6,
        [
            ("pH (Placeholder)", "TBD", {"validation_rules": {"provisional": True}}),
            ("BOD (Placeholder)", "TBD", {"validation_rules": {"provisional": True}}),
            ("COD (Placeholder)", "TBD", {"validation_rules": {"provisional": True}}),
        ],
    ),
    "Air Emissions": (
        7,
        [
            ("Diesel Consumed", "litres", {}),
            ("Petrol Consumed", "litres", {}),
            ("LPG Consumed", "kg", {}),
            ("Coal Consumed", "kg", {}),
            ("Grid Electricity Consumed", "kWh", {}),
            ("Renewable / PPA-Covered Percentage", "%", {"validation_rules": {"min": 0, "max": 100}}),
            *[
                (f"Refrigerant Leakage — {substance}", "kg", {})
                for substance in ["R-22", "R-134a", "R-32", "Halon"]
            ],
        ],
    ),
}


def get_or_create_category(db, tenant_id, name: str, display_order: int) -> Category:
    category = db.query(Category).filter(Category.tenant_id == tenant_id, Category.name == name).first()
    if category is None:
        category = Category(tenant_id=tenant_id, name=name, industry_pack=INDUSTRY_PACK, display_order=display_order)
        db.add(category)
        db.commit()
        db.refresh(category)
        print(f"created category {name}")
    return category


def get_or_create_data_point(db, category_id, name: str, unit: str, extra: dict) -> DataPoint:
    dp = db.query(DataPoint).filter(DataPoint.category_id == category_id, DataPoint.name == name).first()
    if dp is None:
        dp = DataPoint(category_id=category_id, name=name, unit=unit, input_type="number", **extra)
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

        for old_name, new_name in RENAME_DATA_POINTS.items():
            dp = (
                db.query(DataPoint)
                .join(Category, Category.id == DataPoint.category_id)
                .filter(Category.tenant_id == tenant.id, DataPoint.name == old_name)
                .first()
            )
            if dp is not None:
                dp.name = new_name
                db.commit()
                print(f"renamed data point '{old_name}' -> '{new_name}'")

        for category_name, (display_order, points) in CATEGORY_SPEC.items():
            category = get_or_create_category(db, tenant.id, category_name, display_order)
            for point_name, unit, extra in points:
                get_or_create_data_point(db, category.id, point_name, unit, extra)

        print("done")
    finally:
        db.close()


if __name__ == "__main__":
    main()
