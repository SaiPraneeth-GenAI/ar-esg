"""Unit recognition and conversion for bulk upload validation. When a
user's spreadsheet unit doesn't exactly match what a data point expects,
this tries to recognize it as a spelling variant or a convertible unit in
the same family before giving up. Rule: never silently accept a value in
the wrong unit, but never reject a genuinely correct value just because
someone wrote "Liters" instead of "litres" or "1.5 KL" instead of "1500
litres" either -- convert when the conversion is unambiguous, flag with a
concrete suggestion when it isn't.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class UnitFamily:
    name: str
    # canonical unit key (lowercase) -> multiplier to convert 1 of that
    # unit into the family's base unit (e.g. volume base = litres, so
    # "kl": 1000 means 1 kL = 1000 litres).
    units: dict[str, float]


FAMILIES: list[UnitFamily] = [
    UnitFamily(
        "volume",
        {
            "litres": 1, "litre": 1, "liters": 1, "liter": 1, "l": 1,
            "millilitres": 0.001, "millilitre": 0.001, "ml": 0.001,
            "kilolitres": 1000, "kilolitre": 1000, "kl": 1000,
            "m3": 1000, "cubic metres": 1000, "cubic meters": 1000,
        },
    ),
    UnitFamily(
        "mass",
        {
            "kg": 1, "kgs": 1, "kilogram": 1, "kilograms": 1,
            "g": 0.001, "gram": 0.001, "grams": 0.001,
            "mt": 1000, "t": 1000, "tonne": 1000, "tonnes": 1000, "ton": 1000, "tons": 1000, "metric tons": 1000, "metric tonnes": 1000,
        },
    ),
    UnitFamily(
        "energy",
        {
            "kwh": 1, "wh": 0.001,
            "mwh": 1000, "gwh": 1_000_000,
        },
    ),
    UnitFamily(
        "currency_cr",
        {
            "inr cr": 1, "cr": 1, "crore": 1, "crores": 1,
            "inr lakh": 0.01, "lakh": 0.01, "lakhs": 0.01,
            "inr": 1e-7, "rs": 1e-7, "rupees": 1e-7,
        },
    ),
    UnitFamily("count", {"nos": 1, "no": 1, "number": 1, "numbers": 1, "count": 1, "units": 1}),
    UnitFamily("percentage", {"%": 1, "percent": 1, "pct": 1}),
]


def _norm(unit: str) -> str:
    return unit.strip().lower()


def _find_family(unit: str) -> tuple[UnitFamily, float] | None:
    key = _norm(unit)
    for fam in FAMILIES:
        if key in fam.units:
            return fam, fam.units[key]
    return None


def units_equivalent(a: str, b: str) -> bool:
    """True if a and b are the same unit once case/spelling variants are
    normalized -- no numeric conversion involved (e.g. 'Liters' vs
    'litres', or a unit outside every known family compared literally)."""
    if _norm(a) == _norm(b):
        return True
    fam_a = _find_family(a)
    fam_b = _find_family(b)
    if fam_a is None or fam_b is None:
        return False
    return fam_a[0].name == fam_b[0].name and fam_a[1] == fam_b[1]


def convert_unit(value: float, from_unit: str, to_unit: str) -> float | None:
    """Converts value from from_unit into to_unit. Returns None when the
    two units aren't recognized as the same family -- never guesses
    across families (a mass unit is never treated as a volume unit)."""
    if units_equivalent(from_unit, to_unit):
        return value

    from_match = _find_family(from_unit)
    to_match = _find_family(to_unit)
    if from_match is None or to_match is None:
        return None
    from_fam, from_mult = from_match
    to_fam, to_mult = to_match
    if from_fam.name != to_fam.name:
        return None
    return (value * from_mult) / to_mult
