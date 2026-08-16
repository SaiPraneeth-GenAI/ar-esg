"""Explicit, one-shot destructive reset for the Amara Raja tenant: deletes
every Entry (cascading to Approval/AuditLog/Attachment/EmissionCalculation
via FK ondelete=CASCADE) and every EmissionTarget row, so the dashboard
rebuild can be verified against a fully-known, comprehensively-seeded
dataset. Does NOT touch Category/DataPoint config, the EmissionFactor/
IpccReference libraries, Users, Locations, or the Production/Revenue
mapping config rows -- only the two tables explicitly requested.

Run once, immediately followed by seed_comprehensive_demo_data.py.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.models import Entry, EmissionTarget, Location, Tenant  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402


def main() -> None:
    db = SessionLocal()
    try:
        tenant = db.query(Tenant).filter(Tenant.name == "Amara Raja").first()
        if tenant is None:
            raise SystemExit("Tenant 'Amara Raja' not found")

        location_ids = [loc.id for loc in db.query(Location).filter(Location.tenant_id == tenant.id).all()]

        entry_count = db.query(Entry).filter(Entry.location_id.in_(location_ids)).count()
        target_count = db.query(EmissionTarget).filter(EmissionTarget.tenant_id == tenant.id).count()
        print(f"about to delete {entry_count} entries and {target_count} targets for tenant {tenant.name}")

        db.query(Entry).filter(Entry.location_id.in_(location_ids)).delete(synchronize_session=False)
        db.query(EmissionTarget).filter(EmissionTarget.tenant_id == tenant.id).delete(synchronize_session=False)
        db.commit()

        print("done")
    finally:
        db.close()


if __name__ == "__main__":
    main()
