"""Complete printed number tokens and their Unicode code-point spans."""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import re


_SPACE = r"[ \t\u00a0\u202f]"
_SIGN = r"[+\-−–]"
_DECIMAL = r"(?:(?:[0-9]{1,3}(?:[,\u00a0\u202f][0-9]{3})+|[0-9]+)(?:\.[0-9]+)?|\.[0-9]+)"
_POWER = rf"{_SPACE}*[×x]{_SPACE}*10{_SPACE}*(?:\^{_SPACE}*({_SIGN}?[0-9]+)|([⁺⁻]?[⁰¹²³⁴⁵⁶⁷⁸⁹]+))"
_POWER_LITERAL = re.compile(_POWER)
_SUPERSCRIPT = str.maketrans("⁺⁻⁰¹²³⁴⁵⁶⁷⁸⁹", "+-0123456789")
_ATOM = rf"{_SIGN}?{_DECIMAL}(?:[Ee]{_SIGN}?[0-9]+|{_POWER})?"
_PERCENT = rf"{_SPACE}*[%％]"
_JOIN = rf"(?:{_SPACE}*[\-−–—]{_SPACE}*|{_SPACE}+to{_SPACE}+)"
_EXPRESSION = rf"(?P<expression>(?P<range>{_ATOM}(?:{_PERCENT})?{_JOIN}{_ATOM})" \
              rf"|(?P<bound>(?:<=|>=|[<>≤≥≈~]){_SPACE}*{_ATOM})|{_ATOM})"
_READING = re.compile(rf"(?<![\w.+−–-]){_EXPRESSION}(?P<percent>{_PERCENT})?", re.I)
_ISO_DATE = re.compile(r"\b[12][0-9]{3}[-/][0-9]{1,2}[-/][0-9]{1,2}\b")
_IDENTIFIER = re.compile(r"\b(?:table|page|figure|fig\.|p\.|row|sample|test|year|fy)[ \t#.:\-]*$", re.I)
_UNIT_ALIASES = {
    "%": ("%", "％", "percent", "per cent", "wt%", "wt.%", "wt. %", "wt %", "w/w%"),
    "ppm": ("ppm", "parts per million"),
    "ppb": ("ppb", "parts per billion"),
    "Bt": ("Bt", "billion tonnes"),
    "Mt": ("Mt", "M tonnes", "million tonnes", "million tonne"),
    "kt": ("kt", "kilotonnes", "‘000 tonnes", "'000 tonnes"),
    "kt TREO": ("kt TREO",),
    "t": ("t", "tonnes", "tonne"),
    "t TREO": ("t TREO",),
    "kg": ("kg",),
    "g": ("g",),
    "g/t": ("g/t",),
    "kg/t": ("kg/t",),
    "mg/kg": ("mg/kg",),
    "g/L": ("g/L", "g/l"),
    "mg/L": ("mg/L", "mg/l"),
    "mm": ("mm",),
    "cm": ("cm",),
    "m": ("m",),
    "km": ("km",),
}
_CANONICAL_UNIT = {alias.casefold(): unit for unit, aliases in _UNIT_ALIASES.items() for alias in aliases}
_UNIT_PATTERN = "|".join(re.escape(alias) for alias in sorted(_CANONICAL_UNIT, key=len, reverse=True))
_UNIT = re.compile(rf"{_SPACE}*(?P<unit>{_UNIT_PATTERN})(?![\w/])", re.I)
_HEADER_UNIT = re.compile(rf"(?<![\w/])(?:{_UNIT_PATTERN})(?![\w/])", re.I)
_TRANSLATE = str.maketrans({"−": "-", "–": "-", "—": "-", "％": "%", "≤": "<=", "≥": ">="})


def _unit(value):
    if not value:
        return None
    literal = " ".join(value.split())
    if literal.casefold() in {"bt", "mt", "kt"}:
        return literal
    return _CANONICAL_UNIT.get(literal.casefold(), literal)


def _expression(value):
    value = _POWER_LITERAL.sub(lambda match: "e" + (match[1] or match[2].translate(_SUPERSCRIPT)), value)
    value = re.sub(rf"{_SPACE}+to{_SPACE}+", "-", value, flags=re.I)
    value = re.sub(r"(?<=[0-9])[\u00a0\u202f](?=[0-9]{3}(?:[^0-9]|$))", ",", value)
    return re.sub(_SPACE, "", value.translate(_TRANSLATE).lower())


@dataclass(frozen=True, slots=True)
class _Reading:
    start: int
    numeric_end: int
    end: int
    expression: str
    kind: str
    unit: str | None


