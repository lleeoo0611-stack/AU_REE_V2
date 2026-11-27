"""Classify located reporting-standard assertions about one resource estimate."""

from dataclasses import dataclass
import re

from .resource_discourse import changes_estimate_subject, clause_spans, estimate_years, older_estimate, other_estimate, table_numbers


VERSION = "resource-jorc-proposition-v4"
_CODE = r"(?:JORC\b(?:\s+Code(?:\d+)?)?|Joint Ore Reserves Committee)"
_CODE_EDITION = rf"{_CODE}(?:\s+20\d{{2}})?"
_RESOURCE = r"(?:(?:global|total)\s+)?(?:mineral\s+)?resources?(?:\s+estimate)?"
_METHOD = r"(?:reported|estimated|classified|prepared|compiled)"
_ADJECTIVE = r"(?:non[-‐‑–—]?)?compliant"
_RELATION = (r"(?:the\s+)?(?:(?:relevant|applicable|reporting|current|minimum)\s+)*"
             r"(?:(?:guidelines|requirements|provisions|standards|principles)\s+"
             r"(?:of|under|in|set\s+out\s+in)\s+(?:the\s+)?)?")
_NEGATION = (r"(?:not(?!\s+only\b)|never|no\s+longer|cannot|can['’]t|"
             r"(?:doesn|didn|don|isn|wasn|aren|weren|hasn|haven|hadn|won|wouldn|couldn|shouldn|mustn)['’]t)")
_PROSPECTIVE = r"(?:will|(?:expected|intended|planned|anticipated)\s+to)"
_MODAL = (r"(?:can(?!['’]t\b)|may|might|could|would|should|possibly|probably|potentially|necessarily|"
          r"allegedly|purportedly|apparently|(?:appears|seems)\s+to)")
_AUX = r"(?:am|is|are|was|were|be|been|being|has|have|had|do|does|did)"
_EVALUATION = (r"(?:considered|deemed|judged|demonstrated|confirmed|shown|established|certified|"
               r"recognized|recognised|regarded|classified|described|reported|accepted|assessed|found)"
               r"(?:\s+(?:as|to\s+be))?")
_ADVERB = r"(?:not\s+only|yet|still|now|[a-z]+ly)"
_LINK_WORD = rf"(?:{_NEGATION}|{_PROSPECTIVE}|{_MODAL}|{_AUX}|{_EVALUATION}|{_ADVERB}|to)"
_PREFIX = re.compile(rf"\b(?:{_LINK_WORD}\b\s*[,()]*\s*)+$", re.I)
_LINKS_ONLY = re.compile(rf"(?:{_LINK_WORD}\b\s*)+", re.I)
_ASSERTIVE_LINK = re.compile(rf"\b(?:{_AUX}|{_EVALUATION}|{_NEGATION}|{_PROSPECTIVE}|{_MODAL})\b", re.I)
_PARENTHETICAL = re.compile(r"\([^()]{1,80}\)|,[^,()]{1,80},")
_ARTICLE = re.compile(r"\ban?\s*$", re.I)
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
_CURRENT = re.compile(r"\b(?:current|updated|latest|this)\s+(?:(?:mineral\s+)?resource\s+)?(?:estimate|MRE|resource)\b", re.I)
_OTHER_REPORTING_CODE = re.compile(r"\b(?:NI\s*43[-–]101|SAMREC|PERC|S\s*-?\s*K\s*1300)\b", re.I)
_SCOPE_END = re.compile(r"\s+(?:(?:rare earth )?deposit|project)\s*$", re.I)
_SECTION = re.compile(r"^(20\d\d)\s+(.+?)\s+(?:Mineral\s+)?Resource Estimate$", re.I)
_LAYOUT_HEADING = re.compile(r"^\s*(?:appendix|section|figure|table of contents)\b", re.I)
_CONTINUATION = "ADJACENT_BLOCK_CONTINUATION"
_DISCOURSE_ROLE = "jorc_discourse_context"
_MAX_BLOCK_GAP = 18
_MAX_BLOCK_LEFT_OFFSET = 16
_MAX_DISCOURSE_BLOCKS = 4
ROLE_TO_SCOPE = {
    "jorc_target": "TARGET",
    "jorc_other": "OTHER_ESTIMATE",
    "jorc_unscoped": "UNRESOLVED",
    "jorc_ambiguous_target": "TARGET_SCOPE_AMBIGUOUS",
}


