"""Seeds a small, clearly-labeled demo dataset so the carbon dashboard has
something to show immediately -- five consecutive months (Apr-Aug 2026,
ending at the current month so it's visible without changing the period
picker) of Diesel, Grid Electricity, refrigerant leakage, and battery
production, submitted and approved directly (bypassing the self-approval
guard the real API enforces, since this is a scripted one-shot seed, not a
real submission).

Every entry carries a note identifying it as demo data, so it can be found
and removed later: note = "Demo data -- carbon dashboard walkthrough".

This is sample data for demonstration, explicitly NOT sourced from any
reference image or spreadsheet -- picked to show a plausible improving
trend (declining fuel/refrigerant use, rising production), nothing more.
"""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.models import Approval, AuditLog, Category, DataPoint, Entry, Location, Tenant, User  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.services.carbon_calculation import calculate_entry  # noqa: E402

NOTE = "Demo data -- carbon dashboard walkthrough"

# month -> {data_point_name: value}
MONTHLY_DATA = {
    date(2026, 4, 1): {"Diesel Consumed": 520, "Grid Electricity Consumed": 19500, "Refrigerant Leakage — R-134a": 3.2, "Battery Production Volume": 32},
    date(2026, 5, 1): {"Diesel Consumed": 505, "Grid Electricity Consumed": 19000, "Refrigerant Leakage — R-134a": 2.9, "Battery Production Volume": 33},
    date(2026, 6, 1): {"Diesel Consumed": 480, "Grid Electricity Consumed": 18800, "Refrigerant Leakage — R-134a": 2.4, "Battery Production Volume": 34},
    date(2026, 7, 1): {"Diesel Consumed": 460, "Grid Electricity Consumed": 18200, "Refrigerant Leakage — R-134a": 2.0, "Battery Production Volume": 34.5},
    date(2026, 8, 1): {"Diesel Consumed": 450, "Grid Electricity Consumed": 18000, "Refrigerant Leakage — R-134a": 1.8, "Battery Production Volume": 35},
}


def main() -> None:
    db = SessionLocal()
    created_entry_ids = []
    try:
        tenant = db.query(Tenant).filter(Tenant.name == "Amara Raja").first()
        location = db.query(Location).filter(Location.tenant_id == tenant.id).first()
        admin = db.query(User).filter(User.email == "saipraneeth836@gmail.com").first()

        def get_dp(name):
            return (
                db.query(DataPoint)
                .join(Category, Category.id == DataPoint.category_id)
                .filter(Category.tenant_id == tenant.id, DataPoint.name == name)
                .first()
            )

        for period, values in MONTHLY_DATA.items():
            for dp_name, value in values.items():
                dp = get_dp(dp_name)
                if dp is None:
                    print(f"SKIP: data point '{dp_name}' not found")
                    continue

                existing = (
                    db.query(Entry)
                    .filter(Entry.data_point_id == dp.id, Entry.location_id == location.id, Entry.period == period)
                    .first()
                )
                if existing is not None:
                    print(f"SKIP: {dp_name} already has an entry for {period} (status={existing.status})")
                    continue

                entry = Entry(
                    data_point_id=dp.id,
                    location_id=location.id,
                    period=period,
                    value=value,
                    method_of_entry="Manual",
                    status="Approved",
                    submitted_by=admin.id,
                    note=NOTE,
                )
                db.add(entry)
                db.commit()
                db.refresh(entry)
                created_entry_ids.append(entry.id)

                db.add(Approval(entry_id=entry.id, approver_id=admin.id, action="approve"))
                db.add(
                    AuditLog(
                        entry_id=entry.id, actor=admin.email, action="approved",
                        old_value="Draft", new_value="Approved (demo seed)",
                    )
                )
                db.commit()

                calc = calculate_entry(db, entry, tenant.id, admin.id)
                db.commit()
                status = calc.status if calc else "not_a_ghg_source"
                print(f"{period} {dp_name} = {value}: entry created, calculation status = {status}")

        print(f"\ncreated {len(created_entry_ids)} demo entries, all tagged note='{NOTE}'")
    finally:
        db.close()


if __name__ == "__main__":
    main()
