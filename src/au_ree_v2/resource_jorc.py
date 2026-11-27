"""Classify located reporting-standard assertions about one resource estimate."""

import re


VERSION = "resource-jorc-proposition-v2"
_CODE = r"(?:JORC\b(?:\s+Code(?:\d+)?)?|Joint Ore Reserves Committee)"
_CODE_EDITION = rf"{_CODE}(?:\s+20\d{{2}})?"
_RESOURCE = r"(?:(?:global|total)\s+)?(?:mineral\s+)?resources?(?:\s+estimate)?"
_METHOD = r"(?:reported|estimated|classified|prepared|compiled)"
_ADJECTIVE = r"(?:non[-‐‑–—]?)?compliant"
_RELATION = (r"(?:the\s+)?(?:(?:relevant|applicable|reporting|current|minimum)\s+)*"
             r"(?:(?:guidelines|requirements|provisions|standards|principles)\s+"
             r"(?:of|under|in|set\s+out\s+in)\s+(?:the\s+)?)?")
_NEGATION = (r"(?:not|never|no\s+longer|cannot|can['’]t|"
             r"(?:doesn|didn|don|isn|wasn|aren|weren|hasn|haven|hadn|won|wouldn|couldn|shouldn|mustn)['’]t)")
_PROSPECTIVE = r"(?:will|(?:expected|intended|planned|anticipated)\s+to)"
_MODAL = r"(?:can(?!['’]t\b)|may|might|could|would|should|possibly|probably|potentially|necessarily|(?:appears|seems)\s+to)"
_AUX = r"(?:am|is|are|was|were|be|been|being|has|have|had|do|does|did)"
_EVALUATION = (r"(?:considered|deemed|judged|demonstrated|confirmed|shown|established|certified|"
               r"recognized|recognised|regarded|classified|described|reported|accepted|assessed|found)"
               r"(?:\s+(?:as|to\s+be))?")
_ADVERB = r"(?:yet|fully|strictly|entirely|technically|currently|previously|still|now|actually|formally|explicitly)"
_LINK_WORD = rf"(?:{_NEGATION}|{_PROSPECTIVE}|{_MODAL}|{_AUX}|{_EVALUATION}|{_ADVERB}|to)"
_PREFIX = re.compile(rf"\b(?:{_LINK_WORD}\b\s*[,()]*\s*)+$", re.I)
_MODIFIERS = tuple((kind, re.compile(rf"\b{pattern}\b", re.I)) for kind, pattern in (
    ("NEGATION", _NEGATION), ("PROSPECTIVE", _PROSPECTIVE), ("MODAL", _MODAL),
    ("EVALUATION", _EVALUATION), ("QUALIFIER", _ADVERB),
))
_CONDITION = re.compile(r"\b(?:if|unless|provided\s+that|subject\s+to|assuming|contingent\s+on)\b", re.I)
_NEGATED_CLASSIFICATION = re.compile(
    rf"\b(?P<negation>non[-\s‐‑–—]+|without\s+|no\s+|(?:not|never)\s+(?:an?\s+)?)"
    rf"(?P<code>{_CODE_EDITION})(?!\s*[-‐‑–—]?\s*compliant\b)", re.I,
)
_DECLARATION = re.compile(rf"\b(?P<code>{_CODE_EDITION})\s*[-‐‑–—]?\s*{_RESOURCE}\b", re.I)
_RESOURCE_REFERENCE = re.compile(rf"\b(?:{_RESOURCE}|resource\s+estimate|MRE|estimate)\b", re.I)
_REVISION_NOUN = re.compile(r"\s+(?:changes?|revisions?|amendments?|updates?)\b", re.I)
_ANAPHOR = re.compile(rf"^\s*(?:it|this|that|they|these|those|(?:the|this|that)\s+"
                       rf"(?:{_RESOURCE}|resource\s+estimate|MRE|estimate))\b", re.I)
_PLURAL_ANAPHOR = re.compile(r"^\s*(?:they|these|those)\b", re.I)
_CODE_ADJECTIVE = re.compile(rf"\b(?P<code>{_CODE_EDITION})\s*(?:[-‐‑–—(]\s*)?"
                             rf"(?P<link>(?:{_LINK_WORD}\b\s+)*)"
                             rf"(?P<core>{_ADJECTIVE})\b(?![-‐‑–—]\w)", re.I)