@dataclass(frozen=True)
class _LocatedSpan:
    block: int | None
    start: int
    end: int
    text: str


@dataclass(frozen=True)
class _Antecedent:
    span: _LocatedSpan
    unique: bool


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
    match = _PREFIX.search(_link_text(clause[floor:position]))
    return floor + match.start() if match else position


def _link_text(text):
    # Keep positional alignment while ignoring an interrupted adjunct such as
    # "is, despite not being audited, considered JORC compliant".
    def mask(match):
        inner = match[0][1:-1]
        return f" {inner} " if _LINKS_ONLY.fullmatch(inner.strip()) else " " * len(match[0])

    return _PARENTHETICAL.sub(mask, text)


def _predicate(clause, start, end, *, code=None, argument_end=None, extra=(), kind="COMPLIANCE"):
    predicate_text = _link_text(clause[start:end])
    modifiers = [{"kind": label, "start": start + match.start(), "end": start + match.end()}
                 for label, pattern in _MODIFIERS for match in pattern.finditer(predicate_text)]
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


def _implicit_subject(text):
    return not text.strip(" •:-–—()")


def _compliance_propositions(clause, declaration, previous_code, preserve_unresolved=False):
    names = list(_DECLARATION.finditer(clause))
    predicates = []
    # A code-qualified adjective in prose needs a predicate, not merely a
    # noun modifier such as "a discussion of JORC-compliant resources".
    for match in _CODE_ADJECTIVE.finditer(clause):
        article = _ARTICLE.search(clause[:match.start()])
        link_start = article.start() if article else match.start()
        start = _prefix(clause, link_start)
        if _ASSERTIVE_LINK.search(_link_text(clause[start:link_start])) or declaration:
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
        subject = clause[:start]
        implicit = _implicit_subject(subject) or _ANAPHOR.match(subject)
        continued = bool(previous_code and (older_estimate(subject) or _CURRENT.search(subject) or implicit))
        if len(subject_names) == 1 or continued or (preserve_unresolved and implicit):
            code = subject_names[0].span("code") if subject_names else None
            negative = ((match.start(), match.start() + 3),) if match["core"].lower().startswith("non") else ()
            proposition = _predicate(clause, start, match.end(), code=code, extra=negative)
            if code is not None or continued or proposition["polarity"] == "DENIED":
                predicates.append({**proposition, "reporting_code_unresolved": code is None and not continued})
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


