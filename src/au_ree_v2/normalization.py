"""Numerical rules shared by evidence validation and observation normalization."""

import json
import re
from calendar import monthrange
from datetime import date
from decimal import Decimal, InvalidOperation
from unicodedata import normalize


NUMBER = re.compile(r"(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?")
MASS_IN_TONNES = {"kg": "0.001", "t": "1", "kt": "1000", "Mt": "1000000", "Bt": "1000000000",
                 "t TREO": "1", "kt TREO": "1000"}
MASS_FRACTION = {"ppm": "0.000001", "%": "0.01", "g/t": "0.000001", "mg/kg": "0.000001"}
MASS_FRACTION_UNIT_PATTERN = r"ppm|%|g/t|mg/kg"
RESOURCE_CUTOFF_ANALYTE = r"(?:TREO(?:\s*[+]\s*Sc2O3|\s*[-−]\s*CeO2)?|Nb2O5|Ga2O3)(?!\w|\s*[+−-]\s*[A-Za-z])"
_MASS_CONTEXTS = (
    frozenset({"WHOLE_ORE", "BULK_ORE", "RESOURCE_ORE", "RESOURCE_ORE_GRADE", "RESOURCE_ORE_GRADE_OXIDE_PPM",
               "RESOURCE_BULK_ORE", "BULK_ORE_MASS", "RESOURCE_BULK_ORE_MASS"}),
    frozenset({"RESOURCE_PARTICLE_SIZE_FRACTION", "RESOURCE_PARTICLE_SIZE_FRACTION_MASS"}),
    frozenset({"CONCENTRATE", "CONCENTRATE_MASS"}),
    frozenset({"PRODUCT", "PRODUCT_MASS"}),
    frozenset({"TREO", "TREO_MASS"}),
)
MAGNET_ATOMIC_WEIGHTS = {"Nd": "144.242", "Pr": "140.908", "Dy": "162.500", "Tb": "158.925"}
MAGNET_SPECIES = {"Nd": {"Nd", "Nd2O3"}, "Pr": {"Pr", "Pr2O3", "Pr6O11"},
                  "Dy": {"Dy", "Dy2O3"}, "Tb": {"Tb", "Tb2O3", "Tb4O7"}}
OXYGEN_ATOMIC_WEIGHT = Decimal("15.999")


def decimal_token(token, unit, *, signed=False):
    """Parse one source token, preserving range, bound, and absence dispositions upstream."""
    if unit == "%" and token.endswith("%"):
        token = token[:-1].strip()
    if not NUMBER.fullmatch(token[1:] if signed and token.startswith(("+", "-")) else token):
        return None
    return Decimal(token.replace(",", ""))


def unit_factor(original_unit, target_unit, factors):
    """Compute a factor within one explicitly selected dimension."""
    return Decimal(factors[original_unit]) / Decimal(factors[target_unit])


def same_mass_material(material, denominator):
    """Check that a concentration describes mass of the same declared material."""
    return any(material in labels and denominator in labels for labels in _MASS_CONTEXTS)


def date_precision(value):
    """Qualify a reported calendar date without changing its literal precision."""
    if not isinstance(value, str):
        return None
    try:
        if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
            date.fromisoformat(value)
            return "DAY"
        if re.fullmatch(r"[0-9]{4}-[0-9]{2}", value):
            year, month = map(int, value.split("-"))
            if year:
                monthrange(year, month)
                return "MONTH"
        if re.fullmatch(r"[0-9]{4}", value) and int(value):
            return "YEAR"
    except (ValueError, OverflowError):
        return None
    return None


def overlapping_month_and_day(left, right):
    """Whether one reported day and one reported month cannot be ordered."""
    return ({date_precision(left), date_precision(right)} == {"MONTH", "DAY"}
            and left[:7] == right[:7])


def oxide_factor(element, original_species, target_species, atomic_weight):
    """Preserve the number of atoms of one named element during a species change."""
    weight = Decimal(str(atomic_weight))
    if not weight.is_finite() or weight <= 0 or not re.fullmatch(r"[A-Z][a-z]?", element):
        raise ValueError("Invalid elemental atomic weight or symbol")

    def oxide_counts(species):
        match = re.fullmatch(re.escape(element) + r"([1-9]\d*)?O([1-9]\d*)", species)
        if not match:
            raise ValueError("Unsupported chemical species")
        return int(match[1] or 1), int(match[2])

    if original_species == element or target_species == element:
        atoms, oxygen = oxide_counts(target_species if original_species == element else original_species)
        factor = 1 + OXYGEN_ATOMIC_WEIGHT * oxygen / (weight * atoms)
        return factor if original_species == element else 1 / factor

    original_atoms, original_oxygen = oxide_counts(original_species)
    target_atoms, target_oxygen = oxide_counts(target_species)
    return ((target_atoms * weight + target_oxygen * OXYGEN_ATOMIC_WEIGHT) * original_atoms
            / ((original_atoms * weight + original_oxygen * OXYGEN_ATOMIC_WEIGHT) * target_atoms))


