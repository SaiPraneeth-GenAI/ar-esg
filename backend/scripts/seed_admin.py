"""One-time seed: creates the single default Admin account that exists before
anyone logs in. Everyone else gets added from inside the app by this Admin.

NOTE: ADMIN_PASSWORD below is a placeholder for the demo only -- change it
immediately after first login, it is not meant to stay as-is.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.supabase_admin import create_auth_user, get_auth_user_by_email  # noqa: E402
from app.db.models import Location, Tenant, User  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402

ADMIN_EMAIL = "saipraneeth836@gmail.com"
ADMIN_PASSWORD = "admin@123456"  # demo placeholder -- rotate after first login
DEFAULT_TENANT_NAME = "Amara Raja"
DEFAULT_LOCATION_NAME = "ARE&M"


def main() -> None:
    db = SessionLocal()
    try:
        tenant = db.query(Tenant).filter(Tenant.name == DEFAULT_TENANT_NAME).first()
        if tenant is None:
            tenant = Tenant(name=DEFAULT_TENANT_NAME, industry_vertical="battery manufacturing")
            db.add(tenant)
            db.commit()
            db.refresh(tenant)
            print(f"created tenant {tenant.id}")

        location = (
            db.query(Location)
            .filter(Location.tenant_id == tenant.id, Location.name == DEFAULT_LOCATION_NAME)
            .first()
        )
        if location is None:
            location = Location(tenant_id=tenant.id, name=DEFAULT_LOCATION_NAME, plant_type="battery manufacturing")
            db.add(location)
            db.commit()
            db.refresh(location)
            print(f"created location {location.id}")

        if db.query(User).filter(User.email == ADMIN_EMAIL).first() is not None:
            print("admin app_user row already exists, skipping")
            return

        auth_user = get_auth_user_by_email(ADMIN_EMAIL)
        if auth_user is None:
            auth_user = create_auth_user(
                email=ADMIN_EMAIL,
                password=ADMIN_PASSWORD,
                app_metadata={"roles": ["Admin"], "tenant_id": str(tenant.id)},
            )
            print(f"created Supabase auth user {auth_user['id']}")
        else:
            print("Supabase auth user already exists, reusing")

        user = User(
            id=auth_user["id"],
            tenant_id=tenant.id,
            email=ADMIN_EMAIL,
            roles=["Admin"],
            location_scope=[location.id],
            auth_provider="email",
        )
        db.add(user)
        db.commit()
        print(f"created app_user row {user.id}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