def _block_claims(quote, block, incoming, *, declaration=False, scoped_block=False, preserve_unresolved=False):
    """Locate claims and return the continuing subject and reporting code."""
    reference, explicit_code, other_code = incoming
    assertions = []
    for start, end in clause_spans(quote):
        clause = quote[start:end]
        tables = table_numbers(clause)
        # A new named table and estimate replace the antecedent. A subject
        # switch without a unique table remains visible as ambiguous instead
        # of borrowing the preceding estimate. A neutral clause leaves both
        # the subject and the reporting-standard reference available.
        scope_change = changes_estimate_subject(clause, previous_subject=reference.span.text if reference else None)
        if _OTHER_REPORTING_CODE.search(clause) and not re.search(_CODE, clause, re.I):
            explicit_code, other_code = None, True
        propositions = _compliance_propositions(clause, declaration, explicit_code is not None,
                                                preserve_unresolved and not other_code)
        for assertion in propositions:
            subject = clause[:assertion["subject_end"]]
            anaphor = _ANAPHOR.match(subject) or _implicit_subject(subject)
            bindings = {key: start + value if key.endswith(("_start", "_end")) else value
                        for key, value in assertion.items()}
            bindings["modifiers"] = [{"kind": item["kind"], "start": start + item["start"], "end": start + item["end"]}
                                     for item in assertion["modifiers"]]
            if "code_start" in bindings:
                left, right = bindings["code_start"], bindings["code_end"]
                explicit_code, other_code = _LocatedSpan(block, left, right, quote[left:right]), False
            elif explicit_code is not None:
                if explicit_code.block == block:
                    bindings["code_start"], bindings["code_end"] = explicit_code.start, explicit_code.end
                else:
                    bindings["reporting_reference"] = explicit_code
            resolved_reference = reference if anaphor and not scope_change and not _PLURAL_ANAPHOR.match(subject) else None
            if resolved_reference:
                antecedent = resolved_reference.span
                if antecedent.block == block:
                    bindings["subject_start"], bindings["subject_end"] = antecedent.start, antecedent.end
                else:
                    bindings["antecedent"] = antecedent
            bindings["anaphoric"] = resolved_reference is not None
            bindings["subject_reference_unresolved"] = bool(_PLURAL_ANAPHOR.match(subject)
                or (resolved_reference and not resolved_reference.unique)
                or (anaphor and (_implicit_subject(subject) or subject.strip().casefold() in {"it", "this", "that"})
                    and not resolved_reference
                    and not tables))
            assertions.append({"start": start, "end": end, **bindings})
        if scope_change:
            reference = _Antecedent(_LocatedSpan(block, start, end, clause),
                                    len(tables) == 1 and bool(_RESOURCE_REFERENCE.search(clause)))
        elif not reference and scoped_block and propositions and _RESOURCE_REFERENCE.search(clause):
            reference = _Antecedent(_LocatedSpan(block, start, end, clause), True)
    return assertions, (reference, explicit_code, other_code)


def claims(quote, *, declaration=False):
    """Locate subjects and predicates within one physical block, including neutral gaps."""
    yield from _block_claims(quote, None, (None, None, False), declaration=declaration)[0]


def scope_stem(text):
    return _SCOPE_END.sub("", text or "").strip().casefold()


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


def _block_order(witness):
    box = witness["bbox"]
    return witness["physical_page"], box[1], box[0], box[3], box[2]


def _near_previous_block(left, right):
    if (left["physical_page"] != right["physical_page"]
            or left.get("source_sha256") != right.get("source_sha256")
            or left.get("source_id") != right.get("source_id")):
        return False
    a, b = left["bbox"], right["bbox"]
    return (0 <= b[1] - a[3] <= _MAX_BLOCK_GAP and abs(a[0] - b[0]) <= _MAX_BLOCK_LEFT_OFFSET
            and min(a[2], b[2]) > max(a[0], b[0]))


def _starts_section(witness):
    text = witness["quote"]
    return (witness["origin"] in {"SCOPE_CAPTION", "NATIVE_SECTION"} or estimate_heading(text)
            or _LAYOUT_HEADING.search(text))


def _span_record(span, witnesses):
    witness = witnesses[span.block]
    return {name: witness[name] for name in ("source_sha256", "source_id", "physical_page", "bbox", "quote", "origin")
            if name in witness} | {"start": span.start, "end": span.end}


