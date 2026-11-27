"""Classify located reporting-standard assertions about one resource estimate."""

import re


VERSION = "resource-jorc-estimate-scope-v1"
_CODE = r"(?:JORC\b(?:\s+Code(?:\d+)?)?|Joint Ore Reserves Committee)"
_COMPLIANCE = r"(?:compliant|compliance|comply|complies|in\s+accordance|conforms?\s+to)"
_METHOD = r"(?:reported|estimated|classified|prepared|compiled)"
_NEGATION = r"(?:not\s+|never\s+|no\s+|non[-\s‐‑–—]+|without\s+)"
_NEGATIVE = re.compile(
    rf"\b(?:{_NEGATION}(?:an?\s+)?{_CODE}"
    rf"|{_CODE}\s*(?:[-‐‑–—(]\s*)?{_NEGATION}{_COMPLIANCE}"
    rf"|{_NEGATION}(?:(?:been\s+)?{_METHOD}\s+)?{_COMPLIANCE}[^.;!?]{{0,120}}?{_CODE})",
    re.I,
)
_POSITIVE = re.compile(
    rf"\b(?:{_CODE}(?:\s+20\d\d)?\s*(?:[-‐‑–—]\s*)?"
    r"(?:compliant|(?:(?:global|total)\s+)?(?:mineral\s+)?resources?(?:\s+estimate)?)\b"
    rf"|{_METHOD}\s+in\s+accordance\s+[^.;!?]{{0,120}}?{_CODE}"
    rf"|(?:comply|complies|conforms?)\s+(?:with|to)\s+[^.;!?]{{0,100}}?{_CODE})",
    re.I,
)
_ANAPHORIC_NEGATIVE = re.compile(
    rf"\b{_NEGATION}(?:(?:been\s+)?{_METHOD}\s+)?{_COMPLIANCE}\b", re.I,
)
_NEGATABLE = re.compile(r"\b(?:not|never)\s+(?:(?:yet|been|actually|currently)\s+){0,3}$", re.I)
_NO_CHANGE = re.compile(rf"no\s+{_CODE}(?:\s+20\d\d)?\s+(?:mineral\s+)?resources?(?:\s+estimate)?\s+"
                        r"(?:changes?|revisions?)\b", re.I)
_CLAUSE_BREAK = re.compile(r"(?<=[.;!?])\s+|\s+(?=(?:but|whereas)\s+(?:the|this|that)\s+)", re.I)
_TABLE = re.compile(r"\bTable\s+(\d+(?:[-.]\d+)*)(?!\w|[.-]\d)", re.I)
_OLD = re.compile(r"\b(?:earlier|historical|old|previous|prior|former)\s+(?:estimate|assessment|20\d{2}|MRE|resource)\b", re.I)
_CURRENT = re.compile(r"\b(?:current|updated|latest|this)\s+(?:(?:mineral\s+)?resource\s+)?(?:estimate|MRE|resource)\b", re.I)
_SCOPE_END = re.compile(r"\s+(?:(?:rare earth )?deposit|project)\s*$", re.I)
_SECTION = re.compile(r"^(20\d\d)\s+(.+?)\s+(?:Mineral\s+)?Resource Estimate$", re.I)
ROLE_TO_SCOPE = {
    "jorc_target": "TARGET",
    "jorc_other": "OTHER_ESTIMATE",
    "jorc_unscoped": "UNRESOLVED",
    "jorc_ambiguous_target": "TARGET_SCOPE_AMBIGUOUS",
}
SCOPE_TO_ROLE = {scope: role for role, scope in ROLE_TO_SCOPE.items()}
REASONS = {
    "AFFIRMED": None,
    "DENIED": "RESOURCE_JORC_NEGATED",
    "CONFLICT": "RESOURCE_JORC_CONFLICT",
    "UNRESOLVED_SCOPE": "RESOURCE_JORC_SCOPE_UNRESOLVED",
    "UNESTABLISHED": "RESOURCE_REPORTING_STANDARD_UNRESOLVED",
}


def claims(quote):
    """Find compliance predicates locally, including a coordinated negative clause."""
    start = 0
    previous_code = False
    for boundary in [*(_CLAUSE_BREAK.finditer(quote)), None]:
        end = boundary.start() if boundary else len(quote)
        clause = quote[start:end]
        negatives = [m.span() for m in _NEGATIVE.finditer(clause) if not _NO_CHANGE.match(clause, m.start())]
        positives = []
        for match in _POSITIVE.finditer(clause):
            if _NEGATABLE.search(clause[:match.start()]):
                negatives.append((match.start(), match.end()))
            elif not any(left < match.end() and match.start() < right for left, right in negatives):
                positives.append((match.start(), match.end()))
        if previous_code and not negatives and not positives and (_OLD.search(clause) or _CURRENT.search(clause)):
            negatives.extend(m.span() for m in _ANAPHORIC_NEGATIVE.finditer(clause))
        for polarity, spans in (("DENIED", negatives), ("AFFIRMED", positives)):
            if spans:
                # Keep the full clause so the estimate reference is recheckable.
                yield {"polarity": polarity, "start": start, "end": end, "predicate_start": start + spans[0][0]}
        previous_code = bool(negatives or positives) and bool(re.search(_CODE, clause, re.I))
        if boundary:
            start = boundary.end()


def scope_stem(text):
    return _SCOPE_END.sub("", text or "").strip().casefold()


def table_numbers(text):
    return {match[1] for match in _TABLE.finditer(text)}


def section_matches(text, scope, effective):
    match = _SECTION.fullmatch(text)
    return bool(match and effective and match[1] == effective[:4] and scope_stem(match[2]) == scope_stem(scope))


def estimate_heading(text):
    return bool(_SECTION.fullmatch(text))


