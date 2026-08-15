"""One-time fix: Effluent Monitoring's fields were seeded as provisional
placeholders (pH (Placeholder), BOD (Placeholder), COD (Placeholder)).
The fields are finalized now -- rename them and clear the provisional flag
so the category no longer reads as unfinished in the UI.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.models import Category, DataPoint, Tenant  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402

TENANT_NAME = "Amara Raja"
CATEGORY_NAME = "Effluent Monitoring"

RENAMES = {
    "pH (Placeholder)": "pH",
    "BOD (Placeholder)": "BOD",
    "COD (Placeholder)": "COD",
}


def main() -> None:
    db = SessionLocal()
    try:
        tenant = db.query(Tenant).filter(Tenant.name == TENANT_NAME).first()
        if tenant is None:
            raise SystemExit(f"Tenant '{TENANT_NAME}' not found")

        category = db.query(Category).filter(Category.tenant_id == tenant.id, Category.name == CATEGORY_NAME).first()
        if category is None:
            raise SystemExit(f"Category '{CATEGORY_NAME}' not found")

        data_points = db.query(DataPoint).filter(DataPoint.category_id == category.id).all()
        for dp in data_points:
            new_name = RENAMES.get(dp.name, dp.name)
            if new_name != dp.name:
                dp.name = new_name
            if dp.validation_rules and dp.validation_rules.get("provisional"):
                rules = {k: v for k, v in dp.validation_rules.items() if k != "provisional"}
                dp.validation_rules = rules or None
            print(f"updated {dp.name}")
        db.commit()
        print("done")
    finally:
        db.close()


if __name__ == "__main__":
    main()