_CUTOFF_NUMBER = r"(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)(?:\.[0-9]+)?|\.[0-9]+"
_CUTOFF_BASIS = r"[A-Z][A-Z0-9_]*(?:[ -][A-Z0-9_]+|\s*\+\s*[A-Z][A-Z0-9_]*)*?"
_CUTOFF_TEXT = re.compile(
    rf"(?:(?:cut[- ]?off(?:\s+grade)?)(?:\s*[:=]\s*|\s+))?"
    rf"(?P<op>>=|<=|[≥≤><=])?\s*(?P<value>{_CUTOFF_NUMBER})\s*"
    rf"(?P<unit>{MASS_FRACTION_UNIT_PATTERN}|percent|parts per million)\s*(?P<basis>{_CUTOFF_BASIS})"
    rf"(?:\s+cut[- ]?off(?:\s+grade)?)?", re.I,
)
_CUTOFF_OPERATORS = {">=": ">=", "≥": ">=", "<=": "<=", "≤": "<=", ">": ">", "<": "<", "=": "=",
              "DECLARED_CUTOFF": "DECLARED_CUTOFF", "at least": ">=", "above": ">",
              "at most": "<=", "below": "<"}
_CUTOFF_UNITS = {**{label: label for label in MASS_FRACTION}, "parts per million": "ppm", "percent": "%"}


def _cutoff_label(value):
    return " ".join(str(value).split()) if value is not None else ""


def _cutoff_tag(value):
    literal = normalize("NFKC", _cutoff_label(value))
    return re.sub(r"[ -]+", "_", re.sub(r"\s*\+\s*", "+", literal)).upper() or None


def normalize_cutoff(value):
    """Keep the original threshold and normalize only known concentration units.

    An unqualified published cutoff remains a declaration. It does not prove
    whether the boundary is inclusive, so it cannot match an explicit operator.
    """
    original = value
    if isinstance(value, str):
        value = value.strip()
        if value.startswith("{"):
            try:
                value = json.loads(value)
            except ValueError:
                return None
        else:
            match = _CUTOFF_TEXT.fullmatch(normalize("NFKC", value))
            if not match:
                return None
            value = {"value": match["value"], "unit": match["unit"], "basis": match["basis"],
                     "operator": match["op"]}
    if not isinstance(value, dict):
        return None
    unit = _CUTOFF_UNITS.get(_cutoff_label(value.get("unit")).casefold())
    basis = _cutoff_tag(value.get("basis") or value.get("chemical_basis"))
    if basis and basis in {"TOTAL_RARE_EARTH_OXIDES", "TOTAL_RARE_EARTH_OXIDE"}:
        basis = "TREO"
    operators = {_CUTOFF_OPERATORS.get(_cutoff_label(value[field])) for field in ("operator", "comparison", "threshold_operator")
                 if value.get(field)} or {"DECLARED_CUTOFF"}
    number = _cutoff_label(value.get("value"))
    if not (unit and basis and len(operators) == 1 and None not in operators and len(number) <= 30
            and re.fullmatch(_CUTOFF_NUMBER, number)):
        return None
    try:
        numeric = Decimal(number.replace(",", ""))
        if numeric > (100 if unit == "%" else 1_000_000):
            return None
        # Use exponent scaling rather than appending zeroes under a mutable
        # Decimal context. No rounding is needed for the supported tokens.
        digits = numeric.as_tuple()
        ppm = Decimal((digits.sign, digits.digits, digits.exponent + (4 if unit == "%" else 0)))
    except (InvalidOperation, TypeError, ValueError):
        return None
    ppm_text = format(ppm, "f")
    if "." in ppm_text:
        ppm_text = ppm_text.rstrip("0").rstrip(".")
    conversion = {"%": "percent × 10000 = ppm", "ppm": "ppm unchanged",
                  "g/t": "1 g/t = 1 ppm in a mass fraction", "mg/kg": "1 mg/kg = 1 ppm in a mass fraction"}
    return {"original": original, "value_ppm": ppm_text, "basis": basis, "operator": next(iter(operators)),
            "conversion": conversion[unit]}


def cutoff_signature(cutoff):
    return tuple(cutoff[field] for field in ("value_ppm", "basis", "operator")) if cutoff else None