def reporting_status(scoped_polarities):
    pairs = set(scoped_polarities)
    positive = ("TARGET", "AFFIRMED") in pairs
    negative = ("TARGET", "DENIED") in pairs
    if positive and negative:
        return "CONFLICT"
    if any(scope == "TARGET_SCOPE_AMBIGUOUS" for scope, polarity in pairs):
        return "UNRESOLVED_SCOPE"
    if positive or negative:
        return "AFFIRMED" if positive else "DENIED"
    return "UNRESOLVED_SCOPE" if pairs else "UNESTABLISHED"


def evaluate(witnesses, subject, *, projects_in, dates_in):
    """Keep unrelated assertions as evidence without lending their standard to this row."""
    evidence = []
    table = subject["reported_table_label"]
    for witness in witnesses:
        quote = witness["quote"]
        propositions = list(claims(quote))
        refs = table_numbers(quote)
        for assertion in propositions:
            clause = quote[assertion["start"]:assertion["end"]]
            subject_side = quote[assertion["start"]:assertion["predicate_start"]]
            named = table_numbers(clause)
            old = _OLD.search(subject_side)
            origin = witness["origin"]
            proof = None
            projects, dates = projects_in(subject_side), dates_in(clause)
            foreign = bool(projects - {subject["project_id"]} or dates - {subject["effective_date"]})
            if named and named != {table}:
                applicability = "TARGET_SCOPE_AMBIGUOUS" if table in named else "OTHER_ESTIMATE"
            elif foreign:
                applicability = "TARGET_SCOPE_AMBIGUOUS" if named == {table} else "OTHER_ESTIMATE"
            elif old and not (origin in {"SCOPE_CAPTION", "NATIVE_SECTION"} and assertion["start"] == 0):
                applicability = "TARGET_SCOPE_AMBIGUOUS" if named == {table} else "OTHER_ESTIMATE"
            elif origin in {"SCOPE_CAPTION", "NATIVE_SECTION"}:
                applicability, proof = "TARGET", origin
            elif named == {table} or (refs == {table} and len(propositions) == 1 and not old):
                applicability, proof = "TARGET", "TABLE_REFERENCE"
            elif origin == "ADJACENT_ESTIMATE_NOTE" and _CURRENT.search(subject_side) and assertion["polarity"] == "DENIED":
                applicability, proof = "TARGET", origin
            elif origin == "ADJACENT_ESTIMATE_NOTE" and not subject_side.strip(" •:-–—()") and assertion["polarity"] == "DENIED":
                # A nearby subject-free denial could contradict this table, but supplies no definitive estimate identity.
                applicability = "TARGET_SCOPE_AMBIGUOUS"
            elif origin == "MATCHED_ESTIMATE_SECTION":
                applicability, proof = "TARGET", origin
            else:
                applicability = "UNRESOLVED"
            evidence.append({**witness, **assertion, "applicability": applicability, "binding": proof})
    status = reporting_status((x["applicability"], x["polarity"]) for x in evidence)
    return {"version": VERSION, "status": status, "reason": REASONS[status], "subject": subject, "evidence": evidence}


def admission_issue(raw):
    """Check the pinned assertion text and target provenance at the admission boundary."""
    context = dict(raw.context.conditions)
    if context.get("jorc_rule_version") != VERSION:
        return "RESOURCE_JORC_EVIDENCE_REVALIDATION_REQUIRED"
    table = context.get("reported_table_label")
    anchors = [anchor for anchor in raw.evidence_anchors
               if (anchor.sha256, anchor.source_id) == (raw.evidence.sha256, raw.evidence.source_id)
               and anchor.page is not None and anchor.bbox and anchor.quote]
    scoped = []
    for anchor in anchors:
        applicability = ROLE_TO_SCOPE.get(anchor.role)
        if not applicability or not anchor.text_span:
            continue
        polarities = {item["polarity"] for item in claims(anchor.quote)
                     if (item["start"], item["end"]) == anchor.text_span.in_quote}
        if applicability == "TARGET":
            if anchor.locator in {"SCOPE_CAPTION", "NATIVE_SECTION"}:
                role = "scope" if anchor.locator == "SCOPE_CAPTION" else "resource_section"
                bound = (anchor.page, anchor.table) == (raw.evidence.page, raw.evidence.table) and any(
                    other.role == role and (other.page, other.table, other.quote, other.bbox) ==
                    (anchor.page, anchor.table, anchor.quote, anchor.bbox) for other in anchors)
            elif anchor.locator == "TABLE_REFERENCE":
                offset, end = anchor.text_span.in_quote
                names = table_numbers(anchor.quote[offset:end]) or table_numbers(anchor.quote)
                bound = bool(table and names == {table})
            elif anchor.locator == "MATCHED_ESTIMATE_SECTION":
                bound = any(other.role == "jorc_section_scope" and other.page == anchor.page
                            and other.bbox[3] <= anchor.bbox[1] and
                            section_matches(other.quote, raw.scope_id, raw.effective_date) for other in anchors) and any(
                            other.role == "jorc_estimate_scope" and anchor.page <= other.page <= raw.evidence.page
                            for other in anchors)
            elif anchor.locator == "ADJACENT_ESTIMATE_NOTE":
                start, end = anchor.text_span.in_quote
                bound = (anchor.page == raw.evidence.page and polarities == {"DENIED"}
                         and _CURRENT.search(anchor.quote[start:end]))
            else:
                bound = False
            if not bound:
                applicability = "TARGET_SCOPE_AMBIGUOUS"
        scoped.extend((applicability, polarity) for polarity in polarities)
    status = reporting_status(scoped)
    if context.get("jorc_status") != status:
        return REASONS[status] or "RESOURCE_JORC_EVIDENCE_STATUS_MISMATCH"
    return REASONS[status]
