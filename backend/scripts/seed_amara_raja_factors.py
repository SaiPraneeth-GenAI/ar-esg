"""Seeds Amara Raja's tenant-specific EmissionFactor rows (Prompt 3f, part
2) -- these are the actual factors the tenant's own GHG inventory workbook
uses, distinct from (and in most cases slightly different than) the
seeded ipcc_reference defaults. Each row links back to the ipcc_reference
row it was cross-checked against via ipcc_reference_key, wherever a clean
match exists.

Run seed_ipcc_reference.py first -- this script looks up reference rows by
name and will skip the link (not the row) if no match is found. Idempotent:
skips any row that already exists for this tenant (same scope + name/
category + effective_year).
"""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.models import EmissionFactor, IpccReference, Tenant, User  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402

TENANT_NAME = "Amara Raja"
ADMIN_EMAIL = "saipraneeth836@gmail.com"
EFFECTIVE_YEAR = 2026
WORKBOOK = "GHG_Inventory_FY26_AREM"


def find_ref(db, substance_name: str, publication: str | None = None, scope3_category: str | None = None) -> IpccReference | None:
    q = db.query(IpccReference).filter(IpccReference.substance_name == substance_name)
    if publication:
        q = q.filter(IpccReference.publication == publication)
    if scope3_category:
        q = q.filter(IpccReference.scope3_category == scope3_category)
    return q.first()


