"""Re-read physical resource rows eligible for automatic admission checks."""

from contextlib import nullcontext
from datetime import date
from decimal import Decimal
from pathlib import Path
import re

from .document_processing import DocumentUnavailable, PdfDocumentCache
from .numeric_evidence import numeric_token_spans, scalar_decimal
from .observation_pipeline import raw_from_candidate
from .observation_schema import value_evidence_issue
from .pdf_extract import _matches
from .resource_estimate import cutoff_signature, normalize_cutoff
from .resource_jorc import (
    VERSION as JORC_VERSION, SCOPE_TO_ROLE, estimate_heading, evaluate as assess_jorc, scope_stem, section_matches,
    table_numbers,
)
from .semantic_resource import (
    CAPTION, CUTOFF, ESTIMATE_DATE, GRADE_PHRASE, MONTHS, RISKY, _CLASSIFIED_ROW, _anchors, _header_unit,
    clean, column_header_anchors, located_column_headers, page_table_caption,
)
from .store import digest
from .technical_tables import cells


VERSION = "native-resource-row-v4"
_VARIABLES = ("ore_mt", "grade", "contained_treo_kt")
_RESOURCE = re.compile(r"\b(?:mineral resources?|resource estimate|MRE)\b", re.I)
_TABLE_PROSE = re.compile(r"^table\s+\d+(?:[-.]\d+)*\s+(?:(?:above|below)\s+)?"
                         r"(?:is|are|was|were|has|had|does|contains?|includes?|lists?|presents?|shows?|"
                         r"summari[sz]es?|sets?\s+out|compares?|provides?|records?|gives?)\b", re.I)
_TOTAL = re.compile(r"(?:(?:grand|global|project|combined)\s+)?total(?:\s*\(\d+\))?", re.I)
_CATEGORY = re.compile(r"\b(measured|indicated|inferred)\b", re.I)
_CLASSIFICATION = re.compile(r"(?:JORC\s+)?(?:category|classification|resource classification)", re.I)
_SCOPE_END = re.compile(r"\b(?:(?:non[-\s‐‑–—]+|not\s+(?:an?\s+)?)?JORC|total|measured|indicated|inferred|estimate of)\b|"
                        + _RESOURCE.pattern, re.I)
_SCOPE_AFTER = re.compile(r"(?:mineral resources?(?: estimate)?|resource estimate)\s+for\s+(?:the\s+)?(.+?)\s+(?:as at|effective|reported above)\b", re.I)
_BULK = re.compile(r"\b(?:(?:dry|bulk|whole)[ -]+ore|dry\s+(?:material|tonnes?|tonnage))\b", re.I)
_MATERIAL_METHOD = (r"\btonnages?\s+(?:was|were|is|are|has been|have been)\s+"
                    r"(?:reported|assessed|estimated|calculated)\s+on\s+(?:an?\s+)?")
_DRY_METHOD = re.compile(_MATERIAL_METHOD + r"(?:in[- ]situ\s+)?dry(?:,?\s+in[- ]situ)?\s+basis\b", re.I)
_WET_METHOD = re.compile(_MATERIAL_METHOD + r"wet\s+basis\b", re.I)
_CHEMICAL = re.compile(r"\btotal rare earth oxides?(?:\s*\(TREO\))?\b|\bTREO\s*=\s*La2O3\s*\+\s*CeO2\s*\+", re.I)
_EXCLUDED_OXIDE = re.compile(r"\b(?:TREO|total rare earth oxides?)\s*(?:\(TREO\)\s*)?(?:exclud\w+|minus|[-−])\s*"
                             r"(?:[a-z]{1,2}\d*(?:O\d*)?|cerium|yttrium|scandium)\b", re.I)
_HOLD = re.compile(r"\b(?:scandium|gallium|wet tonnes?|concentrate|recoverable|exclud(?:es?|ing)|\bHM\b)\b", re.I)
_CONTINUATION = re.compile(r"\b(?:continued|continuation|cont\.)\b", re.I)
_CUTOFF_COLUMN = re.compile(r"cut[- ]?off\s*\(\s*(?:TREO\s+(ppm|%)|(ppm|%)\s+TREO)\s*\)", re.I)
_CUTOFF_COMPARISON = re.compile(r"(?P<operator>>=|<=|[≥≤><=]|\bat least|\bat most|\babove|\bbelow|\bgreater than|\bless than)"
                                r"(?:\s+(?:an?|the))?\s*$", re.I)
_CUTOFF_MARKER = re.compile(r"\bcut[- ]?off(?:\s+grade)?\s+(?:(?:of|is|was)\s+)?(?:[:=]\s*)?"
                            r"(?P<operator>>=|<=|[≥≤><=])?\s*(?P<x>[0-9][0-9,.]*)\s*"
                            r"(?P<u>ppm|%|g/t)\s*(?P<b>TREO(?:\s*[-−]\s*CeO2)?|Nb2O5|Ga2O3)\b", re.I)
_CUTOFF_CELL = re.compile(r"(?P<operator>>=|<=|[≥≤><=])?\s*(?P<x>[0-9][0-9,.]*)\Z")
_COMPARISONS = {"greater than": ">", "less than": "<"}
_NO_RESERVE_CONVERSION = re.compile(r"\b(?:(?:not|never)\s+(?:yet\s+)?(?:been\s+)?|yet\s+to\s+be\s+)"
                                    r"converted\s+(?:to|into)\s+"
                                    r"(?:an?\s+)?Ore Reserves?\b", re.I)
_REPORT_FOOTER = re.compile(r"(?P<title>.+?)\s+Page\s+(?P<page>\d+)\s+of\s+(?P<count>\d+)\s*$", re.I)
_SCOPE_ALIAS = re.compile(r"\s[—–]\s+([^—–;]+?)\s+scope\s*$", re.I)
_SCOPE_SUFFIX = re.compile(r"\s+(?:(?:rare earth )?deposit|project)\s*$", re.I)
_CONTAINED_CLAIM = re.compile(r"\b(?:contained\s+TREO|TREO\s+conten(?:t|ts)|TREO\s+tonnes?)\b", re.I)
_NARRATIVE_CONTAINED = re.compile(r"\b(?:comprising|containing)\s+([0-9][0-9,.]*)\s*(kt|t|Mt)\s+TREO\b", re.I)
_MISSING = {"", "-", "–", "—", "N/A", "NA", "NR"}
_MONTH = r"(?:January|February|March|April|May|June|July|August|September|October|November|December)"
_PERIOD = re.compile(rf"\b({_MONTH})\s+(20\d{{2}})\b", re.I)
_DATE_PERIOD_CHANGE = re.compile(rf"\bfrom\s+(\d{{1,2}}\s+{_MONTH}\s+20\d{{2}})\s+to\s+"
                                 rf"(\d{{1,2}}\s+{_MONTH}\s+20\d{{2}})(?:\d(?=[.\s]|$))?\b", re.I)