_CODE_AFTER_PREDICATE = re.compile(
    rf"\b(?P<core>{_METHOD}\s+(?:under|in\s+(?:full\s+)?accordance(?:\s+with)?)"
    rf"|(?:{_ADJECTIVE}|comply|complies|complied)\s+(?:with|under|to)"
    rf"|(?:in\s+compliance|in\s+(?:full\s+)?accordance)\s+with"
    rf"|conform(?:s|ed)?\s+to|adhere(?:s|d)?\s+to|meet(?:s)?\s+|met\s+|satisf(?:y|ies|ied)\s+)"
    rf"\s*{_RELATION}(?P<code>{_CODE_EDITION})\b", re.I,
)
_BARE_COMPLIANCE = re.compile(rf"\b(?P<core>{_ADJECTIVE}|in\s+compliance|comply|complies|complied|"
                              rf"{_METHOD}\s+in\s+(?:full\s+)?accordance)\b", re.I)
_CLAUSE_BREAK = re.compile(r"(?<=[.;!?])\s+|\s+(?:but|whereas|while|and)\s+(?=(?:the|this|that|it)\b)", re.I)
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


def _prefix(clause, position):
    # Only the local auxiliary/evaluation chain can modify this predicate.
    floor = max(0, position - 160)
    match = _PREFIX.search(clause[floor:position])
    return floor + match.start() if match else position


def _predicate(clause, start, end, *, code=None, argument_end=None, extra=(), kind="COMPLIANCE"):
    modifiers = [{"kind": label, "start": start + match.start(), "end": start + match.end()}
                 for label, pattern in _MODIFIERS for match in pattern.finditer(clause[start:end])]
    modifiers.extend({"kind": "NEGATION", "start": left, "end": right} for left, right in extra)
    condition = _CONDITION.search(clause)
    if condition:
        modifiers.append({"kind": "CONDITION", "start": condition.start(), "end": condition.end()})
    labels = {item["kind"] for item in modifiers}
    modality = next((item for item in ("CONDITION", "PROSPECTIVE", "MODAL") if item in labels), "ASSERTED")
    # `cannot` is a denial of the stated standard. An uncertain or future
    # statement cannot attest to the present standard, with either polarity.
    polarity = "UNRESOLVED" if modality != "ASSERTED" else "DENIED" if "NEGATION" in labels else "AFFIRMED"
    result = {"subject_start": 0, "subject_end": argument_end if argument_end is not None else start,
              "predicate_start": start, "predicate_end": end, "predicate_kind": kind,
              "polarity": polarity, "modality": modality,
              "modifiers": sorted(modifiers, key=lambda item: (item["start"], item["end"], item["kind"]))}
    if code is not None:
        result["code_start"], result["code_end"] = code
    return result


