"""Re-read physical resource rows eligible for automatic admission checks."""

from datetime import date
from pathlib import Path
import re

from .document_processing import DocumentUnavailable, PdfDocumentCache
from .numeric_evidence import numeric_token_spans, scalar_decimal
from .observation_pipeline import raw_from_candidate
from .observation_schema import value_evidence_issue
from .pdf_extract import _matches
from .semantic_resource import (
    CAPTION, CUTOFF, ESTIMATE_DATE, MONTHS, RISKY, _CLASSIFIED_ROW, _anchors, _header_unit,
    clean, column_header_anchors, located_column_headers, page_table_caption,
)
from .store import digest
from .technical_tables import cells


VERSION = "native-resource-row-v1"
_VARIABLES = ("ore_mt", "grade", "contained_treo_kt")
_RESOURCE = re.compile(r"\b(?:mineral resources?|resource estimate|MRE)\b", re.I)
_JORC = re.compile(r"\bJORC\b", re.I)
_TOTAL = re.compile(r"(?:(?:grand|global|project|combined)\s+)?total(?:\s*\(\d+\))?", re.I)
_CATEGORY = re.compile(r"\b(measured|indicated|inferred)\b", re.I)
_CLASSIFICATION = re.compile(r"(?:JORC\s+)?(?:category|classification|resource classification)", re.I)
_SCOPE_END = re.compile(r"\b(?:total|JORC|measured|indicated|inferred|estimate of)\b|" + _RESOURCE.pattern, re.I)
_SCOPE_AFTER = re.compile(r"(?:mineral resources?(?: estimate)?|resource estimate)\s+for\s+(?:the\s+)?(.+?)\s+(?:as at|effective|reported above)\b", re.I)
_BULK = re.compile(r"\b(?:(?:dry|bulk|whole)[ -]+ore|dry\s+(?:material|tonnes?|tonnage))\b", re.I)
_DRY_METHOD = re.compile(r"\btonnages?\s+(?:was|were|is|are)\s+(?:reported|assessed|estimated|calculated)\s+on\s+a\s+dry\s+basis\b", re.I)
_WET_METHOD = re.compile(r"\btonnages?\s+(?:was|were|is|are)\s+(?:reported|assessed|estimated|calculated)\s+on\s+a\s+wet\s+basis\b", re.I)
_JORC_METHOD = re.compile(r"\b(?:reported|estimated|classified|prepared)\s+in\s+accordance\b.{0,150}\bJORC\b", re.I)
_CHEMICAL = re.compile(r"\btotal rare earth oxides?(?:\s*\(TREO\))?\b|\bTREO\s*=\s*La2O3\s*\+\s*CeO2\s*\+", re.I)
_EXCLUDED_OXIDE = re.compile(r"\b(?:TREO|total rare earth oxides?)\s*(?:\(TREO\)\s*)?(?:exclud\w+|minus|[-−])\s*"
                             r"(?:[a-z]{1,2}\d*(?:O\d*)?|cerium|yttrium|scandium)\b", re.I)
_HOLD = re.compile(r"\b(?:scandium|gallium|wet tonnes?|concentrate|recoverable|exclud(?:es?|ing)|\bHM\b)\b", re.I)
_CONTINUATION = re.compile(r"\b(?:continued|continuation|cont\.)\b", re.I)
_CUTOFF_COLUMN = re.compile(r"cut[- ]?off\s*\(\s*(?:TREO\s+(ppm|%)|(ppm|%)\s+TREO)\s*\)", re.I)
_REPORT_FOOTER = re.compile(r"(?P<title>.+?)\s+Page\s+(?P<page>\d+)\s+of\s+(?P<count>\d+)\s*$", re.I)
_SCOPE_ALIAS = re.compile(r"\s[—–]\s+([^—–;]+?)\s+scope\s*$", re.I)
_SCOPE_SUFFIX = re.compile(r"\s+(?:(?:rare earth )?deposit|project)\s*$", re.I)
_CONTAINED_CLAIM = re.compile(r"\b(?:contained\s+TREO|TREO\s+conten(?:t|ts)|TREO\s+tonnes?)\b", re.I)
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
    declarations = set()
    for text in texts:
        for m in CUTOFF.finditer(text):
            value = scalar_decimal(m["x"], m["u"])
            if value is not None and value >= 0:
                declarations.add((str(value.normalize()), m["u"].lower(), m["b"].upper().replace(" ", "")))
    return declarations


def _supporting_blocks(caption, table, tables, blocks):
    """Use an explicitly referenced description or immediate unit-definition note."""
    table_number = CAPTION.match(caption)[1]
    bounds = table["bbox"]
    next_table_top = min((other["bbox"][1] for other in tables if other["bbox"][1] > bounds[3]), default=float("inf"))
    reference = re.compile(r"\bTable\s+" + re.escape(table_number) + r"(?![\w.\-])", re.I)
    context, notes = [], []
    for box, text in blocks:
        if not bounds[0] <= (box[0] + box[2]) / 2 <= bounds[2] or CAPTION.match(text):
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


