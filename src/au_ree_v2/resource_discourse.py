"""Located text clauses and explicit changes of resource-estimate subject."""

import re


_RESOURCE = r"(?:(?:global|total)\s+)?(?:mineral\s+)?resources?(?:\s+estimate)?"
_ESTIMATE = rf"(?:{_RESOURCE}|estimate|MRE)"
_CODE = r"(?:JORC\b(?:\s+Code(?:\d+)?)?|Joint Ore Reserves Committee)"
_CLAUSE_BREAK = re.compile(
    r"(?<=[.;!?])\s+|\s+(?:but|whereas|while|and)\s+(?=(?:the|this|that|it|for|another|different)\b)", re.I,
)
_TABLE = re.compile(r"\bTable\s+(\d+(?:[-.]\d+)*)(?!\w|[.-]\d)", re.I)
_OLD = re.compile(rf"\b(?:earlier|historical|old|previous|prior|former)\s+(?:{_CODE}\s+)?(?:{_ESTIMATE}|assessment|20\d{{2}})\b", re.I)
_OTHER = re.compile(rf"\b(?:another|other|different|separate|alternative|second)\s+{_ESTIMATE}\b", re.I)
_NEW = re.compile(rf"\bnew\s+{_ESTIMATE}\b", re.I)
_INDEFINITE = re.compile(rf"\ban?\s+{_ESTIMATE}\b", re.I)
_LATEST = re.compile(rf"\b(?:current|updated|latest)\s+{_ESTIMATE}\b", re.I)
_ESTIMATE_YEAR = re.compile(rf"\b(20\d{{2}})\s+(?:{_CODE}\s+)?{_ESTIMATE}\b", re.I)
_REPORTING_CODE_BEFORE_YEAR = re.compile(rf"\b{_CODE}\s*$", re.I)
_PROJECT_TOPIC = re.compile(
    r"\b(?:(?i:another|different|separate|alternative|second|new|next|earlier|former|prior)"
    r"|(?!(?i:the|this|that|our|their|its|an?)\b)[A-Z][\w’'-]*)\s+(?i:project|deposit)\b"
)


def clause_spans(text):
    """Yield nonempty half-open source offsets without rewriting the quote."""
    start = 0
    for boundary in _CLAUSE_BREAK.finditer(text):
        if start < boundary.start():
            yield start, boundary.start()
        start = boundary.end()
    if start < len(text):
        yield start, len(text)


def table_numbers(text):
    return {match[1] for match in _TABLE.finditer(text)}


def older_estimate(text):
    return bool(_OLD.search(text))


def other_estimate(text):
    return bool(_OTHER.search(text))


def estimate_years(text):
    return {match[1] for match in _ESTIMATE_YEAR.finditer(text)
            if not _REPORTING_CODE_BEFORE_YEAR.search(text[:match.start()])}


def changes_estimate_subject(text, previous_subject=None):
    """Recognize a new or ambiguous antecedent that cannot inherit a subject."""
    return bool(table_numbers(text) or older_estimate(text) or other_estimate(text) or _NEW.search(text) or estimate_years(text)
                or _INDEFINITE.search(text) or _PROJECT_TOPIC.search(text)
                or (previous_subject and older_estimate(previous_subject) and _LATEST.search(text)))
