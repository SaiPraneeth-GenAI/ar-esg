"""One-time data correction: refrigerant GWP factors (R-134a, R-32, R-22,
R-404A, R-407C, R-410A) were seeded under Scope 2 in the Prompt 3f dataset,
following that prompt's own table heading. Prompt 4 explicitly and
authoritatively corrects this: "Refrigerant leakage is Scope 1 fugitive
emissions, not an ODS total." Fugitive refrigerant leaks are Scope 1 under
the GHG Protocol -- this was a data-classification error carried over from
the earlier prompt, not a deliberate modelling choice, so it's corrected
here rather than worked around in the calculation-mapping layer.

Affects both the seeded ipcc_reference rows and Amara Raja's own tenant
emission_factor rows for the same six substances. Idempotent: safe to
re-run.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.models import EmissionFactor, IpccReference  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402

REFRIGERANTS = ["R-134a", "R-32", "R-22", "R-404A", "R-407C", "R-410A"]


def main() -> None:
    db = SessionLocal()
    try:
        ref_updated = (
            db.query(IpccReference)
            .filter(IpccReference.factor_type == "gwp", IpccReference.substance_name.in_(REFRIGERANTS), IpccReference.scope == 2)
            .update({"scope": 1}, synchronize_session=False)
        )
        factor_updated = (
            db.query(EmissionFactor)
            .filter(EmissionFactor.gas_type.in_(REFRIGERANTS), EmissionFactor.scope == 2)
            .update({"scope": 1}, synchronize_session=False)
        )
        db.commit()
        print(f"ipcc_reference rows corrected: {ref_updated}")
        print(f"emission_factor rows corrected: {factor_updated}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
