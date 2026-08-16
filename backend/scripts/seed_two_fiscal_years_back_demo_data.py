"""Second prior-fiscal-year companion to seed_prior_fiscal_year_demo_data.py:
the same categories, the same months two years earlier (Mar-Aug 2024), so
a quarterly/YTD trend chart's older buckets (e.g. Q2/Q3 2025) can also show
a real "vs last year" figure instead of a bare bar with no comparison.

Values continue the same linear month-over-month delta already established
between the 2025 and 2026 seed scripts (2024 = 2025 + (2025 - 2026) for a
declining metric, 2025 - (2026 - 2025) for a rising one), so the three
years read as one continuous, plausible efficiency-gain trend rather than
an arbitrary jump. Sample data for demonstration only, picked by hand for
the same reason as the other two seed scripts -- not sourced from any
reference image.

note = "Demo data -- two fiscal years back walkthrough" for later
identification.
"""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.models import Approval, AuditLog, Category, DataPoint, Entry, Location, Tenant, User  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.services.carbon_calculation import calculate_entry  # noqa: E402
from app.services.rollups import recompute_rollup_for_entry  # noqa: E402

NOTE = "Demo data -- two fiscal years back walkthrough"

MONTHS = [date(2024, m, 1) for m in range(3, 9)]  # Mar..Aug 2024

MONTHLY_DATA: dict[date, dict[str, float]] = {
    date(2024, 3, 1): {
        "Diesel Consumed": 750, "Petrol Consumed": 240, "LPG Consumed": 420, "Grid Electricity Consumed": 27400,
        "Refrigerant Leakage — R-134a": 5.2, "Battery Production Volume": 16.0, "Revenue": 50,
        "Surface Water Withdrawal": 1305, "Ground Water Withdrawal": 1118, "Third-Party Water Withdrawal": 931, "Packaging Drinking Water": 372,
        "Hazardous Waste Generated": 38.0, "Non-Hazardous Waste Generated": 57.0,
        "Fatality": 0, "LTIFR": 0.90, "Defensive Driving Training": 49, "Unsafe Conditions": 2479, "Near Miss": 1040,
    },
    date(2024, 4, 1): {
        "Diesel Consumed": 730, "Petrol Consumed": 235, "LPG Consumed": 416, "Grid Electricity Consumed": 26900,
        "Refrigerant Leakage — R-134a": 4.8, "Battery Production Volume": 16.8, "Revenue": 52,
        "Surface Water Withdrawal": 1260, "Ground Water Withdrawal": 1079, "Third-Party Water Withdrawal": 899, "Packaging Drinking Water": 361,
        "Hazardous Waste Generated": 36.1, "Non-Hazardous Waste Generated": 54.1,
        "Fatality": 0, "LTIFR": 0.86, "Defensive Driving Training": 52, "Unsafe Conditions": 2100, "Near Miss": 920,
    },
    date(2024, 5, 1): {
        "Diesel Consumed": 705, "Petrol Consumed": 226, "LPG Consumed": 405, "Grid Electricity Consumed": 26400,
        "Refrigerant Leakage — R-134a": 4.3, "Battery Production Volume": 18.6, "Revenue": 56,
        "Surface Water Withdrawal": 1363, "Ground Water Withdrawal": 1169, "Third-Party Water Withdrawal": 974, "Packaging Drinking Water": 389,
        "Hazardous Waste Generated": 39.8, "Non-Hazardous Waste Generated": 59.6,
        "Fatality": 1, "LTIFR": 0.81, "Defensive Driving Training": 56, "Unsafe Conditions": 1740, "Near Miss": 800,
    },
    date(2024, 6, 1): {
        "Diesel Consumed": 670, "Petrol Consumed": 215, "LPG Consumed": 395, "Grid Electricity Consumed": 26000,
        "Refrigerant Leakage — R-134a": 3.6, "Battery Production Volume": 21.2, "Revenue": 62,
        "Surface Water Withdrawal": 1522, "Ground Water Withdrawal": 1305, "Third-Party Water Withdrawal": 1088, "Packaging Drinking Water": 435,
        "Hazardous Waste Generated": 48.2, "Non-Hazardous Waste Generated": 72.4,
        "Fatality": 0, "LTIFR": 0.76, "Defensive Driving Training": 57, "Unsafe Conditions": 1400, "Near Miss": 700,
    },
    date(2024, 7, 1): {
        "Diesel Consumed": 640, "Petrol Consumed": 210, "LPG Consumed": 381, "Grid Electricity Consumed": 25000,
        "Refrigerant Leakage — R-134a": 3.0, "Battery Production Volume": 20.2, "Revenue": 65,
        "Surface Water Withdrawal": 1431, "Ground Water Withdrawal": 1226, "Third-Party Water Withdrawal": 1023, "Packaging Drinking Water": 410,
        "Hazardous Waste Generated": 44.4, "Non-Hazardous Waste Generated": 66.6,
        "Fatality": 0, "LTIFR": 0.71, "Defensive Driving Training": 58, "Unsafe Conditions": 1090, "Near Miss": 600,
    },
    date(2024, 8, 1): {
        "Diesel Consumed": 620, "Petrol Consumed": 201, "LPG Consumed": 366, "Grid Electricity Consumed": 24400,
        "Refrigerant Leakage — R-134a": 2.6, "Battery Production Volume": 19.0, "Revenue": 67,
        "Surface Water Withdrawal": 1312, "Ground Water Withdrawal": 1125, "Third-Party Water Withdrawal": 937, "Packaging Drinking Water": 375,
        "Hazardous Waste Generated": 40.8, "Non-Hazardous Waste Generated": 61.2,
        "Fatality": 0, "LTIFR": 0.67, "Defensive Driving Training": 66.8, "Unsafe Conditions": 844, "Near Miss": 488,
    },
}