_MARKED_TREO = re.compile(r"\*\s*TREO\s*=\s*total rare earth oxides?\b", re.I)
_TOTAL_EXTENT = re.compile(r"\b(?:covers|represents|includes|encompasses|comprises)\s+(?:all of\s+)?(?:the\s+)?"
                           r"(?:entire|whole)\s+(?:[\w'-]+\s+){0,3}(?:project|deposit)\b", re.I)
_REPORT_GRADE_PHRASE = re.compile(GRADE_PHRASE.pattern.replace("|@)", "|of|@)", 1), GRADE_PHRASE.flags)
_MATCHED_TABLE = "NAMED_ESTIMATE_TABLE_AND_DATE_OR_ROW_VALUES"
_MATCHED_PERIOD = "NAMED_RESOURCE_REPORTING_PERIOD_AND_ROW_VALUES"
_MATCHED_FOOTNOTE = "UNIQUE_TABLE_TREO_FOOTNOTE_MARKER"
_CONTEXT_RELATIONS = frozenset({_MATCHED_TABLE, _MATCHED_PERIOD, _MATCHED_FOOTNOTE})
_CONTEXT_ROLES = {"effective_date": "estimate_effective_date", "material_basis": "estimate_material_basis",
                  "denominator_basis": "estimate_denominator_basis", "chemical_basis": "estimate_chemical_basis",
                  "cutoff_grade": "estimate_cutoff", "scope_coverage": "estimate_extent"}


def _effective_dates(texts):
    result = set()
    for text in texts:
        for match in ESTIMATE_DATE.finditer(text):
            literal = match[1]
            # A cited study or publication date does not establish the estimate date.
            if re.match(r"dated\b", match[0], re.I):
                continue
            try:
                if "-" in literal:
                    result.add(date.fromisoformat(literal).isoformat())
                else:
                    day, month, year = literal.split()
                    result.add(date(int(year), MONTHS.index(month[:3].lower()) + 1, int(day)).isoformat())
            except ValueError:
                continue
    return result


def _cutoff(texts):
    declarations = {}
    for text in texts:
        for m in [*CUTOFF.finditer(text), *_CUTOFF_MARKER.finditer(text)]:
            if m.re is CUTOFF:
                leading = _CUTOFF_COMPARISON.search(text[:m.start()])
                operator = leading["operator"].casefold() if leading else None
                original = text[leading.start():m.end()] if leading else m[0]
            else:
                operator = m["operator"]
                leading = _CUTOFF_COMPARISON.search(text[:m.start()])
                if leading and not operator:
                    operator = leading["operator"].casefold()
                original = text[leading.start():m.end()] if leading else m[0]
            declared = {"value": m["x"], "unit": m["u"].lower(), "basis": m["b"].upper(),
                        "operator": _COMPARISONS.get(operator, operator), "text": original}
            if normalized := normalize_cutoff(declared):
                declarations.setdefault(cutoff_signature(normalized), declared)
    return declarations


def _estimate_dates_in_context(quote, relation):
    dates = _effective_dates((quote,))
    if relation == _MATCHED_PERIOD:
        periods = list(_DATE_PERIOD_CHANGE.finditer(quote))
        if len(periods) == 1:
            first, last = (_effective_dates(("effective " + literal,)) for literal in periods[0].groups())
            if len(first) == len(last) == 1 and next(iter(first)) < next(iter(last)):
                dates |= last
    return dates


def _quote_span(start, end):
    return {"view": "MUPDF_NORMALIZED_SOURCE_QUOTE", "scope": "QUOTE", "start": start, "end": end, "quote_start": 0}


def _resource_context_anchor(role, row, number, box, quote, relation, *, start=0, end=None):
    return _anchors(role, {**row, "physical_page": number}, quote, bbox=box, locator=relation,
                    text_span=_quote_span(start, len(quote) if end is None else end))


def _scope_is_named(scope, quote):
    if not scope:
        return False
    head, _, rest = scope.partition(",")
    names = [scope_stem(head)]
    if rest:
        components = re.sub(r"\s+deposits?\s*$", "", rest, flags=re.I)
        names.extend(part.strip() for part in re.split(r"\s+and\s+|,", components, flags=re.I))
    return bool(all(name and re.search(r"(?<!\w)" + re.escape(name) + r"(?!\w)", quote, re.I) for name in names))


def _documented_extent(scope, quote):
    if match := _TOTAL_EXTENT.search(quote):
        return match
    if not scope or "," not in scope or not _scope_is_named(scope, quote):
        return None
    # A report can describe the named project's aggregate by enumerating
    # every constituent deposit explicitly in its matching table assertion.
    parent = scope_stem(scope.partition(",")[0])
    return re.search(r"\bmineral resource estimate\b[^.!?;]{0,22}\bof\s+(?:the\s+)?" + re.escape(parent)
                     + r"\s+project\s+(?:now\s+)?(?:comprises|totals)\b", quote, re.I)


def _row_values_match(quote, located):
    if any(len(located[field]) != 1 for field in ("ore_mt", "grade")):
        return False
    factors = {"ppm": 1, "%": 10_000, "t": 1, "kt": 1_000, "mt": 1_000_000,
               "million tonnes": 1_000_000, "m tonnes": 1_000_000}

    def agrees(printed, unit, witness, witness_unit):
        value, stated = scalar_decimal(printed, unit), scalar_decimal(witness, witness_unit)
        factor = factors.get(unit.casefold())
        if value is None or stated is None or factor is None:
            return False
        half_place = Decimal(5).scaleb(value.as_tuple().exponent - 1)
        return abs(stated * factors[witness_unit.casefold()] - value * factor) <= half_place * factor

    phrases = list(_REPORT_GRADE_PHRASE.finditer(quote))
    if len(phrases) != 1:
        return False
    phrase = phrases[0]
    return all(agrees(located[field][0][0]["text"], located[field][0][1], phrase[name], phrase[f"{name}_unit"])
               for field, name in (("ore_mt", "mass"), ("grade", "grade")))


