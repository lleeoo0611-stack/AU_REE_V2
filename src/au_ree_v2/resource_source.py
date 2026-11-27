"""Re-read physical resource rows eligible for automatic admission checks."""

from datetime import date
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
)
from .semantic_resource import (
    CAPTION, CUTOFF, ESTIMATE_DATE, GRADE_PHRASE, MONTHS, RISKY, _CLASSIFIED_ROW, _anchors, _header_unit,
    clean, column_header_anchors, located_column_headers, page_table_caption,
)
from .store import digest
from .technical_tables import cells


VERSION = "native-resource-row-v3"
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
_DRY_METHOD = re.compile(r"\btonnages?\s+(?:was|were|is|are)\s+(?:reported|assessed|estimated|calculated)\s+on\s+a\s+dry\s+basis\b", re.I)
_WET_METHOD = re.compile(r"\btonnages?\s+(?:was|were|is|are)\s+(?:reported|assessed|estimated|calculated)\s+on\s+a\s+wet\s+basis\b", re.I)
_CHEMICAL = re.compile(r"\btotal rare earth oxides?(?:\s*\(TREO\))?\b|\bTREO\s*=\s*La2O3\s*\+\s*CeO2\s*\+", re.I)
_EXCLUDED_OXIDE = re.compile(r"\b(?:TREO|total rare earth oxides?)\s*(?:\(TREO\)\s*)?(?:exclud\w+|minus|[-−])\s*"
                             r"(?:[a-z]{1,2}\d*(?:O\d*)?|cerium|yttrium|scandium)\b", re.I)
_HOLD = re.compile(r"\b(?:scandium|gallium|wet tonnes?|concentrate|recoverable|exclud(?:es?|ing)|\bHM\b)\b", re.I)
_CONTINUATION = re.compile(r"\b(?:continued|continuation|cont\.)\b", re.I)
_CUTOFF_COLUMN = re.compile(r"cut[- ]?off\s*\(\s*(?:TREO\s+(ppm|%)|(ppm|%)\s+TREO)\s*\)", re.I)
_CUTOFF_COMPARISON = re.compile(r"(?P<operator>>=|<=|[≥≤><=]|\bat least|\bat most|\babove|\bbelow|\bgreater than|\bless than)"
                                r"(?:\s+(?:an?|the))?\s*$", re.I)
_CUTOFF_MARKER = re.compile(r"\bcut[- ]?off(?:\s+grade)?\s+(?:of\s+)?(?:[:=]\s*)?"
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
    candidates = [(number, box, text) for number, blocks in report_pages.items() if page - 2 <= number < page
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
                   located, cutoff):
    witnesses = []
    section_proof, estimate_proof, next_section = _jorc_section_proofs(page, report_pages, subject["scope_id"],
                                                                      subject["effective_date"], located, cutoff)

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
    for number, page_blocks in report_pages.items():
        for box, quote in page_blocks:
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


def _table_rows(source, registry, page, table, tables, blocks, supporting_pages, method_pages):
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
    elif not extent_bound:
        table_issues.append("PROJECT_SCOPE_EXTENT_UNRESOLVED")
    if len(declared_dates) != 1:
        table_issues.append("RESOURCE_ESTIMATE_DATE_UNRESOLVED" if not declared_dates else "RESOURCE_ESTIMATE_DATE_CONFLICT")
    effective = next(iter(declared_dates)) if len(declared_dates) == 1 else None
    header_text = " | ".join(clean(cell["text"]) for cell in headers)
    scoped_notes = [text for _, text in notes]
    bulk = bool(_BULK.search(header_text) or any(_BULK.search(text) or _DRY_METHOD.search(text) for text in scoped_notes)
                or any(_DRY_METHOD.search(text) for _, _, text in external))
    wet = bool(any(_WET_METHOD.search(text) for text in scoped_notes) or any(_WET_METHOD.search(text) for _, _, text in external))
    bulk = bulk and not wet and not _HOLD.search(header_text)
    if not bulk:
        table_issues.append("DRY_BULK_ORE_BASIS_UNRESOLVED")
    basis = bool(_CHEMICAL.search(header_text) or any(_CHEMICAL.search(text) for text in texts + scoped_notes))
    if any(_EXCLUDED_OXIDE.search(text) for text in [header_text, *texts, *scoped_notes]):
        basis = False
        table_issues.append("TREO_EXCLUDED_OXIDE_BASIS")
    if not basis:
        table_issues.append("TREO_DEFINITION_UNRESOLVED")
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
        for number, box, text in external:
            witnesses.append(_anchors("estimate_reference", {**row, "physical_page": number}, text, bbox=box))
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
        cutoff = next(iter(cutoffs.values())) if len(cutoffs) == 1 else None
        if cutoff and cutoff["basis"] != "TREO":
            cutoff = None
        if cutoff is None:
            row_issues.append("RESOURCE_CUTOFF_UNRESOLVED" if not cutoffs else "RESOURCE_CUTOFF_BASIS_OR_VALUE_CONFLICT")
        estimate = digest(["source-estimate-v1", source["sha256"], page, table["table_index"], project, scope, effective])
        statement = digest(["source-statement-v1", estimate, index])
        reported_table = CAPTION.match(caption)[1] if caption_entry else None
        subject = {"project_id": project, "scope_id": scope, "estimate_id": estimate, "statement_id": statement,
                   "effective_date": effective, "physical_page": page, "table": table["table_index"], "row": index,
                   "reported_table_label": reported_table}
        jorc, jorc_anchors = _jorc_evidence(source, registry, page, table, tables, row, subject, caption_entry, active_section, blocks,
                                           report_pages, located, cutoff)
        if jorc["reason"]:
            row_issues.append(jorc["reason"])
        witnesses.extend(jorc_anchors)
        context = {"scope": scope, "statement_id": statement, "estimate_id": estimate, "effective_date": effective,
                   "category": category or None, "resource_type": "MINERAL_RESOURCE" if declared_resource and not incompatible else None,
                   "reporting_standard": "JORC" if jorc["status"] == "AFFIRMED" else None,
                   "jorc_status": jorc["status"], "jorc_rule_version": JORC_VERSION,
                   "scope_coverage": "PROJECT_TOTAL" if complete and extent_bound else "RESOURCE_COMPONENT" if not complete else None,
                   "cutoff_grade": cutoff,
                   "basis": "TREO" if basis else None, "material_basis": "RESOURCE_BULK_ORE" if bulk else None,
                   "denominator_basis": "RESOURCE_BULK_ORE_MASS" if bulk else None,
                   "available_date": source.get("available_date"), "definition_witness": VERSION,
                   "reported_table_label": reported_table}
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
               "jorc_assessment": jorc}