def main() -> None:
    db = SessionLocal()
    created = 0
    skipped_missing_dp = []
    try:
        tenant = db.query(Tenant).filter(Tenant.name == "Amara Raja").first()
        location = db.query(Location).filter(Location.tenant_id == tenant.id).first()
        manager = db.query(User).filter(User.email == "andhrapradeshweatherman@gmail.com").first()
        approver = db.query(User).filter(User.email == "saipraneeth836@gmail.com").first()

        def get_dp(name: str) -> DataPoint | None:
            return (
                db.query(DataPoint)
                .join(Category, Category.id == DataPoint.category_id)
                .filter(Category.tenant_id == tenant.id, DataPoint.name == name)
                .first()
            )

        for period in MONTHS:
            for dp_name, value in MONTHLY_DATA[period].items():
                dp = get_dp(dp_name)
                if dp is None:
                    skipped_missing_dp.append(dp_name)
                    continue

                existing = (
                    db.query(Entry)
                    .filter(Entry.data_point_id == dp.id, Entry.location_id == location.id, Entry.period == period)
                    .first()
                )
                if existing is not None:
                    continue

                entry = Entry(
                    data_point_id=dp.id,
                    location_id=location.id,
                    period=period,
                    value=value,
                    method_of_entry="Manual",
                    status="Approved",
                    submitted_by=manager.id,
                    note=NOTE,
                )
                db.add(entry)
                db.commit()
                db.refresh(entry)

                db.add(Approval(entry_id=entry.id, approver_id=approver.id, action="approve"))
                db.add(
                    AuditLog(
                        entry_id=entry.id, actor=approver.email, action="approved",
                        old_value="Draft", new_value="Approved (demo seed)",
                    )
                )
                db.commit()

                recompute_rollup_for_entry(db, entry)
                calculate_entry(db, entry, tenant.id, approver.id)
                db.commit()
                created += 1

        print(f"created {created} entries across {len(MONTHS)} two-fiscal-years-back months")
        if skipped_missing_dp:
            print("skipped -- data point not found:", sorted(set(skipped_missing_dp)))
    finally:
        db.close()


if __name__ == "__main__":
    main()