def _compliance_propositions(clause, declaration, previous_code):
    names = list(_DECLARATION.finditer(clause))
    predicates = []
    # A code-qualified adjective in prose needs a predicate, not merely a
    # noun modifier such as "a discussion of JORC-compliant resources".
    for match in _CODE_ADJECTIVE.finditer(clause):
        start = _prefix(clause, match.start())
        if start < match.start() or declaration:
            negative = ((match.start("core"), match.start("core") + 3),) if match["core"].lower().startswith("non") else ()
            predicates.append(_predicate(clause, start, match.end(), code=match.span("code"), extra=negative))
    for match in _CODE_AFTER_PREDICATE.finditer(clause):
        start = _prefix(clause, match.start())
        core = match["core"].lower()
        if core.startswith(("compliant", "non")) and start == match.start() and not declaration:
            # An adjective can itself be a subject-free note, but an embedded
            # noun modifier does not assert compliance of this estimate.
            if clause[:start].strip(" •:-–—()"):
                continue
        if any(item["predicate_start"] <= start < item["predicate_end"] for item in predicates):
            continue
        negative = ((match.start(), match.start() + 3),) if core.startswith("non") else ()
        predicates.append(_predicate(clause, start, match.end(), code=match.span("code"), extra=negative))
    for match in _BARE_COMPLIANCE.finditer(clause):
        start = _prefix(clause, match.start())
        # The standard can be carried by this clause's subject or an explicit
        # contrast between the preceding estimate and the current estimate.
        subject_names = [name for name in names if name.end() <= start]
        if (start == match.start() or any(item["predicate_start"] <= start < item["predicate_end"] for item in predicates)
                or re.match(r"\s+(?:with|under|to)\b", clause[match.end():], re.I)):
            continue
        if len(subject_names) == 1 or (not subject_names and previous_code
                                       and (_OLD.search(clause[:start]) or _CURRENT.search(clause[:start])
                                            or _ANAPHOR.match(clause[:start]))):
            code = subject_names[0].span("code") if subject_names else None
            negative = ((match.start(), match.start() + 3),) if match["core"].lower().startswith("non") else ()
            predicates.append(_predicate(clause, start, match.end(), code=code, extra=negative))
    for match in _NEGATED_CLASSIFICATION.finditer(clause):
        reference = _RESOURCE_REFERENCE.match(clause, match.end() + len(clause[match.end():]) - len(clause[match.end():].lstrip()))
        if reference and _REVISION_NOUN.match(clause, reference.end()):
            continue
        start = _prefix(clause, match.start())
        if (not declaration and not reference and start == match.start()
                or any(item["predicate_start"] <= match.start() < item["predicate_end"] for item in predicates)):
            continue
        predicates.append(_predicate(clause, start, reference.end() if reference else match.end(),
                                     code=match.span("code"), extra=(match.span("negation"),), kind="CLASSIFICATION"))
    if declaration and not predicates:
        for name in names:
            predicates.append(_predicate(clause, name.start(), name.end(), code=name.span("code"),
                                         argument_end=name.end(), kind="CLASSIFICATION"))
    return sorted(predicates, key=lambda item: (item["predicate_start"], item["predicate_end"]))


def claims(quote, *, declaration=False):
    """Locate subjects, predicates and their modifiers in one physical source quote."""
    start = 0
    previous_reference = None
    previous_code = False
    for boundary in [*(_CLAUSE_BREAK.finditer(quote)), None]:
        end = boundary.start() if boundary else len(quote)
        clause = quote[start:end]
        propositions = _compliance_propositions(clause, declaration, previous_code)
        resolved_reference = None
        for assertion in propositions:
            subject = clause[:assertion["subject_end"]]
            anaphor = _ANAPHOR.match(subject)
            bindings = {key: start + value if key.endswith(("_start", "_end")) else value
                        for key, value in assertion.items()}
            bindings["modifiers"] = [{"kind": item["kind"], "start": start + item["start"], "end": start + item["end"]}
                                     for item in assertion["modifiers"]]
            if anaphor and not table_numbers(clause) and previous_reference and not _PLURAL_ANAPHOR.match(subject):
                resolved_reference = previous_reference
                bindings["subject_start"], bindings["subject_end"] = resolved_reference
            bindings["anaphoric"] = resolved_reference is not None
            bindings["subject_reference_unresolved"] = bool(_PLURAL_ANAPHOR.match(subject)
                or (anaphor and subject.strip().casefold() in {"it", "this", "that"} and not resolved_reference
                    and not table_numbers(clause)))
            yield {"start": start, "end": end, **bindings}
        previous_reference = ((start, end) if table_numbers(clause) and _RESOURCE_REFERENCE.search(clause)
                              else resolved_reference)
        previous_code = any("code_start" in item for item in propositions)
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
    if ("TARGET", "UNRESOLVED") in pairs or any(scope == "TARGET_SCOPE_AMBIGUOUS" for scope, _ in pairs):
        return "UNRESOLVED_SCOPE"
    if positive or negative:
        return "AFFIRMED" if positive else "DENIED"
    return "UNRESOLVED_SCOPE" if pairs else "UNESTABLISHED"


def _disposition(scoped):
    status = reporting_status(scoped)
    reason = ("RESOURCE_JORC_PREDICATE_UNRESOLVED" if status == "UNRESOLVED_SCOPE"
              and ("TARGET", "UNRESOLVED") in scoped else REASONS[status])
    return status, reason


def _proposition_tables(quote, assertion):
    subject = quote[assertion["subject_start"]:assertion["subject_end"]]
    clause = quote[assertion["start"]:assertion["end"]]
    return table_numbers(subject) or table_numbers(clause)