def _report_context(page, blocks, supporting_pages, registry, project):
    title = _report_title(page, blocks)
    if not title or {row["entity_id"] for row in _matches(title, registry)} != {project}:
        return []
    return [(number, box, text) for number, other_blocks in sorted(supporting_pages.items()) if number != page
            and _report_title(number, other_blocks) == title for box, text in other_blocks
            if _DRY_METHOD.search(text) or _WET_METHOD.search(text) or _JORC_METHOD.search(text)]


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


def _table_rows(source, registry, page, table, tables, blocks, supporting_pages):
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
    caption_entry = page_table_caption(tables, table, blocks)
    caption = caption_entry[1] if caption_entry else ""
    if not (_RESOURCE.search(caption) or any(_CLASSIFICATION.fullmatch(clean(cell["text"])) for cell in headers)
            and any(_header_unit(_column_parts(cell, headers)[0], "grade", native=True)
                    for cell in native if cell["row"] >= first_row)):
        return
    context_blocks, notes = _supporting_blocks(caption, table, tables, blocks) if caption_entry else ([], [])
    texts = [caption, *(text for _, text in context_blocks)]
    project, scope, extent_bound = _scope(caption, registry)
    external = _report_context(page, blocks, supporting_pages, registry, project) if project else []
    declared_dates = _effective_dates((caption,))
    declared_cutoffs = _cutoff((caption,))
    table_issues = []
    declared_resource = bool(caption_entry and _RESOURCE.search(caption))
    incompatible = bool(RISKY.search(caption) or _HOLD.search(caption))
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
    jorc = bool(any(_JORC.search(text) for text in texts + [cell["text"] for cell in headers])
                or any(_JORC_METHOD.search(text) for _, _, text in external))
    if not jorc:
        table_issues.append("RESOURCE_REPORTING_STANDARD_UNRESOLVED")
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
        cutoffs = set(declared_cutoffs)
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
            if cutoff_column and (number := scalar_decimal(cell["text"], cutoff_column[1] or cutoff_column[2])) is not None:
                cutoff_unit = cutoff_column[1] or cutoff_column[2]
                cutoffs.add((str(number.normalize()), cutoff_unit.lower(), "TREO"))
                witnesses.append(_cell_anchor("cutoff_value", row, table, cell))
                witnesses.extend({**anchor, "field": "cutoff_header"} for anchor in
                                 column_header_anchors(row, table, pieces, cutoff_unit))
        cutoff = next(iter(cutoffs)) if len(cutoffs) == 1 else None
        if cutoff and cutoff[2] != "TREO":
            cutoff = None
        if cutoff is None:
            row_issues.append("RESOURCE_CUTOFF_UNRESOLVED" if not cutoffs else "RESOURCE_CUTOFF_BASIS_OR_VALUE_CONFLICT")
        estimate = digest(["source-estimate-v1", source["sha256"], page, table["table_index"], project, scope, effective])
        statement = digest(["source-statement-v1", estimate, index])
        context = {"scope": scope, "statement_id": statement, "estimate_id": estimate, "effective_date": effective,
                   "category": category or None, "resource_type": "MINERAL_RESOURCE" if declared_resource and not incompatible else None,
                   "reporting_standard": "JORC" if jorc else None,
                   "scope_coverage": "PROJECT_TOTAL" if complete and extent_bound else "RESOURCE_COMPONENT" if not complete else None,
                   "cutoff_grade": dict(zip(("value", "unit", "basis"), cutoff)) if cutoff else None,
                   "basis": "TREO" if basis else None, "material_basis": "RESOURCE_BULK_ORE" if bulk else None,
                   "denominator_basis": "RESOURCE_BULK_ORE_MASS" if bulk else None,
                   "available_date": source.get("available_date"), "definition_witness": VERSION,
                   "reported_table_label": CAPTION.match(caption)[1] if caption_entry else None}
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
               "project_id": project, "observations": tuple(observations), "issues": tuple(sorted(set(row_issues)))}


def candidates_on_page(source, registry, physical_page, blocks, tables, *, supporting_pages=None):
    """Visit native rows and keep every disposition, including unusable components."""
    registry = _registered_scope_aliases(registry)
    return tuple(candidate for table in tables
                 for candidate in _table_rows(source, registry, physical_page, table, tables, blocks, supporting_pages or {}))


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
        for page in sorted(set(context_pages)):
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
                discovered = candidates_on_page(source, registry, page, blocks, tables, supporting_pages=supporting) if not error else ()
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
