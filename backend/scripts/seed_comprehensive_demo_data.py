"""Comprehensive, clearly-labeled demo dataset covering every category the
rebuilt dashboard reads from: GHG sources (Air Emissions), Water, Waste,
Production, Revenue, and Safety -- six consecutive months (Mar-Aug 2026),
submitted and approved directly (bypassing the self-approval guard, since
this is a scripted one-shot seed). Every entry carries
note = "Demo data -- dashboard rebuild walkthrough" for later identification.

Sample data for demonstration only, picked to show a plausible improving
trend (declining fuel/refrigerant/water/waste per unit of rising
production), nothing more -- not sourced from any reference image.
"""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.models import Approval, AuditLog, Category, DataPoint, Entry, Location, Tenant, User  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.services.carbon_calculation import calculate_entry  # noqa: E402
from app.services.rollups import recompute_rollup_for_entry  # noqa: E402

NOTE = "Demo data -- dashboard rebuild walkthrough"

MONTHS = [date(2026, m, 1) for m in range(3, 9)]  # Mar..Aug 2026

# month -> {data_point_name: value}
MONTHLY_DATA: dict[date, dict[str, float]] = {
    date(2026, 3, 1): {
        "Diesel Consumed": 540, "Petrol Consumed": 180, "LPG Consumed": 310, "Grid Electricity Consumed": 20200,
        "Refrigerant Leakage — R-134a": 3.6, "Battery Production Volume": 29.0, "Revenue": 98,
        "Surface Water Withdrawal": 1015, "Ground Water Withdrawal": 870, "Third-Party Water Withdrawal": 725, "Packaging Drinking Water": 290,
        "Hazardous Waste Generated": 27.2, "Non-Hazardous Waste Generated": 40.8,
        "Fatality": 0, "LTIFR": 0.66, "Defensive Driving Training": 75, "Unsafe Conditions": 1481, "Near Miss": 600,
    },
    date(2026, 4, 1): {
        "Diesel Consumed": 520, "Petrol Consumed": 175, "LPG Consumed": 300, "Grid Electricity Consumed": 19500,
        "Refrigerant Leakage — R-134a": 3.2, "Battery Production Volume": 30.6, "Revenue": 102,
        "Surface Water Withdrawal": 950, "Ground Water Withdrawal": 815, "Third-Party Water Withdrawal": 679, "Packaging Drinking Water": 271,
        "Hazardous Waste Generated": 25.5, "Non-Hazardous Waste Generated": 38.3,
        "Fatality": 1, "LTIFR": 0.60, "Defensive Driving Training": 78, "Unsafe Conditions": 1200, "Near Miss": 500,
    },
    date(2026, 5, 1): {
        "Diesel Consumed": 505, "Petrol Consumed": 170, "LPG Consumed": 295, "Grid Electricity Consumed": 19000,
        "Refrigerant Leakage — R-134a": 2.9, "Battery Production Volume": 34.0, "Revenue": 108,
        "Surface Water Withdrawal": 1033, "Ground Water Withdrawal": 885, "Third-Party Water Withdrawal": 738, "Packaging Drinking Water": 295,
        "Hazardous Waste Generated": 28.0, "Non-Hazardous Waste Generated": 42.0,
        "Fatality": 0, "LTIFR": 0.55, "Defensive Driving Training": 80, "Unsafe Conditions": 900, "Near Miss": 420,
    },
    date(2026, 6, 1): {
        "Diesel Consumed": 480, "Petrol Consumed": 165, "LPG Consumed": 285, "Grid Electricity Consumed": 18800,
        "Refrigerant Leakage — R-134a": 2.4, "Battery Production Volume": 39.0, "Revenue": 118,
        "Surface Water Withdrawal": 1158, "Ground Water Withdrawal": 993, "Third-Party Water Withdrawal": 828, "Packaging Drinking Water": 331,
        "Hazardous Waste Generated": 35.6, "Non-Hazardous Waste Generated": 53.4,
        "Fatality": 0, "LTIFR": 0.52, "Defensive Driving Training": 83, "Unsafe Conditions": 700, "Near Miss": 380,
    },
    date(2026, 7, 1): {
        "Diesel Consumed": 460, "Petrol Consumed": 160, "LPG Consumed": 275, "Grid Electricity Consumed": 18200,
        "Refrigerant Leakage — R-134a": 2.0, "Battery Production Volume": 37.2, "Revenue": 121,
        "Surface Water Withdrawal": 1085, "Ground Water Withdrawal": 930, "Third-Party Water Withdrawal": 775, "Packaging Drinking Water": 310,
        "Hazardous Waste Generated": 32.8, "Non-Hazardous Waste Generated": 49.2,
        "Fatality": 0, "LTIFR": 0.49, "Defensive Driving Training": 86, "Unsafe Conditions": 550, "Near Miss": 340,
    },
    date(2026, 8, 1): {
        "Diesel Consumed": 450, "Petrol Consumed": 155, "LPG Consumed": 270, "Grid Electricity Consumed": 18000,
        "Refrigerant Leakage — R-134a": 1.8, "Battery Production Volume": 35.0, "Revenue": 125,
        "Surface Water Withdrawal": 998, "Ground Water Withdrawal": 855, "Third-Party Water Withdrawal": 713, "Packaging Drinking Water": 285,
        "Hazardous Waste Generated": 30.0, "Non-Hazardous Waste Generated": 45.0,
        "Fatality": 0, "LTIFR": 0.49, "Defensive Driving Training": 81.2, "Unsafe Conditions": 436, "Near Miss": 332,
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

        print(f"created {created} entries across {len(MONTHS)} months")
        if skipped_missing_dp:
            print("skipped -- data point not found:", sorted(set(skipped_missing_dp)))
    finally:
        db.close()


if __name__ == "__main__":
    main()