def candidates_on_page(source, registry, physical_page, blocks, tables, *, supporting_pages=None, method_pages=None):
    """Visit native rows and keep every disposition, including unusable components."""
    registry = _registered_scope_aliases(registry)
    supporting_pages = supporting_pages or {}
    if method_pages is None:
        method_pages = supporting_pages.keys()
    return tuple(candidate for table in tables
                 for candidate in _table_rows(source, registry, physical_page, table, tables, blocks, supporting_pages, method_pages))


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


def discover(root, source, registry, *, page_numbers, context_pages=(), cache=None):
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
    decisions, candidates = [], []
    with PdfDocumentCache(path.parent, source_paths={sha: path}, cache=cache) as documents:
        try:
            document = documents.open(sha)
            page_count = len(document)
        except (DocumentUnavailable, OSError, RuntimeError, ValueError) as exc:
            return {"pages": [{"physical_page": page, "status": "SOURCE_BLOCKED", "reason": str(exc)}
                              for page in pages], "candidates": ()}
        supporting = {}
        nearby = {number for page in pages for number in range(max(1, page - 2), page)}
        for page in sorted(set(context_pages) | nearby):
            if page > page_count:
                continue
            try:
                supporting[page] = [(list(block[:4]), clean(block[4])) for block in document.blocks(page) if block[6] == 0]
            except (OSError, RuntimeError, ValueError):
                continue
        for page in pages:
            if page > page_count:
                decisions.append({"physical_page": page, "status": "PAGE_UNAVAILABLE", "reason": "PHYSICAL_PAGE_OUT_OF_RANGE"})
                continue
            try:
                blocks = [(list(block[:4]), clean(block[4])) for block in document.blocks(page) if block[6] == 0]
                tables, error = document.tables(page)
                discovered = candidates_on_page(source, registry, page, blocks, tables, supporting_pages=supporting,
                                                method_pages=context_pages) if not error else ()
                if discovered:
                    words = document.words(page)
                    discovered = tuple({**candidate, "issues": tuple(sorted(set(candidate["issues"]) |
                                              set(_positioned_value_issues(candidate, words))))} for candidate in discovered)
            except (OSError, RuntimeError, ValueError) as exc:
                error, discovered = type(exc).__name__, ()
            status = "PARSE_FAILED" if error else "DISCOVERED" if discovered else "NO_CANDIDATES"
            decisions.append({"physical_page": page, "status": status, "reason": error})
            candidates.extend(discovered)
    return {"pages": decisions, "candidates": tuple(candidates)}