def _table_context_references(page, reported_table, scope, declared_dates, caption, blocks, supporting_pages, located,
                              table_label_pages, *, project, registry):
    """Require a located connection to the estimate. Retrieval rank cannot establish identity."""
    if not reported_table or not scope:
        return
    period_matches = {(int(match[2]), MONTHS.index(match[1][:3].lower()) + 1) for match in _PERIOD.finditer(caption)}
    pages = {**supporting_pages, page: blocks}
    duplicate_label = bool(set(table_label_pages.get(reported_table, ())) - {page}) or any(
        number != page and any((match := CAPTION.match(quote)) and match[1] == reported_table
                               and not _TABLE_PROSE.match(quote) and _RESOURCE.search(quote) for _, quote in page_blocks)
        for number, page_blocks in pages.items())
    for number, page_blocks in sorted(pages.items()):
        named_reporting_period = any(_scope_is_named(scope, quote) and _RESOURCE.search(quote) for _, quote in page_blocks)
        for box, quote in page_blocks:
            if not 0 < len(quote) <= 1800 or (CAPTION.match(quote) and not _TABLE_PROSE.match(quote)):
                continue
            names, dates = table_numbers(quote), _effective_dates((quote,))
            if dates and declared_dates and dates.isdisjoint(declared_dates):
                continue
            same_date = bool(dates and dates == declared_dates and len(dates) == 1)
            same_quantities = _row_values_match(quote, located)
            if (_scope_is_named(scope, quote) and _RESOURCE.search(quote) and names == {reported_table}
                    and not duplicate_label and (same_date or same_quantities)):
                # A block can contain independent prose sentences. A named
                # table next to another project's numeric statement does not
                # give the target table that project's date or basis.
                if len(dates) <= 1 and all(item['entity_id'] == project for item in _matches(quote, registry)):
                    yield number, box, quote, _MATCHED_TABLE
            elif (number != page and not names and not duplicate_label and named_reporting_period and len(period_matches) == 1
                  and _RESOURCE.search(quote) and not RISKY.search(quote) and same_quantities):
                dates = _estimate_dates_in_context(quote, _MATCHED_PERIOD)
                if (len(dates) == 1 and any((d.year, d.month) in period_matches for d in map(date.fromisoformat, dates))
                        and all(item['entity_id'] == project for item in _matches(quote, registry))):
                    yield number, box, quote, _MATCHED_PERIOD


def _nearby_marked_treo(page, table, tables, blocks, header_text):
    if not re.search(r"\bTREO\s*\*", header_text, re.I):
        return ()
    found = [(page, box, quote, _MATCHED_FOOTNOTE) for box, quote in blocks if _MARKED_TREO.search(quote)
             and table["bbox"][3] - 25 <= box[1] <= table["bbox"][3] + 28
             and not any(other is not table and other["bbox"][1] < box[3] and other["bbox"][3] > box[1]
                         for other in tables)]
    return tuple(found) if len(found) == 1 else ()


def _supporting_blocks(caption, table, tables, blocks):
    """Use an explicitly referenced description or immediate unit-definition note."""
    table_number = CAPTION.match(caption)[1]
    bounds = table["bbox"]
    next_table_top = min((other["bbox"][1] for other in tables if other["bbox"][1] > bounds[3]), default=float("inf"))
    reference = re.compile(r"\bTable\s+" + re.escape(table_number) + r"(?![\w.\-])", re.I)
    context, notes = [], []
    for box, text in blocks:
        if (not bounds[0] <= (box[0] + box[2]) / 2 <= bounds[2]
                or CAPTION.match(text) and not _TABLE_PROSE.match(text)):
            continue
        if 0 <= bounds[1] - box[3] <= 42 and reference.search(text) and _RESOURCE.search(text) and not RISKY.search(text):
            context.append((box, text))
        if (0 <= box[1] - bounds[3] <= 28 and box[3] < next_table_top and len(text) <= 700
                and box[3] - box[1] <= 58 and (_CHEMICAL.search(text) or _EXCLUDED_OXIDE.search(text)
                                                or _BULK.search(text) or _DRY_METHOD.search(text) or _WET_METHOD.search(text))):
            notes.append((box, text))
    return context, notes


def _registered_scope_aliases(registry):
    """Recognize exact named scopes already declared in the existing Project registry."""
    return [dict(project, aliases=sorted(set(project.get("aliases", ())) | ({alias[1]} if alias else set())))
            for project in registry if (alias := _SCOPE_ALIAS.search(project.get("name", ""))) or project.get("aliases")]


def _scope(caption, registry):
    title = CAPTION.sub("", caption, count=1)
    explicit = _SCOPE_AFTER.match(title)
    marker = _SCOPE_END.search(title)
    label = (explicit[1] if explicit else title[:marker.start()] if marker else "").strip(" :-–—,;")
    hits = _matches(label, registry) if label else []
    if len(hits) != 1 or {p["entity_id"] for p in _matches(caption, registry)} != {hits[0]["entity_id"]}:
        return None, label or None, False
    plain = _SCOPE_SUFFIX.sub("", label).casefold()
    declared = {name.casefold() for name in (*hits[0]["aliases"], hits[0].get("name", ""))}
    return hits[0]["entity_id"], label, label.casefold() in declared or plain in declared


def _report_title(page, page_blocks):
    matches = {m["title"] for _, text in page_blocks if (m := _REPORT_FOOTER.fullmatch(text))
               and int(m["page"]) == page and int(m["count"]) >= page and _RESOURCE.search(m["title"])}
    return next(iter(matches)) if len(matches) == 1 else None


def _related_report_pages(page, blocks, supporting_pages, registry, project):
    title = _report_title(page, blocks)
    if not title or {row["entity_id"] for row in _matches(title, registry)} != {project}:
        return {}
    return {number: other_blocks for number, other_blocks in sorted(supporting_pages.items())
            if number != page and _report_title(number, other_blocks) == title}


