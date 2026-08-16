"""Activates the two fully-supported targets from Prompt 4's recommended
structure, using the real 6-month baseline (Mar-Aug 2026) the comprehensive
demo seed already produced:

1. Primary: Scope 1+2 location-based intensity (tCO2e/MnAh), 10% reduction.
2. Secondary guardrail: Scope 1+2 location-based absolute (tCO2e), 8% reduction.

The third recommended target -- Scope 2 market-based, shown beside
location-based as a disclosure figure -- is deliberately NOT seeded here:
the calculation engine only ever resolves grid electricity as
location-based today (see carbon_mapping._tenant_factor_matches), so a
market-based target would never have real data to baseline against.
Activating it anyway would mean seeding a target the platform can't
actually track, which is exactly the kind of misleading number Prompt 4
prohibits.

Uses the real create_target/activate_target service functions, not direct
row inserts, so the baseline is computed and locked exactly the way a real
user's activation would be.
"""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.auth import CurrentUser  # noqa: E402
from app.db.models import Tenant, User  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.api.routes import targets as targets_routes  # noqa: E402
from app.schemas.targets import BaselinePreviewRequest, TargetActivateRequest, TargetCreate  # noqa: E402

BASELINE_START = date(2026, 3, 1)
BASELINE_END = date(2026, 8, 1)
TARGET_START = date(2026, 9, 1)
TARGET_END = date(2027, 8, 1)


def main() -> None:
    db = SessionLocal()
    try:
        tenant = db.query(Tenant).filter(Tenant.name == "Amara Raja").first()
        approver = db.query(User).filter(User.email == "saipraneeth836@gmail.com").first()
        current = CurrentUser(id=str(approver.id), email=approver.email, roles=["Admin"], tenant_id=tenant.id)

        specs = [
            {
                "scope": "1_2_combined",
                "calculation_method": "location_based",
                "metric_type": "intensity_tco2e_per_mnah",
                "reduction_percentage": 10.0,
                "rationale": "Primary target -- 10% reduction in Scope 1+2 location-based intensity vs the Mar-Aug 2026 baseline, aligned with the battery-manufacturing intensity KPI.",
            },
            {
                "scope": "1_2_combined",
                "calculation_method": "location_based",
                "metric_type": "absolute_tco2e",
                "reduction_percentage": 8.0,
                "rationale": "Secondary guardrail -- 8% reduction in absolute Scope 1+2 location-based emissions, shown alongside the intensity target so production growth alone can't obscure an absolute increase.",
            },
        ]

        for spec in specs:
            # Mirrors what the wizard UI does: preview the baseline first,
            # compute the scenario's target value from it, and only then
            # create the target -- the user reviews the actual computed
            # number before it's ever persisted, per Prompt 4's rule that
            # a reduction percentage is a decision, not an auto-commit.
            preview = targets_routes.baseline_preview(
                BaselinePreviewRequest(
                    location_id=None,
                    scope=spec["scope"],
                    calculation_method=spec["calculation_method"],
                    metric_type=spec["metric_type"],
                    baseline_period_start=BASELINE_START,
                    baseline_period_end=BASELINE_END,
                ),
                current,
                db,
            )
            if not preview.ready or preview.baseline_value is None:
                print(f"SKIP {spec['metric_type']}: baseline not ready -- {preview.message}")
                continue
            target_value = preview.baseline_value * (1 - spec["reduction_percentage"] / 100)

            payload = TargetCreate(
                location_id=None,
                scope=spec["scope"],
                calculation_method=spec["calculation_method"],
                metric_type=spec["metric_type"],
                baseline_period_start=BASELINE_START,
                baseline_period_end=BASELINE_END,
                target_period_start=TARGET_START,
                target_period_end=TARGET_END,
                reduction_percentage=spec["reduction_percentage"],
                target_value=target_value,
                owner_id=approver.id,
                rationale=None,
            )
            created = targets_routes.create_target(payload, current, db)
            print(f"created draft {created.id} ({spec['metric_type']}), baseline={created.baseline_value}, target_value={created.target_value}")

            activated = targets_routes.activate_target(
                created.id, TargetActivateRequest(rationale=spec["rationale"]), current, db
            )
            print(f"  activated: baseline={activated.baseline_value}, target_value={activated.target_value}, status={activated.status}")

        print("done")
    finally:
        db.close()


if __name__ == "__main__":
    main()