def _located_claims(witnesses):
    """Replay only immediate, unambiguous same-column neighbors on a physical page."""
    witnesses = sorted(witnesses, key=_block_order)
    states = {}
    preceding = []
    for index, witness in enumerate(witnesses):
        path = ()
        incoming = (None, None, False)
        box = witness["bbox"]
        preceding = [prior for prior in preceding if witnesses[prior]["physical_page"] == witness["physical_page"]
                     and witnesses[prior]["bbox"][3] >= box[1] - _MAX_BLOCK_GAP]
        if not _starts_section(witness):
            neighbors = [prior for prior in preceding if _near_previous_block(witnesses[prior], witness)]
            if neighbors:
                nearest_y = max(witnesses[prior]["bbox"][3] for prior in neighbors)
                nearest = [prior for prior in neighbors if nearest_y - witnesses[prior]["bbox"][3] <= 1]
                if len(nearest) == 1:
                    inherited, state = states[nearest[0]]
                    if len(inherited) < _MAX_DISCOURSE_BLOCKS:
                        path, incoming = inherited, state
        origin = witness["origin"]
        assertions, outgoing = _block_claims(witness["quote"], index, incoming,
                                             declaration=origin in {"SCOPE_CAPTION", "NATIVE_SECTION"},
                                             scoped_block=origin in {"MATCHED_ESTIMATE_SECTION", "BOUND_ESTIMATE_CONTEXT"},
                                             preserve_unresolved=True)
        reference, code, _ = outgoing
        retained_from = min(index, reference.span.block if reference else index, code.block if code else index)
        states[index] = (tuple(prior for prior in (*path, index) if prior >= retained_from), outgoing)
        preceding.append(index)
        for assertion in assertions:
            for name in ("antecedent", "reporting_reference"):
                if span := assertion.get(name):
                    assertion[name] = _span_record(span, witnesses)
            yield witness, assertion, [witnesses[prior] for prior in path]


def _subject_text(quote, assertion):
    if antecedent := assertion.get("antecedent"):
        return antecedent["quote"][antecedent["start"]:antecedent["end"]]
    return quote[assertion["subject_start"]:assertion["subject_end"]]


def _proposition_tables(quote, assertion):
    subject = _subject_text(quote, assertion)
    clause = quote[assertion["start"]:assertion["end"]]
    return table_numbers(subject) or table_numbers(clause)