def _narrative_values(text, scope, located, cutoff):
    """Link a current estimate paragraph to the complete physical table row."""
    if not scope or not cutoff or not re.match(r"(?:the\s+)?" + re.escape(scope_stem(scope)) +
            r"\s+(?:mineral\s+)?resources?(?:\s+estimate)?\s+(?:is|are)\s+(?:now|currently)\s+"
            r"(?:estimated|reported)\s+at\b", text, re.I):
        return False
    factors = {"ppm": 1, "%": 10000, "t": 1, "kt": 1000, "mt": 10**6, "million tonnes": 10**6,
               "m tonnes": 10**6}

    def value(token, unit):
        unit = unit.casefold()
        number = scalar_decimal(token, unit)
        return number * factors[unit] if number is not None and unit in factors else None

    # The next sentence may introduce a project-wide or different estimate.
    statement = text.split(". ", 1)[0]
    declared = _cutoff([statement])
    cutoff_key = cutoff_signature(normalize_cutoff(cutoff))
    ore_grade, contained = GRADE_PHRASE.search(statement), _NARRATIVE_CONTAINED.search(statement)
    if (not ore_grade or not contained or not cutoff_key or not declared
            or any(key not in {cutoff_key, (*cutoff_key[:2], "DECLARED_CUTOFF")} for key in declared)):
        return False
    quantities = (value(ore_grade["mass"], ore_grade["mass_unit"]), value(ore_grade["grade"], ore_grade["grade_unit"]),
                  value(*contained.groups()))
    if None in quantities or any(len(located[variable]) != 1 for variable in _VARIABLES):
        return False
    return quantities == tuple(value(matches[0][0]["text"], matches[0][1]) for matches in located.values())


def _jorc_section_proofs(page, report_pages, scope, effective, located, cutoff):
    """Find one named dated section linked by a current-estimate value witness."""
    candidates = [(number, box, text) for number, blocks in report_pages.items() if number < page
                  for box, text in blocks]
    sections = [entry for entry in candidates if section_matches(entry[2], scope, effective)]
    if len(sections) != 1:
        return None, None, None
    section = sections[0]
    start = (section[0], section[1][3])
    end = min(((number, box[1]) for number, box, text in candidates if estimate_heading(text)
               and (number, box[1]) >= start), default=(page, 0))
    links = [(number, box, text) for number, box, text in candidates if start <= (number, box[1]) < end
             and _narrative_values(text, scope, located, cutoff)]
    return (section, links[0], end) if len(links) == 1 else (None, None, None)


def _adjacent_estimate_note(box, table, tables):
    midpoint = (box[0] + box[2]) / 2
    neighbors = [item for item in tables if item["bbox"][0] <= midpoint <= item["bbox"][2]
                 and (0 <= item["bbox"][1] - box[3] <= 42 or 0 <= box[1] - item["bbox"][3] <= 42)]
    return len(neighbors) == 1 and neighbors[0] is table


def _jorc_evidence(source, registry, page, table, tables, row, subject, caption_entry, active_section, blocks, report_pages,
                   section_context, bound_context):
    witnesses = []
    section_proof, estimate_proof, next_section = section_context

    def collect(number, box, quote, origin, **location):
        witnesses.append({"source_sha256": source["sha256"], "source_id": source["key"],
                          "physical_page": number, "bbox": box, "quote": quote, "origin": origin, **location})

    if caption_entry:
        collect(page, *caption_entry, "SCOPE_CAPTION", table=table["table_index"])
    if active_section:
        collect(page, active_section["bbox"], active_section["text"], "NATIVE_SECTION", table=table["table_index"],
                row=active_section["row"], column=active_section["column"])
    for box, quote in blocks:
        if ((box, quote) != caption_entry and
                (not active_section or (box, quote) != (active_section["bbox"], active_section["text"]))):
            origin = "ADJACENT_ESTIMATE_NOTE" if _adjacent_estimate_note(box, table, tables) else "SAME_PAGE"
            collect(page, box, quote, origin)
    bound_locations = {(number, tuple(box), quote) for number, box, quote, relation in bound_context
                       if number != page and relation == _MATCHED_TABLE}
    for number, box, quote in sorted(bound_locations):
        collect(number, list(box), quote, "BOUND_ESTIMATE_CONTEXT")
    for number, page_blocks in report_pages.items():
        for box, quote in page_blocks:
            if (number, tuple(box), quote) in bound_locations:
                continue
            origin = ("MATCHED_ESTIMATE_SECTION" if section_proof and number == section_proof[0]
                      and section_proof[1][3] <= box[1] and (number, box[1]) < next_section
                      and not _REPORT_FOOTER.fullmatch(quote) else "REPORT_CONTEXT")
            collect(number, box, quote, origin)

    assessment = assess_jorc(witnesses, subject, projects_in=lambda text: {p["entity_id"] for p in _matches(text, registry)},
                             dates_in=lambda text: _effective_dates([text]))
    anchors = [_anchors(SCOPE_TO_ROLE[item["applicability"]], {**row, "physical_page": item["physical_page"]}, item["quote"],
                        bbox=item["bbox"], table_index=item.get("table"), row=item.get("row"), column=item.get("column"),
                        locator=item["binding"], text_span={"view": "MUPDF_NORMALIZED_SOURCE_QUOTE", "scope": "QUOTE",
                       "start": item["start"], "end": item["end"], "quote_start": 0}) for item in assessment["evidence"]]
    if section_proof:
        for binding, (number, box, quote) in (("jorc_section_scope", section_proof), ("jorc_estimate_scope", estimate_proof)):
            anchors.append(_anchors(binding, {**row, "physical_page": number}, quote, bbox=box))
        assessment["scope_proof"] = [{"role": anchor["field"], **anchor} for anchor in anchors[-2:]]
    return assessment, anchors


def _column_parts(cell, headers):
    pieces = located_column_headers(cell, headers)
    text = clean(" ".join(dict.fromkeys(piece["text"] for piece in pieces)))
    return text, pieces


def _cell_anchor(field, row, table, cell, **extra):
    return _anchors(field, row, cell["text"], table_index=table["table_index"], row=cell["row"],
                    column=cell["column"], bbox=cell["bbox"], **extra)


