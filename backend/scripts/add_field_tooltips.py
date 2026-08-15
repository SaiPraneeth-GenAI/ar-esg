"""Adds a tooltip (short definition) and an example value to every data
point's validation_rules JSON, for the info-icon hover in the entry form.

NOTE on sourcing: docs/data_model_and_dictionary.md documents the database
schema (table/field/type), not field-level ESG glossary text -- it has no
per-data-point definitions to pull from for fields like "Ground Water
Withdrawal" or "R-134a". These definitions are written here using standard
ESG/BRSR/CPCB terminology so they're accurate and consistent, not literally
copied from that doc since it doesn't contain this content.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.models import Category, DataPoint, Tenant  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402

TENANT_NAME = "Amara Raja"

# data point name -> (tooltip, example)
DEFINITIONS: dict[str, tuple[str, str]] = {
    "Surface Water Withdrawal": (
        "Water drawn from rivers, lakes, or other surface water bodies for site use.",
        "e.g. 420 KL this month"
    ),
    "Ground Water Withdrawal": (
        "Water extracted from borewells or other groundwater sources on-site.",
        "e.g. 2,600 KL this month"
    ),
    "Third-Party Water Withdrawal": (
        "Water purchased from a municipal supply or other external/third-party source.",
        "e.g. 410 KL this month"
    ),
    "Packaging Drinking Water": (
        "Packaged/bottled drinking water procured for on-site consumption (not process use).",
        "e.g. 8 KL this month"
    ),
    "Total Treated Effluent Generated": (
        "Total volume of wastewater processed through this treatment plant in the period.",
        "e.g. 1,200 KL this month"
    ),
    "Recycled Water Used for Process": (
        "Treated water reused in production processes instead of drawing fresh water.",
        "e.g. 300 KL this month"
    ),
    "Recycled Water Used for Irrigation": (
        "Treated water reused for landscaping or irrigation instead of drawing fresh water.",
        "e.g. 50 KL this month"
    ),
    "R-22": ("Quantity of R-22 (HCFC-22) refrigerant handled, topped up, or known to have leaked.", "e.g. 2.5 kg"),
    "R-134a": ("Quantity of R-134a (HFC) refrigerant handled, topped up, or known to have leaked.", "e.g. 1.8 kg"),
    "R-32": ("Quantity of R-32 (HFC) refrigerant handled, topped up, or known to have leaked.", "e.g. 3.0 kg"),
    "Halon": ("Quantity of Halon (fire-suppression ODS) handled or known to have leaked.", "e.g. 0.5 kg"),
    "pH": ("Acidity/alkalinity of the effluent sample, measured on the 0-14 pH scale.", "e.g. 7.2"),
    "BOD": ("Biochemical Oxygen Demand -- oxygen consumed by microorganisms breaking down organic matter in the effluent.", "e.g. 25 mg/L"),
    "COD": ("Chemical Oxygen Demand -- oxygen required to chemically oxidize pollutants in the effluent.", "e.g. 80 mg/L"),
    "Diesel Consumed": ("Diesel fuel burned on-site (generators, vehicles, equipment) -- a Scope 1 emissions source.", "e.g. 450 litres"),
    "Petrol Consumed": ("Petrol/gasoline burned on-site -- a Scope 1 emissions source.", "e.g. 60 litres"),
    "LPG Consumed": ("LPG burned on-site (canteens, process heating) -- a Scope 1 emissions source.", "e.g. 120 kg"),
    "Coal Consumed": ("Coal burned on-site (boilers, furnaces) -- a Scope 1 emissions source.", "e.g. 2,000 kg"),
    "Grid Electricity Consumed": ("Electricity drawn from the grid -- the basis for Scope 2 emissions.", "e.g. 85,000 kWh"),
    "Renewable / PPA-Covered Percentage": (
        "Share of this period's grid electricity covered by renewable generation or a Power Purchase Agreement.",
        "e.g. 18 (%)"
    ),
    "Battery Production Volume": ("Total battery output for the period, used as the denominator for intensity metrics.", "e.g. 35 Mn Ah"),
    "Hazardous Waste Generated": ("Legacy aggregate hazardous waste figure -- new entries should use the specific waste-type fields below instead.", "e.g. 20 MT"),
    "Non-Hazardous Waste Generated": ("Legacy aggregate non-hazardous waste figure -- new entries should use the specific waste-type fields below instead.", "e.g. 55 MT"),
}

WASTE_TYPE_DEFS = {
    "Plastic Waste": "Plastic packaging, containers, or process scrap generated on-site.",
    "Other Hazardous Waste": "Hazardous waste not covered by a more specific category (chemical residues, contaminated material, etc).",
    "Biomedical Waste": "Waste from on-site medical/first-aid facilities requiring biomedical disposal handling.",
    "Construction & Demolition Waste": "Debris and material from construction, renovation, or demolition work on-site.",
    "Battery Waste": "Spent or scrap batteries and battery components generated during manufacturing.",
    "E-Waste": "Discarded electronic equipment and components.",
}
DISPOSITION_DEFS = {
    "Recycled": "sent for recycling",
    "Sent to Landfill": "sent to landfill disposal",
    "Incinerated": "sent for incineration",
}

REFRIGERANT_LEAK_SUBSTANCES = ["R-22", "R-134a", "R-32", "Halon"]


def build_definitions() -> dict[str, tuple[str, str]]:
    defs = dict(DEFINITIONS)
    for waste_type, base in WASTE_TYPE_DEFS.items():
        for disposition, phrase in DISPOSITION_DEFS.items():
            name = f"{waste_type} — {disposition}"
            defs[name] = (f"{base} Quantity {phrase} this period.", "e.g. 4.2 MT")
    for substance in REFRIGERANT_LEAK_SUBSTANCES:
        name = f"Refrigerant Leakage — {substance}"
        defs[name] = (f"Quantity of {substance} refrigerant known to have leaked from Air Emissions-related equipment.", "e.g. 0.8 kg")
    return defs


def main() -> None:
    db = SessionLocal()
    try:
        tenant = db.query(Tenant).filter(Tenant.name == TENANT_NAME).first()
        if tenant is None:
            raise SystemExit(f"Tenant '{TENANT_NAME}' not found")

        definitions = build_definitions()
        data_points = (
            db.query(DataPoint).join(Category, Category.id == DataPoint.category_id).filter(Category.tenant_id == tenant.id).all()
        )

        updated = 0
        skipped = []
        for dp in data_points:
            if dp.name not in definitions:
                skipped.append(dp.name)
                continue
            tooltip, example = definitions[dp.name]
            rules = dict(dp.validation_rules or {})
            rules["tooltip"] = tooltip
            rules["example"] = example
            dp.validation_rules = rules
            updated += 1
        db.commit()
        print(f"updated {updated} data points")
        if skipped:
            print("no definition found for:", skipped)
    finally:
        db.close()


if __name__ == "__main__":
    main()