def evaluate(witnesses, subject, *, projects_in, dates_in):
    """Keep unrelated assertions as evidence without lending their standard to this row."""
    evidence = []
    discourse_context = {}
    table = subject["reported_table_label"]
    for witness, assertion, preceding in _located_claims(witnesses):
        quote = witness["quote"]
        origin = witness["origin"]
        declaration = origin in {"SCOPE_CAPTION", "NATIVE_SECTION"}
        clause = quote[assertion["start"]:assertion["end"]]
        subject_side = _subject_text(quote, assertion)
        antecedent = assertion.get("antecedent")
        named = _proposition_tables(quote, assertion)
        old = older_estimate(subject_side)
        proof = None
        projects, dates = projects_in(subject_side), dates_in(subject_side) | dates_in(clause)
        effective_date = subject["effective_date"]
        years = estimate_years(subject_side)
        earlier_dated_estimate = bool(old and effective_date and (
            max(dates) < effective_date if dates else years and max(years) < effective_date[:4]))
        other_named_project = bool(subject["project_id"] and len(projects) == 1 and subject["project_id"] not in projects)
        separate = other_estimate(subject_side)
        separate_date = bool(effective_date and (len(dates) == 1 and effective_date not in dates
                             or not dates and len(years) == 1 and effective_date[:4] not in years))
        foreign = bool(projects - {subject["project_id"]} or dates - {effective_date}
                       or (effective_date and years - {effective_date[:4]}))
        gap = quote[assertion["subject_end"]:assertion["start"]] if assertion["anaphoric"] and not antecedent else ""
        if antecedent:
            start = next((i for i, block in enumerate(preceding) if (block["bbox"], block["quote"]) ==
                          (antecedent["bbox"], antecedent["quote"])), len(preceding))
            gap = " ".join([antecedent["quote"][antecedent["end"]:],
                            *(block["quote"] for block in preceding[start + 1:]), quote[:assertion["start"]]])
        conflicting_gap = bool(gap and (projects_in(gap) - {subject["project_id"]} or dates_in(gap) - {effective_date}))
        if named and named != {table}:
            applicability = "TARGET_SCOPE_AMBIGUOUS" if table in named else "OTHER_ESTIMATE"
        elif earlier_dated_estimate or other_named_project or separate and separate_date:
            applicability = "OTHER_ESTIMATE"
        elif separate:
            applicability = "TARGET_SCOPE_AMBIGUOUS" if named == {table} else "UNRESOLVED"
        elif foreign:
            applicability = "TARGET_SCOPE_AMBIGUOUS" if named == {table} else "OTHER_ESTIMATE"
        elif old and not named and not declaration:
            applicability = "OTHER_ESTIMATE"
        elif assertion["subject_reference_unresolved"] or assertion.get("reporting_code_unresolved") or conflicting_gap:
            near_target = (named == {table} or table in table_numbers(quote) or declaration
                           or origin in {"ADJACENT_ESTIMATE_NOTE", "MATCHED_ESTIMATE_SECTION", "BOUND_ESTIMATE_CONTEXT"})
            applicability = "TARGET_SCOPE_AMBIGUOUS" if near_target else "UNRESOLVED"
        elif old and not (declaration or named == {table} and witness["physical_page"] == subject["physical_page"]):
            applicability = "TARGET_SCOPE_AMBIGUOUS" if named == {table} else "OTHER_ESTIMATE"
        elif declaration:
            applicability, proof = "TARGET", origin
        elif origin == "BOUND_ESTIMATE_CONTEXT" and any(left <= assertion["start"] and assertion["end"] <= right
                                                       for left, right in witness.get("bound_spans", ())):
            applicability, proof = "TARGET", origin
        elif named == {table}:
            if (witness["physical_page"] == subject["physical_page"] and subject.get("reported_table_unique_on_page", True)):
                applicability, proof = "TARGET", _CONTINUATION if antecedent else "TABLE_REFERENCE"
            elif origin == "MATCHED_ESTIMATE_SECTION":
                applicability, proof = "TARGET", origin
            else:
                applicability = ("TARGET_SCOPE_AMBIGUOUS" if witness["physical_page"] == subject["physical_page"]
                                 else "UNRESOLVED")
        elif origin == "ADJACENT_ESTIMATE_NOTE" and _CURRENT.search(subject_side) and assertion["polarity"] == "DENIED":
            applicability, proof = "TARGET", origin
        elif origin == "ADJACENT_ESTIMATE_NOTE" and _implicit_subject(subject_side) and assertion["polarity"] == "DENIED":
            # A nearby subject-free denial could contradict this table, but supplies no definitive estimate identity.
            applicability = "TARGET_SCOPE_AMBIGUOUS"
        elif origin == "MATCHED_ESTIMATE_SECTION":
            applicability, proof = "TARGET", origin
        else:
            applicability = "UNRESOLVED"
        if antecedent or assertion.get("reporting_reference"):
            for block in [*preceding, witness]:
                discourse_context[block["physical_page"], tuple(block["bbox"]), block["quote"]] = block
        evidence.append({**witness, **assertion, "applicability": applicability, "binding": proof})
    status, reason = _disposition({(x["applicability"], x["polarity"]) for x in evidence})
    return {"version": VERSION, "status": status, "reason": reason, "subject": subject, "evidence": evidence,
            "discourse_context": list(discourse_context.values())}


def _anchor_key(anchor):
    return anchor.page, anchor.bbox, anchor.quote


