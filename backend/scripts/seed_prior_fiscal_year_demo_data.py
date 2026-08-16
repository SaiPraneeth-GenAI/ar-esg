"""Prior-fiscal-year companion to seed_comprehensive_demo_data.py: the same
categories, the same months one year earlier (Mar-Aug 2025), so every
dashboard card can show a real 'vs last year' figure instead of 'no
comparison available'. Values are deliberately higher for GHG/energy/
water/waste-per-unit and lower for production/revenue than the
corresponding 2026 month -- a plausible year-over-year efficiency-gain
narrative, picked by hand for the same reason as the 2026 seed: sample
data for demonstration, not sourced from any reference image.

note = "Demo data -- prior fiscal year walkthrough" for later identification.
"""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.models import Approval, AuditLog, Category, DataPoint, Entry, Location, Tenant, User  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.services.carbon_calculation import calculate_entry  # noqa: E402
from app.services.rollups import recompute_rollup_for_entry  # noqa: E402

NOTE = "Demo data -- prior fiscal year walkthrough"

MONTHS = [date(2025, m, 1) for m in range(3, 9)]  # Mar..Aug 2025

MONTHLY_DATA: dict[date, dict[str, float]] = {
    date(2025, 3, 1): {
        "Diesel Consumed": 645, "Petrol Consumed": 210, "LPG Consumed": 365, "Grid Electricity Consumed": 23800,
        "Refrigerant Leakage — R-134a": 4.4, "Battery Production Volume": 22.5, "Revenue": 74,
        "Surface Water Withdrawal": 1160, "Ground Water Withdrawal": 994, "Third-Party Water Withdrawal": 828, "Packaging Drinking Water": 331,
        "Hazardous Waste Generated": 32.6, "Non-Hazardous Waste Generated": 48.9,
        "Fatality": 0, "LTIFR": 0.78, "Defensive Driving Training": 62, "Unsafe Conditions": 1980, "Near Miss": 820,
    },
    date(2025, 4, 1): {
        "Diesel Consumed": 625, "Petrol Consumed": 205, "LPG Consumed": 358, "Grid Electricity Consumed": 23200,
        "Refrigerant Leakage — R-134a": 4.0, "Battery Production Volume": 23.7, "Revenue": 77,
        "Surface Water Withdrawal": 1105, "Ground Water Withdrawal": 947, "Third-Party Water Withdrawal": 789, "Packaging Drinking Water": 316,
        "Hazardous Waste Generated": 30.8, "Non-Hazardous Waste Generated": 46.2,
        "Fatality": 0, "LTIFR": 0.73, "Defensive Driving Training": 65, "Unsafe Conditions": 1650, "Near Miss": 710,
    },
    date(2025, 5, 1): {
        "Diesel Consumed": 605, "Petrol Consumed": 198, "LPG Consumed": 350, "Grid Electricity Consumed": 22700,
        "Refrigerant Leakage — R-134a": 3.6, "Battery Production Volume": 26.3, "Revenue": 82,
        "Surface Water Withdrawal": 1198, "Ground Water Withdrawal": 1027, "Third-Party Water Withdrawal": 856, "Packaging Drinking Water": 342,
        "Hazardous Waste Generated": 33.9, "Non-Hazardous Waste Generated": 50.8,
        "Fatality": 1, "LTIFR": 0.68, "Defensive Driving Training": 68, "Unsafe Conditions": 1320, "Near Miss": 610,
    },
    date(2025, 6, 1): {
        "Diesel Consumed": 575, "Petrol Consumed": 190, "LPG Consumed": 340, "Grid Electricity Consumed": 22400,
        "Refrigerant Leakage — R-134a": 3.0, "Battery Production Volume": 30.1, "Revenue": 90,
        "Surface Water Withdrawal": 1340, "Ground Water Withdrawal": 1149, "Third-Party Water Withdrawal": 958, "Packaging Drinking Water": 383,
        "Hazardous Waste Generated": 41.9, "Non-Hazardous Waste Generated": 62.9,
        "Fatality": 0, "LTIFR": 0.64, "Defensive Driving Training": 70, "Unsafe Conditions": 1050, "Near Miss": 540,
    },
    date(2025, 7, 1): {
        "Diesel Consumed": 550, "Petrol Consumed": 185, "LPG Consumed": 328, "Grid Electricity Consumed": 21600,
        "Refrigerant Leakage — R-134a": 2.5, "Battery Production Volume": 28.7, "Revenue": 93,
        "Surface Water Withdrawal": 1258, "Ground Water Withdrawal": 1078, "Third-Party Water Withdrawal": 899, "Packaging Drinking Water": 360,
        "Hazardous Waste Generated": 38.6, "Non-Hazardous Waste Generated": 57.9,
        "Fatality": 0, "LTIFR": 0.60, "Defensive Driving Training": 72, "Unsafe Conditions": 820, "Near Miss": 470,
    },
    date(2025, 8, 1): {
        "Diesel Consumed": 535, "Petrol Consumed": 178, "LPG Consumed": 318, "Grid Electricity Consumed": 21200,
        "Refrigerant Leakage — R-134a": 2.2, "Battery Production Volume": 27.0, "Revenue": 96,
        "Surface Water Withdrawal": 1155, "Ground Water Withdrawal": 990, "Third-Party Water Withdrawal": 825, "Packaging Drinking Water": 330,
        "Hazardous Waste Generated": 35.4, "Non-Hazardous Waste Generated": 53.1,
        "Fatality": 0, "LTIFR": 0.58, "Defensive Driving Training": 74, "Unsafe Conditions": 640, "Near Miss": 410,
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
                calc = calculate_entry(db, entry, tenant.id, approver.id)
                db.commit()
                created += 1

        print(f"created {created} entries across {len(MONTHS)} prior-fiscal-year months")
        if skipped_missing_dp:
            print("skipped -- data point not found:", sorted(set(skipped_missing_dp)))
    finally:
        db.close()


if __name__ == "__main__":
    main()
