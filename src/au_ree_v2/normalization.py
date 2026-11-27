"""Numerical rules shared by evidence validation and observation normalization."""

import json
import re
from decimal import Decimal, InvalidOperation


NUMBER = re.compile(r"(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?")
MASS_IN_TONNES = {"kg": "0.001", "t": "1", "kt": "1000", "Mt": "1000000", "Bt": "1000000000",
                 "t TREO": "1", "kt TREO": "1000"}
MASS_FRACTION = {"ppm": "0.000001", "%": "0.01"}
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
_CUTOFF_BASIS = r"[A-Z][A-Z0-9_]*(?:[ -][A-Z0-9_]+)*?"
_CUTOFF_TEXT = re.compile(
    rf"(?:(?:cut[- ]?off(?:\s+grade)?)(?:\s*[:=]\s*|\s+))?"
    rf"(?P<op>>=|<=|[≥≤><=])?\s*(?P<value>{_CUTOFF_NUMBER})\s*"
    rf"(?P<unit>ppm|%|percent|parts per million)\s+(?P<basis>{_CUTOFF_BASIS})"
    rf"(?:\s+cut[- ]?off(?:\s+grade)?)?", re.I,
)
_CUTOFF_OPERATORS = {">=": ">=", "≥": ">=", "<=": "<=", "≤": "<=", ">": ">", "<": "<", "=": "=",
              "DECLARED_CUTOFF": "DECLARED_CUTOFF", "at least": ">=", "above": ">",
              "at most": "<=", "below": "<"}
_CUTOFF_UNITS = {"ppm": "ppm", "parts per million": "ppm", "%": "%", "percent": "%"}


def _cutoff_label(value):
    return " ".join(str(value).split()) if value is not None else ""


def _cutoff_tag(value):
    return re.sub(r"[ -]+", "_", _cutoff_label(value)).upper() or None


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
            match = _CUTOFF_TEXT.fullmatch(value)
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
    return {"original": original, "value_ppm": ppm_text, "basis": basis, "operator": next(iter(operators)),
            "conversion": "percent × 10000 = ppm" if unit == "%" else "ppm unchanged"}


def cutoff_signature(cutoff):
    return tuple(cutoff[field] for field in ("value_ppm", "basis", "operator")) if cutoff else None
