"""Idempotently add missing org-wide demo targets for a tenant.

Run inside the deployed application container. Dry-run is the default;
pass --apply to persist. Existing active targets are never changed.
"""

import argparse
from datetime import date

from app.api.routes.targets import activate_target, create_target
from app.core.auth import CurrentUser
from app.db.models import EmissionTarget, Tenant, User
from app.db.session import SessionLocal
from app.schemas.targets import TargetActivateRequest, TargetCreate
from app.services.demo_data import _TARGET_SPECS
from app.services.target_calculation import compute_baseline, target_from_percentage

BASELINE_START = date(2025, 1, 1)
BASELINE_END = date(2025, 12, 1)
TARGET_START = date(2026, 1, 1)
TARGET_END = date(2026, 12, 1)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant", default="Amara Raja")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    if SessionLocal is None:
        raise RuntimeError("DATABASE_URL is not configured")

    db = SessionLocal()
    try:
        tenant = db.query(Tenant).filter(Tenant.name == args.tenant).first()
        if tenant is None:
            raise RuntimeError(f"Tenant not found: {args.tenant}")
        actor = (
            db.query(User)
            .filter(User.tenant_id == tenant.id, User.roles.any("Admin"))
            .order_by(User.email)
            .first()
        )
        if actor is None:
            raise RuntimeError(f"No Admin user found for tenant: {args.tenant}")

        current = CurrentUser(id=str(actor.id), email=actor.email, roles=["Admin"], tenant_id=tenant.id)
        active_keys = {
            row.metric_key
            for row in db.query(EmissionTarget).filter(
                EmissionTarget.tenant_id == tenant.id,
                EmissionTarget.location_id.is_(None),
                EmissionTarget.status == "active",
            )
        }
        missing = [key for key in _TARGET_SPECS if key not in active_keys]
        print(f"tenant={tenant.name} active={len(active_keys)} missing={len(missing)} apply={args.apply}")

        created = 0
        for metric_key in missing:
            percentage, rationale = _TARGET_SPECS[metric_key]
            baseline = compute_baseline(
                db, tenant.id, None, metric_key, BASELINE_START, BASELINE_END
            )
            if not baseline.ready or baseline.baseline_value is None:
                print(f"SKIP {metric_key}: {baseline.message}")
                continue
            target_value = target_from_percentage(baseline.baseline_value, percentage, metric_key)
            print(
                f"{'CREATE' if args.apply else 'WOULD_CREATE'} {metric_key}: "
                f"target={target_value:.6g} ({percentage:g}% improvement)"
            )
            if not args.apply:
                continue

            target = create_target(
                TargetCreate(
                    location_id=None,
                    metric_key=metric_key,
                    baseline_period_start=BASELINE_START,
                    baseline_period_end=BASELINE_END,
                    target_period_start=TARGET_START,
                    target_period_end=TARGET_END,
                    reduction_percentage=percentage,
                    target_value=target_value,
                    owner_id=actor.id,
                    rationale=rationale,
                ),
                current,
                db,
            )
            activate_target(target.id, TargetActivateRequest(rationale=rationale), current, db)
            created += 1

        final_active = db.query(EmissionTarget).filter(
            EmissionTarget.tenant_id == tenant.id,
            EmissionTarget.location_id.is_(None),
            EmissionTarget.status == "active",
        ).count()
        print(f"created={created} final_active={final_active}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
