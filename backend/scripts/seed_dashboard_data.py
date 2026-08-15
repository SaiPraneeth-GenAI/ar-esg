"""Seeds ~7 months of synthetic, already-approved Water/Waste entries (plus a
Production data point used only as the intensity denominator) for the Amara
Raja tenant, so the dashboard has real cards to show instead of the empty
state. These figures are entirely made up for the demo -- not Amara Raja's
actual data -- but shaped with plausible month-to-month variation (a
maintenance-driven dip, a seasonal peak) rather than flat repeats.

Idempotent: safe to re-run: existing categories/data points/thresholds/entries
are reused rather than duplicated, and rollups are recomputed either way.
"""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.models import Category, DataPoint, Entry, Location, Tenant, Threshold, User  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.services.rollups import recompute_rollup  # noqa: E402

TENANT_NAME = "Amara Raja"
LOCATION_NAME = "ARE&M"
ADMIN_EMAIL = "saipraneeth836@gmail.com"

# category name -> (industry_pack, display_order)
CATEGORIES = {
    "Water": ("battery manufacturing", 1),
    "Waste": ("battery manufacturing", 2),
    "Production": ("battery manufacturing", 99),
}

# category -> [(data point name, unit)]
DATA_POINTS = {
    "Water": [
        ("Ground Water Withdrawal", "KL"),
        ("Municipal Water Purchased", "KL"),
    ],
    "Waste": [
        ("Hazardous Waste Generated", "MT"),
        ("Non-Hazardous Waste Generated", "MT"),
    ],
    "Production": [
        ("Battery Production Volume", "Mn Ah"),
    ],
}

# data point name -> monthly target
TARGETS = {
    "Ground Water Withdrawal": 2500,
    "Municipal Water Purchased": 400,
    "Hazardous Waste Generated": 20,
    "Non-Hazardous Waste Generated": 45,
}

# month (2026) -> { data point name: value }
MONTHLY_VALUES = {
    1: {
        "Ground Water Withdrawal": 2420,
        "Municipal Water Purchased": 375,
        "Hazardous Waste Generated": 17.5,
        "Non-Hazardous Waste Generated": 50,
        "Battery Production Volume": 32.5,
    },
    2: {
        "Ground Water Withdrawal": 2470,
        "Municipal Water Purchased": 390,
        "Hazardous Waste Generated": 18.2,
        "Non-Hazardous Waste Generated": 52,
        "Battery Production Volume": 33.4,
    },
    3: {
        "Ground Water Withdrawal": 2650,
        "Municipal Water Purchased": 415,
        "Hazardous Waste Generated": 20.5,
        "Non-Hazardous Waste Generated": 57,
        "Battery Production Volume": 35.8,
    },
    4: {  # planned maintenance shutdown -- lower production and consumption
        "Ground Water Withdrawal": 2360,
        "Municipal Water Purchased": 355,
        "Hazardous Waste Generated": 16.8,
        "Non-Hazardous Waste Generated": 47,
        "Battery Production Volume": 30.6,
    },
    5: {
        "Ground Water Withdrawal": 2700,
        "Municipal Water Purchased": 425,
        "Hazardous Waste Generated": 21.3,
        "Non-Hazardous Waste Generated": 59,
        "Battery Production Volume": 36.9,
    },
    6: {  # seasonal peak
        "Ground Water Withdrawal": 2850,
        "Municipal Water Purchased": 460,
        "Hazardous Waste Generated": 24.0,
        "Non-Hazardous Waste Generated": 65,
        "Battery Production Volume": 39.0,
    },
    7: {  # cooling off from the peak
        "Ground Water Withdrawal": 2600,
        "Municipal Water Purchased": 410,
        "Hazardous Waste Generated": 20.0,
        "Non-Hazardous Waste Generated": 56,
        "Battery Production Volume": 35.0,
    },
}


def get_or_create_category(db, tenant_id, name: str) -> Category:
    category = db.query(Category).filter(Category.tenant_id == tenant_id, Category.name == name).first()
    if category is None:
        industry_pack, display_order = CATEGORIES[name]
        category = Category(tenant_id=tenant_id, name=name, industry_pack=industry_pack, display_order=display_order)
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


def get_or_create_threshold(db, data_point_id, target_value: float) -> None:
    existing = db.query(Threshold).filter(Threshold.data_point_id == data_point_id).first()
    if existing is None:
        db.add(Threshold(data_point_id=data_point_id, target_value=target_value))
        db.commit()
        print(f"created threshold target={target_value}")


def get_or_create_entry(db, data_point_id, location_id, period: date, value: float, submitted_by) -> Entry:
    existing = (
        db.query(Entry)
        .filter(Entry.data_point_id == data_point_id, Entry.location_id == location_id, Entry.period == period)
        .first()
    )
    if existing is not None:
        return existing
    entry = Entry(
        data_point_id=data_point_id,
        location_id=location_id,
        period=period,
        value=value,
        method_of_entry="Manual",
        status="Approved",
        submitted_by=submitted_by,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def main() -> None:
    db = SessionLocal()
    try:
        tenant = db.query(Tenant).filter(Tenant.name == TENANT_NAME).first()
        if tenant is None:
            raise SystemExit(f"Tenant '{TENANT_NAME}' not found -- run scripts/seed_admin.py first")

        location = db.query(Location).filter(Location.tenant_id == tenant.id, Location.name == LOCATION_NAME).first()
        if location is None:
            raise SystemExit(f"Location '{LOCATION_NAME}' not found -- run scripts/seed_admin.py first")

        admin_user = db.query(User).filter(User.email == ADMIN_EMAIL).first()
        if admin_user is None:
            raise SystemExit(f"Admin user '{ADMIN_EMAIL}' not found -- run scripts/seed_admin.py first")

        data_points_by_name: dict[str, DataPoint] = {}
        for category_name, points in DATA_POINTS.items():
            category = get_or_create_category(db, tenant.id, category_name)
            for point_name, unit in points:
                dp = get_or_create_data_point(db, category.id, point_name, unit)
                data_points_by_name[point_name] = dp
                if point_name in TARGETS:
                    get_or_create_threshold(db, dp.id, TARGETS[point_name])

        periods: set[date] = set()
        for month, values in MONTHLY_VALUES.items():
            period = date(2026, month, 1)
            periods.add(period)
            for point_name, value in values.items():
                dp = data_points_by_name[point_name]
                get_or_create_entry(db, dp.id, location.id, period, value, admin_user.id)
        print(f"seeded entries for {len(MONTHLY_VALUES)} months")

        for period in sorted(periods):
            for category_name in CATEGORIES:
                recompute_rollup(db, tenant.id, location.id, category_name, period)
        print(f"recomputed rollups for {len(periods)} months x {len(CATEGORIES)} categories")
    finally:
        db.close()


if __name__ == "__main__":
    main()
