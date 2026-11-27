"""Geometry and physical quantities for classified resource-table layouts."""

from decimal import Decimal
import re

from .normalization import MASS_FRACTION, MASS_FRACTION_UNIT_PATTERN, MASS_IN_TONNES, unit_factor
from .numeric_evidence import scalar_decimal
from .semantic_resource import GRADE_PHRASE, _header_unit, clean, located_column_headers


PARTICLE_SIZE = re.compile(
    r"(?P<operator>[-‐‑–−+]|<|>)\s*(?P<size>\d+(?:\.\d+)?)\s*[μµuų]m\b", re.I,
)
FRACTION_MATERIAL = "RESOURCE_PARTICLE_SIZE_FRACTION"
FRACTION_DENOMINATOR = "RESOURCE_PARTICLE_SIZE_FRACTION_MASS"
_FRACTION_MASS = re.compile(PARTICLE_SIZE.pattern + r"\s*\(?(?P<unit>Mt|kt|t)\)?", re.I)
_BULK_MASS = re.compile(r"(?:(?:bulk|whole)\s+ore|total(?:\s+(?:ore\s+)?(?:tonnage|tonnes))?)"
                        r"\s*\(?(Mt|kt|t)\)?", re.I)
_ESTIMATE_MASS = re.compile(r"MRE\s+tonnes?\s*\(\s*(Mt|kt|t)\s*\)", re.I)
_TREOSC = re.compile(r"TREO\s*\+\s*Sc(?:[2₂]O[3₃]|O\s*[2₂]\s*[3₃])", re.I)
_COMPOSITE_GRADE = re.compile(rf"(?P<species>TREOSc|{_TREOSC.pattern})\s*"
                              rf"\(\s*(?P<unit>{MASS_FRACTION_UNIT_PATTERN})\s*\)", re.I)
_SPLIT_TREO_GRADE = re.compile(rf"(?P<value>[\d,.]+)\s*(?P<unit>{MASS_FRACTION_UNIT_PATTERN})\s*"
                              r"(?:TREO(?:s)?|total rare earth oxides?)\b", re.I)
_MASS_TONNE_FACTORS = {"t": MASS_IN_TONNES["t"], "kt": MASS_IN_TONNES["kt"],
                       **dict.fromkeys(("mt", "m tonnes", "million tonnes"), MASS_IN_TONNES["Mt"])}


def header_for(cell, headers):
    pieces = located_column_headers(cell, headers)
    return clean(" ".join(dict.fromkeys(piece["text"] for piece in pieces))), pieces


def particle_size(text):
    if match := PARTICLE_SIZE.search(text):
        return {"operator": "<" if match["operator"] in "-‐‑–−<" else ">", "value": match["size"], "unit": "µm",
                "original": match[0]}
    return None


def _native_units(header, suffix, particle):
    if particle:
        if match := _FRACTION_MASS.fullmatch(header):
            return (("fraction_mass", match["unit"]),)
        # An explicit particle label may precede the TREO column name.
        header = PARTICLE_SIZE.sub("", header, count=1).strip()
    if suffix and (bulk := _BULK_MASS.fullmatch(header)):
        return (("bulk_ore_mt", bulk[1]),)
    if (mass := _ESTIMATE_MASS.fullmatch(header)) and mass[1] in {"Mt", "kt", "t"}:
        return (("ore_mt", mass[1]),)
    if composite := _COMPOSITE_GRADE.fullmatch(header):
        return (("grade_treosc", composite["unit"].lower()),)
    return tuple((quantity, unit) for quantity in ("ore_mt", "grade", "contained_treo_kt")
                 if (unit := _header_unit(header, quantity, native=True)))


def row_quantities(row_cells, headers):
    """Identify native columns without pairing constituent and whole-material masses."""
    values = {quantity: [] for quantity in ("ore_mt", "grade", "contained_treo_kt", "fraction_mass", "bulk_ore_mt",
                                             "grade_treosc")}
    headers_by_column = [(cell, *header_for(cell, headers)) for cell in row_cells]
    has_fraction_mass = any(_FRACTION_MASS.fullmatch(header) for _, header, _ in headers_by_column)
    for cell, header, pieces in headers_by_column:
        for quantity, unit in _native_units(header, has_fraction_mass, particle_size(header)):
            values[quantity].append((cell, unit, pieces))
    return values


def composite_grade_basis(pieces, cutoff):
    """Expand an abbreviation only with a composite declaration for the same estimate."""
    label = clean(" ".join(dict.fromkeys(piece["text"] for piece in pieces)))
    match = _COMPOSITE_GRADE.fullmatch(label)
    if match and (_TREOSC.fullmatch(match["species"]) or (cutoff or {}).get("basis") == "TREO+SC2O3"):
        return "TREO+SC2O3"
    return None


def has_resource_value_row(row_cells, headers):
    values = row_quantities(row_cells, headers)
    mass = values["ore_mt"] or values["fraction_mass"]
    return bool(mass and values["grade"] and all(any(scalar_decimal(cell["text"], unit) is not None
                                                     for cell, unit, _ in entries) for entries in (mass, values["grade"])))


def _agrees(printed, printed_unit, witness, witness_unit):
    first, second = scalar_decimal(printed, printed_unit), scalar_decimal(witness, witness_unit)
    units = printed_unit.casefold(), witness_unit.casefold()
    if all(unit in MASS_FRACTION for unit in units):
        target, factors = "ppm", MASS_FRACTION
    else:
        target, factors = "t", _MASS_TONNE_FACTORS
    if first is None or second is None or any(unit not in factors for unit in units):
        return False
    a, b = (unit_factor(unit, target, factors) for unit in units)
    # Source summaries can round either one of the two physical presentations.
    half_first = Decimal(5).scaleb(first.as_tuple().exponent - 1) * a
    half_second = Decimal(5).scaleb(second.as_tuple().exponent - 1) * b
    return abs(first * a - second * b) <= max(half_first, half_second)


def fraction_grade_summary(quote, mass, grade, size):
    """Require one named grain-size interpretation and the reported mass/grade pair."""
    phrase = list(GRADE_PHRASE.finditer(quote))
    marks = {tuple(particle_size(m[0])[key] for key in ("value", "operator")) for m in PARTICLE_SIZE.finditer(quote)}
    if len(phrase) != 1 or marks != {(size["value"], size["operator"])} or len(mass) != 1 or len(grade) != 1:
        return False
    match = phrase[0]
    return all(_agrees(entries[0][0]["text"], entries[0][1], match[key], match[f"{key}_unit"])
               for entries, key in ((mass, "mass"), (grade, "grade")))


def co_commodity_summary(quote, mass, grade):
    """Bind a supplemental TREO grade to one physical mass plus a second commodity."""
    split_grades = list(_SPLIT_TREO_GRADE.finditer(quote))
    if len(mass) != 1 or len(grade) != 1 or len(split_grades) != 1:
        return False
    first = re.findall(r"(?<![\w.,])([\d,.]+)\s*(Mt|kt|t)\b", quote, re.I)
    grade_value, grade_unit = split_grades[0].groups()
    return (len([pair for pair in first if _agrees(mass[0][0]["text"], mass[0][1], *pair)]) == 1
            and _agrees(grade[0][0]["text"], grade[0][1], grade_value, grade_unit))