def _typed(source, row, table, cell, quantity, unit, pieces, context, witnesses):
    token = cell["text"].strip()
    spans = numeric_token_spans(token, token, unit)
    if spans != ((0, len(token)),):
        return None, "RESOURCE_TOKEN_UNREADABLE_OR_UNIT_CONFLICT"
    scalar = scalar_decimal(token, unit)
    state = "NUMBER" if scalar is not None else (
        "BOUND" if re.match(r"[<>≤≥≈~]", token) else "RANGE")
    first = _cell_anchor("token", row, table, cell, text_span={
        "view": "MUPDF_NATIVE_TABLE_CELL", "scope": "QUOTE", "start": 0, "end": len(token), "quote_start": 0,
    })
    anchor_list = [first, *column_header_anchors(row, table, pieces, unit), *witnesses]
    if not any(anchor["field"] == "unit" for anchor in anchor_list):
        return None, "NATIVE_UNIT_WITNESS_MISSING"
    identity = digest(["resource-cell-identity-v1", source["sha256"], row["physical_page"], table["table_index"],
                       cell["row"], cell["column"], quantity])
    observation = raw_from_candidate({"observation_id": identity, **row,
                                      "quantity_kind": "RESOURCE", "context": context, "anchors": anchor_list,
                                      "native": {"quantity": quantity, "token": token, "unit": unit, "token_state": state}},
                                     source_id=source["key"], extractor_version=VERSION, metadata=source)
    issue = value_evidence_issue(observation, observation.evidence_anchors)
    if scalar is None:
        issue = issue or "RESOURCE_NOT_SCALAR"
    elif scalar < 0 or quantity == "grade" and scalar > (100 if unit == "%" else 1_000_000):
        issue = issue or "RESOURCE_VALUE_OUT_OF_RANGE"
    return observation, issue


def _bound_field_witnesses(row, scope, bound_context):
    """Record each field from its unmerged physical PDF block."""
    identities, fields, dates, cutoffs = [], {}, set(), {}
    wet, excluded = False, False
    for number, bbox, quote, relation in bound_context:
        identities.append(_resource_context_anchor("estimate_identity_reference", row, number, bbox, quote, relation))

        def record(field, match=None):
            start, end = match.span() if match else (0, len(quote))
            anchor = _resource_context_anchor(_CONTEXT_ROLES[field], row, number, bbox, quote, relation, start=start, end=end)
            fields.setdefault(field, []).append(anchor)

        if relation != _MATCHED_FOOTNOTE:
            if additions := _estimate_dates_in_context(quote, relation):
                dates |= additions
                record("effective_date")
            if relation == _MATCHED_TABLE:
                if additions := _cutoff((quote,)):
                    cutoffs.update(additions)
                    record("cutoff_grade")
                if match := _DRY_METHOD.search(quote):
                    record("material_basis", match)
                    record("denominator_basis", match)
                wet |= bool(_WET_METHOD.search(quote))
                if match := _documented_extent(scope, quote):
                    record("scope_coverage", match)
        if match := (_MARKED_TREO if relation == _MATCHED_FOOTNOTE else _CHEMICAL).search(quote):
            record("chemical_basis", match)
        excluded |= bool(_EXCLUDED_OXIDE.search(quote))
    return identities, fields, dates, cutoffs, wet, excluded


def verified_context_anchors(observations):
    """Verify the same-estimate linkage for typed contextual field witnesses."""
    first = observations[0]
    source = (first.evidence.sha256, first.evidence.source_id)
    anchors = [anchor for anchor in first.evidence_anchors if (anchor.sha256, anchor.source_id) == source
               and anchor.page and anchor.bbox and anchor.quote and anchor.text_span]
    props = dict(first.context.conditions)
    caption = next((anchor.quote for anchor in first.evidence_anchors if anchor.role == "scope"
                    and (anchor.sha256, anchor.page, anchor.table) == (source[0], first.evidence.page, first.evidence.table)), "")
    scope_dates = _effective_dates((caption,))
    table_label = props.get("reported_table_label")
    located = {field: [] for field in ("ore_mt", "grade")}
    for item in observations:
        if item.variable in located:
            located[item.variable].append(({"text": item.original_value}, item.original_unit, ()))

    def key(anchor):
        return anchor.page, anchor.bbox, anchor.quote, anchor.locator

    def bound(anchor):
        relation = anchor.locator
        if relation == _MATCHED_TABLE:
            dates = _effective_dates((anchor.quote,))
            if not table_label or table_numbers(anchor.quote) != {table_label} or not _scope_is_named(first.scope_id, anchor.quote):
                return False
            return bool(dates and scope_dates == dates and len(dates) == 1 or _row_values_match(anchor.quote, located))
        if relation == _MATCHED_PERIOD:
            dates = _estimate_dates_in_context(anchor.quote, relation)
            periods = {(int(match[2]), MONTHS.index(match[1][:3].lower()) + 1) for match in _PERIOD.finditer(caption)}
            return (len(dates) == len(periods) == 1
                    and any((day.year, day.month) in periods for day in map(date.fromisoformat, dates))
                    and _row_values_match(anchor.quote, located)
                    and any(witness.role == "estimate_report_scope" and witness.page == anchor.page
                            and _scope_is_named(first.scope_id, witness.quote) and _RESOURCE.search(witness.quote)
                            for witness in anchors))
        if relation == _MATCHED_FOOTNOTE:
            return (anchor.page == first.evidence.page and bool(_MARKED_TREO.search(anchor.quote))
                    and any(item.variable == "grade" and any(header.role == "unit" and "TREO*" in header.quote.upper().replace(" ", "")
                            for header in item.evidence_anchors if header.quote) for item in observations))
        return False

    identity = {key(anchor) for anchor in anchors if anchor.role == "estimate_identity_reference"
                and anchor.locator in _CONTEXT_RELATIONS and bound(anchor)}
    selected = [anchor for anchor in anchors if anchor.role in _CONTEXT_ROLES.values() and key(anchor) in identity]
    # All observation tokens must carry the same proof set for this estimate.
    if any(not set(selected).issubset(set(item.evidence_anchors)) for item in observations):
        return ()
    return tuple(selected)