def _readings(text):
    if not text:
        return
    dates = tuple(match.span() for match in _ISO_DATE.finditer(text))
    for match in _READING.finditer(text):
        start, end = match.span()
        if any(left <= start < right for left, right in dates):
            continue
        prefix = text[max(0, start - 18):start]
        if not match["bound"] and re.search(r"[<>≤≥≈~][= \t\u00a0\u202f]*$", prefix):
            continue
        if start >= 2 and text[start - 1] == "," and text[start - 2].isdigit():
            continue
        if re.match(r"[,.][0-9]", text[end:]):
            continue
        inline = "%" if match["percent"] else None
        if inline is None and (unit := _UNIT.match(text, end)):
            inline = _unit(unit["unit"])
            end = unit.end()
        elif inline is None and end < len(text) and (text[end].isalnum() or text[end] == "_"):
            # A chemical formula, sample ID, or malformed exponent stays intact.
            continue
        if inline is None and _IDENTIFIER.search(prefix):
            continue
        kind = "RANGE" if match["range"] else "BOUND" if match["bound"] else "NUMBER"
        yield _Reading(start, match.end("expression"), end, _expression(match["expression"]), kind, inline)


def quantity_literals(text):
    """Yield located lexical candidates that have an explicitly printed adjoining unit."""
    return (reading for reading in _readings(text) if reading.unit is not None)


NATIVE_GEOMETRIC_UNIT_HEADER = "NATIVE_GEOMETRIC_UNIT_HEADER"


def header_within_value_column(header_box, value_box):
    """Prove a narrower native header belongs to one wider data-column span."""
    if not (header_box and value_box):
        return False
    left, _, right, _ = header_box
    value_left, _, value_right, _ = value_box
    midpoint = (value_left + value_right) / 2
    return (value_left - .01 <= left < midpoint < right <= value_right + .01
            and (left > value_left + .01 or right < value_right - .01))


def unit_header_matches_value_column(header, value):
    """Match the native index, or recheck a located split-grid relationship."""
    return type(header.column) is int and type(value.column) is int and (
        header.column == value.column or header.locator == NATIVE_GEOMETRIC_UNIT_HEADER
        and header_within_value_column(header.bbox, value.bbox))


def header_unit_issue(text, unit):
    """Check a known header at the already bound column, keeping unclear labels unresolved."""
    if not text:
        return None
    # Explicit parenthetical units take precedence over descriptions such as
    # "Tonnes (Mt)". In a bare label "Tonnes Mt", the scale likewise governs.
    explicit = {_unit(label) for label in re.findall(r"\(([^()]*)\)", text)
                if " ".join(label.casefold().split()) in _CANONICAL_UNIT}
    labels = explicit or {_unit(match[0]) for match in _HEADER_UNIT.finditer(text)}
    if labels & {"Bt", "Mt", "kt", "t TREO", "kt TREO"}:
        labels.discard("t")
    if labels and _unit(unit) not in labels:
        return "NUMERIC_EVIDENCE_BINDING_MISMATCH"
    if len(labels) > 1:
        return "NUMERIC_EVIDENCE_LOCATION_INSUFFICIENT"
    return None


def _reported(value, unit):
    value = value.strip() if value else ""
    reading = next(_readings(value), None)
    if reading is None or reading.start != 0 or reading.end != len(value):
        return None
    if reading.unit is not None and unit is not None and reading.unit != _unit(unit):
        return None
    return reading


def numeric_token_spans(text, value, unit=None):
    """Find complete printed lexemes, preserving an explicit unit in the requested literal."""
    expected = _reported(value, unit)
    if expected is None:
        return ()
    bound_unit = expected.unit or _unit(unit)
    includes_unit = expected.end != expected.numeric_end
    return tuple((actual.start, actual.end if includes_unit else actual.numeric_end)
                 for actual in _readings(text)
                 if actual.expression == expected.expression and actual.kind == expected.kind
                 and (actual.unit is None or bound_unit is None or actual.unit == bound_unit)
                 and (not includes_unit or actual.unit == expected.unit))


def numeric_witness_issue(text, value, unit, *, span=None, cell=False, token_state=None):
    """Separate conflicting text/position from an otherwise plausible unlocated reading."""
    if not text or not value:
        return "NUMERIC_EVIDENCE_LOCATION_INSUFFICIENT"
    expected = _reported(value, unit)
    declared = {"NUMBER": "NUMBER", "SCALAR": "NUMBER", "RANGE": "RANGE", "BOUND": "BOUND"}
    if expected is None or (token_state is not None and declared.get(token_state) != expected.kind):
        return "NUMERIC_EVIDENCE_BINDING_MISMATCH"
    matches = numeric_token_spans(text, value, unit)
    if not matches or (span is not None and span not in matches):
        return "NUMERIC_EVIDENCE_BINDING_MISMATCH"
    readings = tuple(_readings(text))
    if span is None and len(readings) != 1:
        return "NUMERIC_EVIDENCE_LOCATION_INSUFFICIENT"
    start = (span or matches[0])[0]
    located = next(reading for reading in readings if reading.start == start)
    if located.unit is None and (not cell or text[:located.start].strip() or text[located.end:].strip()):
        return "NUMERIC_EVIDENCE_LOCATION_INSUFFICIENT"
    return None


def scalar_decimal(value, unit):
    """Read one printed scalar with exact precision; bounds and ranges stay unconverted."""
    reading = _reported(value, unit)
    if reading is None or reading.kind != "NUMBER":
        return None
    try:
        return Decimal(reading.expression.replace(",", ""))
    except InvalidOperation:
        return None
