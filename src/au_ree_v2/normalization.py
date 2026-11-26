"""Numerical rules shared by evidence validation and observation normalization."""

import re
from decimal import Decimal


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