def _table_rows(source, registry, page, table, tables, blocks, supporting_pages, method_pages, table_label_pages):
    native = cells(table)
    labels = [cell for cell in native if _CLASSIFIED_ROW.fullmatch(clean(cell["text"])) or _TOTAL.fullmatch(clean(cell["text"]))]
    if not labels:
        return
    first_row = min(cell["row"] for cell in labels)
    # Full-width section titles identify sub-estimates, never act as units.
    table_width = table["bbox"][2] - table["bbox"][0]
    sections = [cell for cell in native if _RESOURCE.search(cell["text"])
                and cell["bbox"][2] - cell["bbox"][0] >= .8 * table_width]
    headers = [cell for cell in native if cell["row"] < first_row and cell not in sections]
    # "Table 2 presents ..." is a reference in prose. It can bind a following
    # proposition but must not compete with the table's structural title.
    caption_entry = page_table_caption(tables, table, [(box, text) for box, text in blocks if not _TABLE_PROSE.match(text)])
    caption = caption_entry[1] if caption_entry else ""
    if not (_RESOURCE.search(caption) or any(_CLASSIFICATION.fullmatch(clean(cell["text"])) for cell in headers)
            and any(_header_unit(_column_parts(cell, headers)[0], "grade", native=True)
                    for cell in native if cell["row"] >= first_row)):
        return
    context_blocks, notes = _supporting_blocks(caption, table, tables, blocks) if caption_entry else ([], [])
    texts = [caption, *(text for _, text in context_blocks)]
    project, scope, extent_bound = _scope(caption, registry)
    report_pages = _related_report_pages(page, blocks, supporting_pages, registry, project) if project else {}
    external = [(number, box, text) for number, related in report_pages.items() for box, text in related
                if number in method_pages and (_DRY_METHOD.search(text) or _WET_METHOD.search(text))]
    declared_dates = _effective_dates((caption,))
    declared_cutoffs = _cutoff((caption,))
    reported_table = CAPTION.match(caption)[1] if caption_entry else None
    unique_on_page = bool(reported_table and sum(1 for _, quote in blocks if (match := CAPTION.match(quote))
                          and match[1] == reported_table and not _TABLE_PROSE.match(quote)) == 1)
    table_issues = []
    declared_resource = bool(caption_entry and _RESOURCE.search(caption))
    material_caption = _NO_RESERVE_CONVERSION.sub("", caption)
    incompatible = bool(RISKY.search(material_caption) or _HOLD.search(material_caption))
    if not declared_resource:
        table_issues.append("RESOURCE_TABLE_CAPTION_UNRESOLVED")
    if incompatible:
        table_issues.append("RESOURCE_ESTIMATE_MATERIAL_OR_STANCE_INCOMPATIBLE")
    if table.get("continuation_candidate") or _CONTINUATION.search(caption):
        table_issues.append("CONTINUATION_SCOPE_UNCONFIRMED")
    if not project or source.get("project_binding_status") == "UNRESOLVED_DISTINCT_PROJECT":
        table_issues.append("PROJECT_SCOPE_UNRESOLVED")
    elif project not in (source.get("summary_project_ids") or ()):
        table_issues.append("SOURCE_PROJECT_NOT_REGISTERED_FOR_ADMISSION")
    header_text = " | ".join(clean(cell["text"]) for cell in headers)
    scoped_notes = [text for _, text in notes]
    local_bulk = bool(_BULK.search(header_text) or any(_BULK.search(text) or _DRY_METHOD.search(text) for text in scoped_notes))
    local_wet = any(_WET_METHOD.search(text) for text in scoped_notes)
    local_basis = bool(_CHEMICAL.search(header_text) or any(_CHEMICAL.search(text) for text in texts + scoped_notes))
    local_exclusion = any(_EXCLUDED_OXIDE.search(text) for text in [header_text, *texts, *scoped_notes])
    marked_treo = _nearby_marked_treo(page, table, tables, blocks, header_text)
    totals = [cell for cell in labels if _TOTAL.fullmatch(clean(cell["text"]))]
    for index in sorted({cell["row"] for cell in labels}):
        row_labels = [cell for cell in labels if cell["row"] == index]
        row = {"source_sha256": source["sha256"], "physical_page": page, "project_id": project}
        row_issues = list(table_issues)
        is_total = len(row_labels) == 1 and row_labels[0] in totals
        complete = is_total and len(totals) == 1 or not totals and len(labels) == 1
        active_section = next((cell for cell in reversed(sections) if cell["row"] < index), None)
        if active_section:
            title = active_section["text"]
            section_ids = {hit["entity_id"] for hit in _matches(title, registry)}
            complete &= bool(re.search(r"\btotal\b", title, re.I) and section_ids == {project}
                             and not re.search(r"\b(?:open pit|underground|stockpile|subset)\b", title, re.I))
        if not complete:
            row_issues.append("RESOURCE_COMPONENT_OR_COMPETING_TOTALS")
            row_issues.append("RESOURCE_COMPETING_TOTALS_UNRESOLVED" if any(cell in totals for cell in row_labels)
                              else "RESOURCE_COMPONENT_EXCLUDED")
        row_role = ("ESTIMATE_TOTAL" if is_total else "SOLE_CLASSIFIED_ESTIMATE") if complete else (
            "COMPETING_TOTAL" if any(cell in totals for cell in row_labels) else "COMPONENT")
        first_section_row = active_section["row"] if active_section else -1
        category_cells = ([cell for cell in labels if first_section_row < cell["row"] < index] if is_total else row_labels)
        categories = {match[0].upper() for cell in category_cells for match in _CATEGORY.finditer(cell["text"])}
        if is_total and active_section is None:
            categories |= {match[0].upper() for match in _CATEGORY.finditer(caption)}
        category = "_".join(item for item in ("MEASURED", "INDICATED", "INFERRED") if item in categories)
        if not category:
            row_issues.append("RESOURCE_CLASSIFICATION_UNRESOLVED")
        elif is_total:
            category += "_TOTAL"
        located = {quantity: [] for quantity in _VARIABLES}
        cutoffs = dict(declared_cutoffs)
        witnesses = [_cell_anchor("row", row, table, cell) for cell in row_labels]
        if is_total:
            witnesses.extend(_cell_anchor("classification", row, table, cell) for cell in category_cells)
        if caption_entry:
            witnesses.append(_anchors("scope", row, caption, table_index=table["table_index"], bbox=caption_entry[0]))
        if active_section:
            witnesses.append(_cell_anchor("resource_section", row, table, active_section))
        for box, text in [*context_blocks, *notes]:
            witnesses.append(_anchors("estimate_reference", row, text, table_index=table["table_index"], bbox=box))
        for cell in (cell for cell in native if cell["row"] == index and cell not in row_labels):
            header, pieces = _column_parts(cell, headers)
            for quantity in _VARIABLES:
                unit = _header_unit(header, quantity, native=True)
                if unit:
                    located[quantity].append((cell, unit, pieces))
            if _CONTAINED_CLAIM.search(header) and not _header_unit(header, "contained_treo_kt"):
                row_issues.append("RESOURCE_CONTAINED_UNIT_OR_BASIS_UNRESOLVED")
            cutoff_column = _CUTOFF_COLUMN.fullmatch(header)
            if cutoff_column and (number := _CUTOFF_CELL.fullmatch(cell["text"].strip())):
                cutoff_unit = cutoff_column[1] or cutoff_column[2]
                declaration = {"value": number["x"], "unit": cutoff_unit.lower(), "basis": "TREO",
                               "operator": number["operator"], "text": cell["text"]}
                if normalized_cutoff := normalize_cutoff(declaration):
                    cutoffs.setdefault(cutoff_signature(normalized_cutoff), declaration)
                witnesses.append(_cell_anchor("cutoff_value", row, table, cell))
                witnesses.extend({**anchor, "field": "cutoff_header"} for anchor in
                                 column_header_anchors(row, table, pieces, cutoff_unit))
        # Keep all target evidence located, and admit cross-page context only
        # after validating table identity, not from the retrieved page alone.
        bound_context = [*marked_treo]
        if unique_on_page and complete:
            bound_context.extend(_table_context_references(page, reported_table, scope, declared_dates, caption,
                                                           blocks, supporting_pages, located, table_label_pages,
                                                           project=project, registry=registry))
        identities, field_evidence, bound_dates, bound_cutoffs, bound_wet, bound_exclusion = _bound_field_witnesses(row, scope, bound_context)
        witnesses.extend(identities)
        for number in sorted({number for number, _, _, relation in bound_context if relation == _MATCHED_PERIOD}):
            witnesses.extend(_resource_context_anchor("estimate_report_scope", row, number, box, quote, _MATCHED_PERIOD)
                             for box, quote in supporting_pages[number]
                             if _scope_is_named(scope, quote) and _RESOURCE.search(quote))
        witnesses.extend(anchor for anchors in field_evidence.values() for anchor in anchors)
        effective_dates = declared_dates | bound_dates
        effective = next(iter(effective_dates)) if len(effective_dates) == 1 else None
        if not effective:
            row_issues.append("RESOURCE_ESTIMATE_DATE_CONFLICT" if effective_dates else "RESOURCE_ESTIMATE_DATE_UNRESOLVED")
        basis = (local_basis or "chemical_basis" in field_evidence) and not (local_exclusion or bound_exclusion)
        if local_exclusion or bound_exclusion:
            row_issues.append("TREO_EXCLUDED_OXIDE_BASIS")
        if not basis:
            row_issues.append("TREO_DEFINITION_UNRESOLVED")
        scope_bound = extent_bound or (complete and "scope_coverage" in field_evidence)
        if project and project in (source.get("summary_project_ids") or ()) and not scope_bound:
            row_issues.append("PROJECT_SCOPE_EXTENT_UNRESOLVED")
        prior_cutoffs = set(cutoffs)
        for signature, declaration in bound_cutoffs.items():
            cutoffs.setdefault(signature, declaration)
        cutoff = next(iter(cutoffs.values())) if len(cutoffs) == 1 else None
        if cutoff and cutoff["basis"] != "TREO":
            cutoff = None
        if cutoff is None:
            row_issues.append("RESOURCE_CUTOFF_UNRESOLVED" if not cutoffs else "RESOURCE_CUTOFF_BASIS_OR_VALUE_CONFLICT")
        section_context = _jorc_section_proofs(page, report_pages, scope, effective, located, cutoff)
        # A footer alone identifies a report, which can contain several
        # estimates. Method text for that report additionally needs the
        # named estimate section and its exact corroborating resource row.
        external_method = external if section_context[0] else ()
        for number, box, text in external_method:
            witnesses.append(_anchors("estimate_reference", {**row, "physical_page": number}, text, bbox=box,
                                      locator="SAME_NAMED_REPORT_AND_MATCHED_ESTIMATE_SECTION"))
        report_bulk = any(_DRY_METHOD.search(text) for _, _, text in external_method)
        report_wet = any(_WET_METHOD.search(text) for _, _, text in external_method)
        bulk = ((local_bulk or report_bulk or "material_basis" in field_evidence)
                and not (local_wet or bound_wet or report_wet or _HOLD.search(header_text)))
        if not bulk:
            row_issues.append("DRY_BULK_ORE_BASIS_UNRESOLVED")
        estimate = digest(["source-estimate-v1", source["sha256"], page, table["table_index"], project, scope, effective])
        statement = digest(["source-statement-v1", estimate, index])
        subject = {"project_id": project, "scope_id": scope, "estimate_id": estimate, "statement_id": statement,
                   "effective_date": effective, "physical_page": page, "table": table["table_index"], "row": index,
                   "reported_table_label": reported_table, "reported_table_unique_on_page": unique_on_page}
        jorc, jorc_anchors = _jorc_evidence(source, registry, page, table, tables, row, subject, caption_entry, active_section, blocks,
                                           report_pages, section_context, bound_context)
        if jorc["reason"]:
            row_issues.append(jorc["reason"])
        witnesses.extend(jorc_anchors)
        context = {"scope": scope, "statement_id": statement, "estimate_id": estimate, "effective_date": effective,
                   "category": category or None, "resource_type": "MINERAL_RESOURCE" if declared_resource and not incompatible else None,
                   "reporting_standard": "JORC" if jorc["status"] == "AFFIRMED" else None,
                   "jorc_status": jorc["status"], "jorc_rule_version": JORC_VERSION,
                   "scope_coverage": "PROJECT_TOTAL" if complete and scope_bound else "RESOURCE_COMPONENT" if not complete else None,
                   "cutoff_grade": cutoff,
                   "basis": "TREO" if basis else None, "material_basis": "RESOURCE_BULK_ORE" if bulk else None,
                   "denominator_basis": "RESOURCE_BULK_ORE_MASS" if bulk else None,
                   "available_date": source.get("available_date"), "definition_witness": VERSION,
                   "reported_table_label": reported_table,
                   "reported_table_unique_on_page": str(unique_on_page).lower()}
        new_fields = {field: value for field, value, prior in (
            ("effective_date", effective, declared_dates), ("cutoff_grade", cutoff, prior_cutoffs),
            ("material_basis", context["material_basis"], local_bulk),
            ("denominator_basis", context["denominator_basis"], local_bulk),
            ("chemical_basis", context["basis"], local_basis), ("scope_coverage", context["scope_coverage"], extent_bound),
        ) if value and not prior and field in field_evidence and complete}
        gains = {field: {"value": value, "decision": "BOUND_SAME_ESTIMATE", "evidence": field_evidence[field]}
                 for field, value in new_fields.items()}
        observations = []
        for quantity in _VARIABLES:
            matches = [entry for entry in located[quantity] if entry[0]["text"].strip() not in _MISSING]
            if len(matches) != 1:
                if matches or quantity != "contained_treo_kt":
                    row_issues.append(f"RESOURCE_COLUMN_{'AMBIGUOUS' if matches else 'UNBOUND'}:{quantity}")
                continue
            cell, unit, pieces = matches[0]
            observation, issue = _typed(source, row, table, cell, quantity, unit, pieces, context, witnesses)
            if issue:
                row_issues.append(f"{issue}:{quantity}")
            if observation is not None:
                observations.append(observation)
        yield {"candidate_id": statement, "physical_page": page, "table": table["table_index"], "row": index,
               "project_id": project, "observations": tuple(observations), "issues": tuple(sorted(set(row_issues))),
               "jorc_assessment": jorc, "row_role": row_role, "context_field_gains": gains}