def evaluate(witnesses, subject, *, projects_in, dates_in):
    """Keep unrelated assertions as evidence without lending their standard to this row."""
    evidence = []
    table = subject["reported_table_label"]
    for witness in witnesses:
        quote = witness["quote"]
        origin = witness["origin"]
        declaration = origin in {"SCOPE_CAPTION", "NATIVE_SECTION"}
        for assertion in claims(quote, declaration=declaration):
            clause = quote[assertion["start"]:assertion["end"]]
            subject_side = quote[assertion["subject_start"]:assertion["subject_end"]]
            named = _proposition_tables(quote, assertion)
            old = _OLD.search(subject_side)
            proof = None
            projects, dates = projects_in(subject_side), dates_in(subject_side) | dates_in(clause)
            foreign = bool(projects - {subject["project_id"]} or dates - {subject["effective_date"]})
            if named and named != {table}:
                applicability = "TARGET_SCOPE_AMBIGUOUS" if table in named else "OTHER_ESTIMATE"
            elif foreign:
                applicability = "TARGET_SCOPE_AMBIGUOUS" if named == {table} else "OTHER_ESTIMATE"
            elif assertion["subject_reference_unresolved"]:
                applicability = ("TARGET_SCOPE_AMBIGUOUS" if named == {table} or declaration
                                 or origin in {"ADJACENT_ESTIMATE_NOTE", "MATCHED_ESTIMATE_SECTION"} else "UNRESOLVED")
            elif old and not (declaration or named == {table} and witness["physical_page"] == subject["physical_page"]):
                applicability = "TARGET_SCOPE_AMBIGUOUS" if named == {table} else "OTHER_ESTIMATE"
            elif declaration:
                applicability, proof = "TARGET", origin
            elif named == {table}:
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
    status, reason = _disposition({(x["applicability"], x["polarity"]) for x in evidence})
    return {"version": VERSION, "status": status, "reason": reason, "subject": subject, "evidence": evidence}


def admission_issue(raw):
    """Check the pinned assertion text and target provenance at the admission boundary."""
    context = dict(raw.context.conditions)
    if context.get("jorc_rule_version") != VERSION:
        return "RESOURCE_JORC_EVIDENCE_REVALIDATION_REQUIRED"
    table = context.get("reported_table_label")
    anchors = [anchor for anchor in raw.evidence_anchors
               if (anchor.sha256, anchor.source_id) == (raw.evidence.sha256, raw.evidence.source_id)
               and anchor.page is not None and anchor.bbox and anchor.quote]
    scoped = set()
    for anchor in anchors:
        applicability = ROLE_TO_SCOPE.get(anchor.role)
        if not applicability or not anchor.text_span:
            continue
        declaration = anchor.locator in {"SCOPE_CAPTION", "NATIVE_SECTION"} or any(
            other.role in {"scope", "resource_section"} and (other.page, other.table, other.quote, other.bbox) ==
            (anchor.page, anchor.table, anchor.quote, anchor.bbox) for other in anchors)
        propositions = [item for item in claims(anchor.quote, declaration=declaration)
                        if (item["start"], item["end"]) == anchor.text_span.in_quote]
        polarities = {item["polarity"] for item in propositions}
        if applicability == "TARGET":
            if anchor.locator in {"SCOPE_CAPTION", "NATIVE_SECTION"}:
                role = "scope" if anchor.locator == "SCOPE_CAPTION" else "resource_section"
                bound = (anchor.page, anchor.table) == (raw.evidence.page, raw.evidence.table) and any(
                    other.role == role and (other.page, other.table, other.quote, other.bbox) ==
                    (anchor.page, anchor.table, anchor.quote, anchor.bbox) for other in anchors)
            elif anchor.locator == "TABLE_REFERENCE":
                bound = bool(table and propositions and all(not item["subject_reference_unresolved"]
                             and _proposition_tables(anchor.quote, item) == {table} for item in propositions))
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
        scoped.update((applicability, polarity) for polarity in polarities)
    status, reason = _disposition(scoped)
    if context.get("jorc_status") != status:
        return reason or "RESOURCE_JORC_EVIDENCE_STATUS_MISMATCH"
    return reason