def main() -> None:
    db = SessionLocal()
    try:
        tenant = db.query(Tenant).filter(Tenant.name == TENANT_NAME).first()
        if tenant is None:
            print(f"Tenant '{TENANT_NAME}' not found -- run seed_admin.py first. Aborting.")
            return
        admin = db.query(User).filter(User.email == ADMIN_EMAIL).first()
        created_by = admin.id if admin else None

        created = 0

        def add(scope: int, *, gas_type=None, method=None, scope3_category=None, description=None, unit, value, source_reference, ref: IpccReference | None):
            nonlocal created
            existing = (
                db.query(EmissionFactor)
                .filter(
                    EmissionFactor.tenant_id == tenant.id,
                    EmissionFactor.scope == scope,
                    EmissionFactor.gas_type == gas_type,
                    EmissionFactor.method == method,
                    EmissionFactor.scope3_category == scope3_category,
                    EmissionFactor.description == description,
                    EmissionFactor.effective_date == date(EFFECTIVE_YEAR, 1, 1),
                )
                .first()
            )
            if existing:
                return
            db.add(
                EmissionFactor(
                    tenant_id=tenant.id,
                    scope=scope,
                    gas_type=gas_type,
                    method=method,
                    scope3_category=scope3_category,
                    description=description,
                    unit=unit,
                    factor_value=value,
                    effective_date=date(EFFECTIVE_YEAR, 1, 1),
                    version=f"FY{str(EFFECTIVE_YEAR)[2:]}",
                    source="Amara Raja GHG Inventory",
                    source_reference=source_reference,
                    ipcc_reference_key=ref.id if ref else None,
                    created_by=created_by,
                    is_active=True,
                )
            )
            created += 1

        # ---- Scope 1: fuels ----
        add(1, gas_type="Diesel", unit="kg CO2e/litre", value=2.697,
            source_reference=f"{WORKBOOK}, Scope-1 tab",
            ref=find_ref(db, "Diesel", "IPCC_2006_Vol2"))
        add(1, gas_type="Liquefied Petroleum Gas", unit="kg CO2e/kg", value=2.94,
            source_reference=f"{WORKBOOK}, Scope-1 tab",
            ref=find_ref(db, "Liquefied Petroleum Gas", "IPCC_2006_Vol2"))
        add(1, gas_type="Acetylene", unit="kg CO2e/kg", value=3.92,
            source_reference=f"{WORKBOOK}, Scope-1 tab",
            ref=find_ref(db, "Acetylene", "IPCC_2006_Vol2"))

        # ---- Scope 2: grid electricity ----
        add(2, method="location-based", unit="t CO2e/MWh", value=0.710,
            source_reference=f"{WORKBOOK}, Scope-2 tab, CEA V21 (FY2024-25)",
            ref=find_ref(db, "India Grid Electricity (All-India weighted average)", "CEA_V21"))

        # ---- Scope 2: refrigerant GWP (AR6 Aug 2024) ----
        for gas, value in [("R-134a", 1530), ("R-32", 677), ("R-22", 1760), ("R-404A", 3942), ("R-407C", 1774), ("R-410A", 2088)]:
            add(2, gas_type=gas, unit="GWP-100", value=value,
                source_reference=f"{WORKBOOK}, Scope-1 tab, IPCC AR6 Aug 2024 revision",
                ref=find_ref(db, gas, "IPCC_AR6_Aug2024"))

        # ---- Scope 3: verified categories ----
        # description, scope3_category, value, unit, source_suffix,
        # (ipcc_reference substance_name, ipcc_reference scope3_category) for the lookup
        scope3 = [
            ("Purchased Goods and Services", "Purchased Goods & Services", 0.187, "kg CO2e/USD", "DEFRA 2024 proxy",
             ("Purchased Goods and Services", None)),
            ("Capital Goods", "Capital Goods", 0.241, "kg CO2e/USD", "DEFRA 2024 proxy",
             ("Capital Goods", None)),
            ("Fuel and Energy Related Activities", "Fuel and Energy Related Activities", 0.024, "kg CO2e/MWh", "IPCC 2006",
             ("Fuel and Energy Related Activities", None)),
            ("Upstream Transportation and Distribution", "Upstream Transport", 0.098, "kg CO2e/ton-km", "DEFRA 2024 HGV",
             ("Upstream Transportation and Distribution", None)),
            ("Waste Generated in Operations (Incineration)", "Waste Generated in Operations", 0.0012, "kg CO2e/ton", "IPCC 2006 incineration",
             ("Waste Generated in Operations", "Waste Incineration")),
            ("Waste Generated in Operations (Landfill)", "Waste Generated in Operations", 0.193, "kg CO2e/ton", "IPCC 2006 landfill CH4",
             ("Waste Generated in Operations", "Landfill Disposal")),
            ("Business Travel (Air)", "Business Travel", 0.245, "kg CO2e/km", "DEFRA 2024 international flights",
             ("Business Travel", "Air Travel")),
            ("Business Travel (Rail)", "Business Travel", 0.041, "kg CO2e/km", "DEFRA 2024 national rail",
             ("Business Travel", "Rail Travel")),
            ("Employee Commuting", "Employee Commuting", 0.192, "kg CO2e/km", "DEFRA 2024 average car",
             ("Employee Commuting", None)),
            ("Upstream Leased Assets", "Upstream Leased Assets", 0.210, "kg CO2e/kWh", "CEA V21 location-based",
             ("Upstream Leased Assets", None)),
            ("Downstream Transportation and Distribution", "Downstream Transport", 0.098, "kg CO2e/ton-km", "DEFRA 2024 HGV",
             ("Downstream Transportation and Distribution", None)),
            ("Use of Sold Products", "Use of Sold Products", 0.710, "t CO2e/MWh", "CEA V21 India grid",
             ("Use of Sold Products", None)),
            ("End-of-Life Treatment of Sold Products", "End-of-Life Treatment", 0.045, "kg CO2e/ton", "IPCC 2006 recycling",
             ("End-of-Life Treatment of Sold Products", None)),
            ("Franchises", "Franchises", 0.187, "kg CO2e/USD", "DEFRA 2024 proxy",
             ("Franchises", None)),
        ]
        for description, scope3_category, value, unit, source_suffix, (ref_substance, ref_scope3_category) in scope3:
            ref = find_ref(db, ref_substance, scope3_category=ref_scope3_category)
            add(3, scope3_category=scope3_category, description=description, unit=unit, value=value,
                source_reference=f"{WORKBOOK}, Scope-3 tab, {source_suffix}", ref=ref)

        db.commit()
        print(f"created {created} Amara Raja emission_factor rows")
    finally:
        db.close()


if __name__ == "__main__":
    main()