def candidates_on_page(source, registry, physical_page, blocks, tables, *, supporting_pages=None, method_pages=None,
                       table_label_pages=None):
    """Visit native rows and keep every disposition, including unusable components."""
    registry = _registered_scope_aliases(registry)
    supporting_pages = supporting_pages or {}
    table_label_pages = table_label_pages or {}
    if method_pages is None:
        method_pages = supporting_pages.keys()
    return tuple(candidate for table in tables
                 for candidate in _table_rows(source, registry, physical_page, table, tables, blocks, supporting_pages, method_pages,
                                              table_label_pages))


def _positioned_value_issues(candidate, words):
    """Compare independent positioned words inside the same native value rectangle."""
    for observation in candidate["observations"]:
        left, top, right, bottom = observation.evidence.bbox
        located = [part for part in words if left < (part[0] + part[2]) / 2 < right
                   and top < (part[1] + part[3]) / 2 < bottom]
        # Word order from a sparse table may differ from PDF drawing order.
        text = " ".join(part[4] for part in sorted(located, key=lambda part: (round(part[1], 1), part[0])))
        if not text:
            yield "RESOURCE_POSITIONED_TOKEN_UNAVAILABLE:" + observation.variable
        elif numeric_token_spans(text, observation.original_value, observation.original_unit) != ((0, len(text)),):
            yield "RESOURCE_POSITIONED_TOKEN_CONFLICT:" + observation.variable