def _replay_witnesses(anchors):
    witnesses = {}
    for anchor in anchors:
        if anchor.role not in ROLE_TO_SCOPE and anchor.role != _DISCOURSE_ROLE:
            continue
        origin = anchor.locator if anchor.role == _DISCOURSE_ROLE else "SAME_PAGE"
        if anchor.role != _DISCOURSE_ROLE:
            if any(other.role in {"scope", "resource_section"} and _anchor_key(other) == _anchor_key(anchor)
                   and other.table == anchor.table for other in anchors):
                origin = "SCOPE_CAPTION" if anchor.row is None else "NATIVE_SECTION"
            elif anchor.locator in {"MATCHED_ESTIMATE_SECTION", "BOUND_ESTIMATE_CONTEXT", "ADJACENT_ESTIMATE_NOTE"}:
                origin = anchor.locator
        key = _anchor_key(anchor)
        if key not in witnesses or anchor.role == _DISCOURSE_ROLE:
            witnesses[key] = {"physical_page": anchor.page, "bbox": anchor.bbox, "quote": anchor.quote,
                              "source_sha256": anchor.sha256, "source_id": anchor.source_id, "origin": origin}
    for witness, assertion, _ in _located_claims(witnesses.values()):
        yield (witness["physical_page"], witness["bbox"], witness["quote"], assertion["start"], assertion["end"]), assertion


def admission_issue(raw):
    """Check the pinned assertion text and target provenance at the admission boundary."""
    context = dict(raw.context.conditions)
    if context.get("jorc_rule_version") != VERSION:
        return "RESOURCE_JORC_EVIDENCE_REVALIDATION_REQUIRED"
    table = context.get("reported_table_label")
    anchors = [anchor for anchor in raw.evidence_anchors
               if (anchor.sha256, anchor.source_id) == (raw.evidence.sha256, raw.evidence.source_id)
               and anchor.page is not None and anchor.bbox and anchor.quote]
    parsed = {}
    for key, proposition in _replay_witnesses(anchors):
        parsed.setdefault(key, []).append(proposition)
    scoped = set()
    for anchor in anchors:
        applicability = ROLE_TO_SCOPE.get(anchor.role)
        if not applicability or not anchor.text_span:
            continue
        propositions = parsed.get((*_anchor_key(anchor), *anchor.text_span.in_quote), ())
        polarities = {item["polarity"] for item in propositions}
        if applicability == "TARGET":
            if anchor.locator in {"SCOPE_CAPTION", "NATIVE_SECTION"}:
                role = "scope" if anchor.locator == "SCOPE_CAPTION" else "resource_section"
                bound = (anchor.page, anchor.table) == (raw.evidence.page, raw.evidence.table) and any(
                    other.role == role and (other.page, other.table, other.quote, other.bbox) ==
                    (anchor.page, anchor.table, anchor.quote, anchor.bbox) for other in anchors)
            elif anchor.locator in {"TABLE_REFERENCE", _CONTINUATION}:
                bound = bool(anchor.page == raw.evidence.page and table and propositions
                             and context.get("reported_table_unique_on_page") != "false"
                             and all(not item["subject_reference_unresolved"]
                             and not item.get("reporting_code_unresolved")
                             and bool(item.get("antecedent")) == (anchor.locator == _CONTINUATION)
                             and _proposition_tables(anchor.quote, item) == {table} for item in propositions))
            elif anchor.locator == "BOUND_ESTIMATE_CONTEXT":
                bound = bool(propositions and all(not item["subject_reference_unresolved"] for item in propositions)
                             and any(other.role == "estimate_identity_reference"
                                     and (other.page, other.quote, other.bbox) == (anchor.page, anchor.quote, anchor.bbox)
                                     and other.text_span and other.text_span.in_quote[0] <= anchor.text_span.in_quote[0]
                                     and anchor.text_span.in_quote[1] <= other.text_span.in_quote[1]
                                     for other in anchors))
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
            if not bound or any(other_estimate(_subject_text(anchor.quote, item)) for item in propositions):
                applicability = "TARGET_SCOPE_AMBIGUOUS"
        scoped.update((applicability, polarity) for polarity in polarities)
    status, reason = _disposition(scoped)
    if context.get("jorc_status") != status:
        return reason or "RESOURCE_JORC_EVIDENCE_STATUS_MISMATCH"
    return reason