def _known_table_label_pages(document):
    """Use indexed text to detect repeated printed labels beyond the parse budget."""
    labels = {}
    for number in range(1, len(document) + 1):
        try:
            lines = document.text(number, positioned=True).splitlines()
        except (OSError, RuntimeError, ValueError):
            continue
        for index, line in enumerate(lines):
            text = clean(line)
            if (match := CAPTION.match(text)) and not _TABLE_PROSE.match(text):
                heading = " ".join(map(clean, lines[index:index + 2]))
                if _RESOURCE.search(heading):
                    labels.setdefault(match[1], set()).add(number)
    return labels


def discover(root, source, registry, *, page_numbers, context_pages=(), cache=None, document_cache=None):
    """Verify the exact PDF first, then read fixed native pages and table coordinates."""
    page_numbers, context_pages = tuple(page_numbers), tuple(context_pages)
    if not page_numbers or any(type(page) is not int or page < 1 for page in page_numbers):
        raise ValueError("Resource discovery requires positive physical page numbers")
    if any(type(page) is not int or page < 1 for page in context_pages):
        raise ValueError("Resource method witnesses require positive physical page numbers")
    if source["kind"] != "pdf":
        raise ValueError("Resource discovery requires a PDF source snapshot")
    pages = sorted(set(page_numbers))
    path = Path(root) / source["path"]
    sha = source["sha256"]
    decisions, context_decisions, candidates = [], [], []
    holder = nullcontext(document_cache) if document_cache is not None else PdfDocumentCache(
        path.parent, source_paths={sha: path}, cache=cache)
    with holder as documents:
        try:
            document = documents.open(sha)
            page_count = len(document)
        except (DocumentUnavailable, OSError, RuntimeError, ValueError) as exc:
            return {"pages": [{"physical_page": page, "status": "SOURCE_BLOCKED", "reason": str(exc)}
                              for page in pages], "context_page_dispositions": [
                        {"physical_page": page, "status": "SOURCE_BLOCKED", "reason": str(exc), "requested": True}
                        for page in sorted(set(context_pages))], "candidates": ()}
        known_labels = _known_table_label_pages(document) if document_cache is not None else {}
        supporting = {}
        failures = {}
        nearby = {number for page in pages if page <= page_count for number in range(max(1, page - 2), page)}
        context_requested = set(context_pages) | nearby
        for page in sorted(set(pages) | context_requested):
            status, reason = "PAGE_UNAVAILABLE", "PHYSICAL_PAGE_OUT_OF_RANGE"
            if page > page_count:
                reason = "PHYSICAL_PAGE_OUT_OF_RANGE"
            else:
                try:
                    blocks = [(list(block[:4]), text) for block in document.blocks(page)
                              if block[6] == 0 and (text := clean(block[4]))]
                except (OSError, RuntimeError, ValueError) as exc:
                    status, reason = "PARSE_FAILED", type(exc).__name__
                    failures[page] = reason
                else:
                    supporting[page] = blocks
                    status, reason = ("PARSED", None) if blocks else ("UNREADABLE", "NATIVE_TEXT_BLOCKS_EMPTY")
            if page in context_requested:
                context_decisions.append({"physical_page": page, "requested": page in context_pages,
                                          "status": status, "reason": reason})
        for page in pages:
            if page > page_count:
                decisions.append({"physical_page": page, "status": "PAGE_UNAVAILABLE", "reason": "PHYSICAL_PAGE_OUT_OF_RANGE"})
                continue
            if page in failures:
                decisions.append({"physical_page": page, "status": "PARSE_FAILED", "reason": failures[page]})
                continue
            try:
                blocks = supporting[page]
                tables, error = document.tables(page)
                discovered = candidates_on_page(source, registry, page, blocks, tables, supporting_pages=supporting,
                                                method_pages=context_pages, table_label_pages=known_labels) if not error else ()
                if discovered:
                    words = document.words(page)
                    discovered = tuple({**candidate, "issues": tuple(sorted(set(candidate["issues"]) |
                                              set(_positioned_value_issues(candidate, words))))} for candidate in discovered)
            except (OSError, RuntimeError, ValueError) as exc:
                error, discovered = type(exc).__name__, ()
            status = "PARSE_FAILED" if error else "DISCOVERED" if discovered else "NO_CANDIDATES"
            decisions.append({"physical_page": page, "status": status, "reason": error})
            candidates.extend(discovered)
    return {"pages": decisions, "context_page_dispositions": context_decisions, "candidates": tuple(candidates)}
