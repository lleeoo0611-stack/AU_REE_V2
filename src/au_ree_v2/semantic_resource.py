"""Source-bound resource quantities and auditable estimate relationship candidates.

This experimental reader uses the already-frozen Project and PDF bindings. A
binding licenses work on a page, and a source witness establishes a particular
cell. Published values and previous adjudication labels are not read here.
"""
from collections import defaultdict
from datetime import date
from decimal import Decimal
from itertools import combinations
import re
import unicodedata

from .document_processing import DocumentUnavailable, PdfDocumentCache
from .normalization import MASS_FRACTION_UNIT_PATTERN, RESOURCE_CUTOFF_ANALYTE
from .numeric_evidence import NATIVE_GEOMETRIC_UNIT_HEADER, header_within_value_column, numeric_token_spans
from .pdf_extract import NUMBER
from .store import digest
from .technical_tables import cells, number_token, path_above


VERSION = "resource-source-observation-v1"
LOCATED_VERSION = "resource-source-observation-v2-typed-span"
PROFILE = "DIRECT_RESOURCE_UNIT_COMPARISON_V1"
MARKER = re.compile(rf"(?:\btotal(?:\(\d+\))?\s+)?{NUMBER}(?:\s+{NUMBER})+\s*$", re.I)
CAPTION = re.compile(r"^table\s+(\d+(?:[-.]\d+)?)\b[\s:.–-]*", re.I)
MASS_HEADER = re.compile(r"(?:tonnes?|tonnage|resource(?: tonnage)?|dry tonnes?|material)\s*\(?\s*(Mt|kt|t)\s*\)?", re.I)
GRADE_HEADER = re.compile(rf"(?:TREO\s*\*?\s*\(?\s*({MASS_FRACTION_UNIT_PATTERN})\s*\)?|"
                          rf"({MASS_FRACTION_UNIT_PATTERN})\s+TREO\s*\*?)", re.I)
NATIVE_MASS_HEADER = re.compile(r"(?:dry\s+)?(?:bulk\s+)?ore\s+(?:tonnes?|tonnage)\s*\(?\s*(Mt|kt|t)\s*\)?", re.I)
NATIVE_GRADE_HEADER = re.compile(r"(?:total rare earth oxides?\s*\(TREO\)|TREO)\s*\*?\s*(?:grade\s*)?"
                                 rf"\(?\s*({MASS_FRACTION_UNIT_PATTERN})\s*\)?", re.I)
CONTAINED_HEADER = re.compile(r"(?:contained\s+)?TREO\s*\*?\s*\(?\s*(t|kt|[‘'’]?000 tonnes)\s*\)?", re.I)
GRADE_PHRASE = re.compile(
    rf"(?<![\w.,+−–-])(?P<mass>{NUMBER})\s*(?P<mass_unit>million tonnes|Mt|kt|t)\s*"
    rf"(?:at(?:\s+an\s+average\s+grade\s+of)?|@)\s*(?P<grade>{NUMBER})\s*(?P<grade_unit>{MASS_FRACTION_UNIT_PATTERN})\s*"
    r"(?P<basis>total rare earth oxides?\s*\(TREO\)|TREO)(?!\w|\s*[+−-]\s*(?:Ce|Y|Sc|[A-Z][a-z]?\d*O\d+)\b)",
    re.I,
)
TABLE_GRADE_PHRASE = re.compile(rf"(?P<mass>{NUMBER})\s*(?P<mass_unit>Bt|Mt)\s+at\s+(?P<grade>{NUMBER})\s*(?P<grade_unit>ppm|%)")
CUTOFF = re.compile(
    rf"(?P<x>{NUMBER})\s*(?P<u>{MASS_FRACTION_UNIT_PATTERN})\s*(?P<b>{RESOURCE_CUTOFF_ANALYTE})\s+cut[- ]?off\b",
    re.I,
)
ESTIMATE_DATE = re.compile(
    r"\b(?:as\s+at|effective(?:\s+date)?(?:\s*of)?|dated)\s+"
    r"(\d{4}-\d{2}-\d{2}|\d{1,2}\s+(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{4})\b",
    re.I,
)
MONTHS = "jan feb mar apr may jun jul aug sep oct nov dec".split()
RISKY = re.compile(r"\b(?:ore reserves?|exploration targets?|production targets?|forecast|stockpiles?)\b", re.I)


def clean(value):
    return " ".join(unicodedata.normalize("NFKC", str(value or "")).split())


def _decimal(token):
    return Decimal(token.replace(",", "")) if re.fullmatch(NUMBER, token) else None


def _numeric_tokens(text):
    return re.findall(rf"(?<![\w.,]){NUMBER}(?![\w.,])", text)


def _matches_text(text, marker):
    return bool(re.search(r"(?<![\w.,])" + re.escape(marker) + r"(?![\w.,])", text))


def _anchors(field, source_row, quote, **position):
    return {"field": field, "source_sha256": source_row["source_sha256"], "page": source_row["physical_page"],
            "quote": quote, **position}


def _span(view, start, end, *, scope="QUOTE", quote_start=0):
    return {"scope": scope, "view": view, "start": start, "end": end, "quote_start": quote_start}


def _header_unit(header, quantity, *, native=False):
    # Preserve source spelling, including case distinctions in SI prefixes.
    if quantity == "ore_mt":
        if header in {"M Tonnes", "Million Tonnes", "million tonnes"}:
            return header
        parse = MASS_HEADER.fullmatch(header)
        if not parse and native:
            parse = NATIVE_MASS_HEADER.fullmatch(header)
        return parse[1] if parse and parse[1] in {"Mt", "kt", "t"} else None
    if quantity == "grade":
        match = GRADE_HEADER.fullmatch(header)
        if match:
            return (match[1] or match[2]).lower()
        native_grade = NATIVE_GRADE_HEADER.fullmatch(header) if native else None
        return native_grade[1].lower() if native_grade else None
    parse = CONTAINED_HEADER.fullmatch(header)
    return parse[1] if parse else None


def _context(row, anchors):
    edition = row.get("effective_date")
    claim = "RESOURCE_ESTIMATE" if row.get("statement_kind") in {"RESOURCE_CONTEXT", "MINERAL_RESOURCE"} else "UNRESOLVED"
    cutoff = None
    as_of = None
    for evidence in anchors:
        if evidence["field"] not in {"scope", "estimate_reference"}:
            continue
        quote = evidence["quote"]
        matches = {m.groups() for m in CUTOFF.finditer(quote)}
        if len(matches) == 1:
            x, u, b = next(iter(matches))
            cutoff = {"value": str(_decimal(x)), "unit": u, "basis": b.upper().replace(" ", "")}
        match = ESTIMATE_DATE.search(quote)
        if match and re.search(r"\b(?:mineral resource|estimate|MRE)\b", quote, re.I):
            date_text = match[1]
            try:
                if "-" in date_text:
                    as_of = date.fromisoformat(date_text).isoformat()
                else:
                    day, month, year = date_text.split()
                    as_of = date(int(year), MONTHS.index(month[:3].lower()) + 1, int(day)).isoformat()
            except ValueError:
                as_of = None
    return {"scope": row.get("scope"), "statement_id": row.get("statement_id"),
            "statement_kind": row.get("statement_kind"), "category": row.get("category"),
            "edition_effective_date": edition, "date_role": row.get("date_role"),
            "publication_date": row.get("publication_date"), "known_at": row.get("source_date_used"),
            "estimate_date": as_of, "estimate_date_precision": "DAY" if as_of else None,
            "cutoff": cutoff, "frozen_cutoff_label": row.get("cutoff_grade"),
            "chemical_basis": row.get("basis"), "material": row.get("material_basis"),
            "denominator": row.get("denominator_basis"), "claim_type": claim,
            "original_locator": row.get("locator")}


def _table_caption(tables, table, blocks):
    """A top caption binds only to the immediate following table region."""
    top = table["bbox"][1]
    prior_bottom = max((t["bbox"][3] for t in tables if t["bbox"][3] <= top), default=0)
    captions = [text for bbox, text in blocks if prior_bottom - 2 <= bbox[3] <= top + 1
                and 0 <= top - bbox[3] <= 45 and CAPTION.search(text)]
    if len(captions) == 1:
        return captions[0]
    return None


def page_table_caption(tables, table, blocks):
    """Find an isolated, unambiguous caption above or below its native grid."""
    def distance(box, grid):
        left, top, right, bottom = grid["bbox"]
        if not left <= (box[0] + box[2]) / 2 <= right:
            return None
        if 0 <= top - box[3] <= 45:
            return top - box[3]
        if 0 <= box[1] - bottom <= 65:
            return box[1] - bottom
        return None

    matching = []
    for box, text in blocks:
        if not CAPTION.match(text) or len(text) > 260 or box[3] - box[1] > 44:
            continue
        owners = [(gap, other["table_index"]) for other in tables
                  if (gap := distance(box, other)) is not None]
        owners.sort()
        if owners and owners[0][1] == table["table_index"] and (len(owners) == 1 or owners[1][0] - owners[0][0] > 2):
            matching.append((box, text))
    return matching[0] if len(matching) == 1 else None


def _marker_binding(row_text, markers, raw_tokens):
    normalized = clean(row_text)
    if any(MARKER.fullmatch(m) and _matches_text(normalized, m) for m in markers):
        return True
    numbers = _numeric_tokens(normalized)
    # Full known token row or multiple independent printed anchors identify a
    # row. A single coincident number, a partial match, or a page is insufficient.
    if len(raw_tokens) >= 2 and raw_tokens == numbers:
        return True
    scalar_markers = {m for m in markers if _decimal(m) is not None}
    if len(scalar_markers.intersection(numbers)) >= 2:
        return True
    # A total-row prefix from an independently preserved quote identifies a
    # category and its leading mass cell. The binding remains ambiguous if
    # more than one native table has this quoted prefix.
    return any(re.fullmatch(rf"(?:grand )?total\s+{NUMBER}", m, re.I)
               and re.match(re.escape(m) + r"(?:\s|$)", normalized, re.I) for m in markers)


def _header_cells(native, table, tables):
    first_data = next((c["row"] for c in native if _decimal(clean(c["text"])) is not None or
                       TABLE_GRADE_PHRASE.fullmatch(clean(c["text"]))), len(table["cells"]))
    own = [c for c in native if c["row"] < first_data]
    if any(re.search(r"\b(?:tonnes|tonnage|TREO|resource)\b", c["text"], re.I) for c in own):
        return own
    # Some PDFs render the header and the body as separate connected grids.
    # Match the entire horizontal extent, the number of columns, and a local
    # pre-data header immediately above. A different table cannot lend a unit.
    x0, y0, x1, _ = table["bbox"]
    prior = [other for other in tables if 0 <= y0 - other["bbox"][3] <= 75
             and abs(x0 - other["bbox"][0]) <= 2 and abs(x1 - other["bbox"][2]) <= 2
             and len(other["cells"][0]) == len(table["cells"][0])]
    if len(prior) == 1:
        inherited = cells(prior[0])
        if inherited and not any(_decimal(clean(c["text"])) is not None for c in inherited):
            return inherited + own
    return own


def located_column_headers(cell, header_cells):
    """Keep actual header cells touching one column, in native grid order."""
    midpoint = (cell["bbox"][0] + cell["bbox"][2]) / 2
    return [piece for piece in header_cells if piece["row"] < cell["row"]
            and piece["bbox"][0] < midpoint < piece["bbox"][2]
            and piece["bbox"][3] <= cell["bbox"][1] + .1]


def column_header_anchors(row, table, pieces, unit, *, value_cell=None, row_cells=()):
    """Record native heading locations and independently prove any split-grid column."""
    unit_pattern = re.compile(r"(?<![\w])" + re.escape(unit) + r"(?![\w])")
    result = []
    for piece in pieces:
        quote = clean(piece["text"])
        role = "unit" if unit_pattern.search(quote) else "header_definition"
        anchor = _anchors(role, row, quote, table_index=table["table_index"], row=piece["row"],
                          column=piece["column"], bbox=piece["bbox"])
        if role == "unit" and value_cell and value_cell["column"] != piece["column"]:
            matching_values = [cell for cell in row_cells if header_within_value_column(piece["bbox"], cell["bbox"])]
            if matching_values == [value_cell]:
                anchor["locator"] = NATIVE_GEOMETRIC_UNIT_HEADER
        result.append(anchor)
    return result


def _table_witnesses(row, tables, blocks, markers, raw_tokens, *, location=None, caption_witness=None):
    witnesses = []
    quantity = row["target_variable"]
    for table in tables:
        if location is not None and table["table_index"] != location[0]:
            continue
        native = cells(table)
        caption = caption_witness[1] if caption_witness else _table_caption(tables, table, blocks)
        headers = _header_cells(native, table, tables)
        for ri, source_row in enumerate(table["cells"]):
            row_text = clean(" ".join(str(c or "") for c in source_row))
            if (location is not None and ri != location[1]
                    or location is None and not _marker_binding(row_text, markers, raw_tokens)):
                continue
            for c in (c for c in native if c["row"] == ri):
                header_path = path_above(c, headers, len(table["cells"]) + 10)
                if table.get("external_header") and c["column"] < len(table.get("header", [])):
                    header_path = [table["header"][c["column"]], *header_path]
                header = clean(" ".join(dict.fromkeys(str(t or "") for t in header_path)))
                unit = _header_unit(header, quantity, native=location is not None)
                quote = token = clean(c["text"])
                start, end = 0, len(token)
                pos = dict(table_index=table["table_index"], row=ri, column=c["column"], bbox=c["bbox"])
                if not unit and re.search(r"Total Mineral Resource", header, re.I):
                    full = TABLE_GRADE_PHRASE.fullmatch(token)
                    if full and quantity in {"ore_mt", "grade"}:
                        group = "grade" if quantity == "grade" else "mass"
                        unit = full[group + "_unit"]
                        token = full[group]
                        start, end = full.span(group)
                state = number_token(token)
                if not unit or state is None:
                    continue
                if RISKY.search(header) or (caption and RISKY.search(caption) and
                                            not re.search(r"\b(?:mineral resource|MRE)\b", caption, re.I)):
                    continue
                if location is None and state["token_state"] == "NUMBER" and not any(
                    _matches_text(m, state["original_token"]) for m in markers
                ) and state["original_token"] not in raw_tokens:
                    # Preserve the search witness and keep the mismatching
                    # original precision for a later relation review.
                    if not caption and not re.match(r"^(?:total|grand total)\b", row_text, re.I):
                        continue
                span = _span("MUPDF_TABLE_CELL_NFKC_WHITESPACE_FOLDED", start, end)
                anchors = [_anchors("token", row, quote, text_span=span, **pos), _anchors("row", row, row_text, **pos)]
                unit_anchors = column_header_anchors(row, table, located_column_headers(c, [h for h in headers if h in native]), unit) if location is not None else []
                if any(anchor["field"] == "unit" for anchor in unit_anchors):
                    anchors.extend(unit_anchors)
                else:
                    anchors.append(_anchors("unit", row, header, table_index=table["table_index"], column=c["column"]))
                if caption:
                    anchors.append(_anchors("scope", row, caption, table_index=table["table_index"],
                                            **({"bbox": caption_witness[0]} if caption_witness else {})))
                witnesses.append((_native(quantity, state, unit), anchors))
    return witnesses


def _native(quantity, state, unit):
    return {"quantity": quantity, "token": state["original_token"], "unit": unit,
            "token_state": state["token_state"], "bounds": state["bounds"]}


def _narrative_witnesses(row, blocks, markers):
    quantity = row["target_variable"]
    if quantity not in {"ore_mt", "grade"}:
        return []
    results = []
    for bbox, text in blocks:
        for match in GRADE_PHRASE.finditer(text):
            before = re.split(r"(?<=[a-z)])\.\s+|[;\n]", text[:match.start()])[-1]
            if RISKY.search(before[-130:]) or re.search(r"\b(?:if|assuming|not|target|guidance|planned|expected)\b", before[-90:], re.I):
                continue
            if not re.search(r"\b(?:mineral resources?|resource estimate|MRE)\b", before[-180:], re.I):
                continue
            pair = match["mass"], match["grade"]
            if markers is not None and not all(any(_matches_text(m, token) for m in markers) for token in pair):
                continue
            group = "mass" if quantity == "ore_mt" else "grade"
            token, unit = match[group], match[group + "_unit"]
            start, end = match.span(group)
            span = _span("MUPDF_NATIVE_BLOCK_WHITESPACE_FOLDED", start, end,
                         scope="BLOCK", quote_start=match.start())
            anchors = [_anchors("token", row, match[0], bbox=bbox, offset=start, text_span=span),
                       _anchors("unit", row, match[0], bbox=bbox),
                       _anchors("estimate_reference", row, text, bbox=bbox)]
            results.append((_native(quantity, number_token(token), unit), anchors))
    return results


def _existing_native(row, lines, blocks):
    """Preserve previously captured literals if a uniquely aligned witness exists."""
    token, unit = clean(row.get("original_token")), clean(row.get("original_unit"))
    state = number_token(token)
    if not token or not unit or not state:
        return []
    raw = row.get("raw") or {}
    quote = clean(raw.get("raw_text"))
    def witness(text, view, **location):
        matches = numeric_token_spans(text, token, unit)
        if len(matches) != 1:
            return []
        span = _span(view, *matches[0])
        return [(_native(row["target_variable"], state, unit),
                 [_anchors("token", row, text, text_span=span, **location)])]

    if quote and sum(_matches_text(line, quote) for line in lines) == 1:
        result = witness(quote, "MUPDF_CONTENT_ORDER_LINE_NFKC_WHITESPACE_FOLDED")
        if result:
            return result
    versions = [(bbox, text) for bbox, text in blocks if _matches_text(text, token) and _matches_text(text, unit)]
    if len(versions) == 1 and raw.get("page_markers") and any(
        len(clean(m)) >= 12 and _matches_text(versions[0][1], clean(m)) for m in raw["page_markers"]
    ):
        bounds, quote = versions[0]
        return witness(quote, "MUPDF_NATIVE_BLOCK_WHITESPACE_FOLDED", bbox=bounds)
    return []


def _raw_signatures(row):
    raw = row.get("raw") or {}
    markers = {clean(m) for m in raw.get("page_markers") or [] if isinstance(m, str) and m.strip()}
    quoted = clean(raw.get("raw_text"))
    if quoted:
        markers.add(quoted)
    # These are prior source excerpts, not the stored canonical number or an answer.
    tokens = [clean(item) for item in raw.get("original_tokens") or [] if isinstance(item, (str, int, float))]
    return markers, tokens


def _resolve(row, source):
    result = {"candidate_id": row["candidate_id"], "observation_id": row["observation_id"],
              "project_id": row["project_id"], "source_sha256": row["source_sha256"],
              "physical_page": row["physical_page"], "profile_id": PROFILE,
              "native": None, "anchors": [], "context": _context(row, []), "extraction_version": VERSION}
    gates = list(row.get("source_gates") or [])
    if not source:
        return dict(result, status="SOURCE_BLOCKED", reasons=sorted(set(gates + ["PDF_BYTES_OR_PAGE_UNAVAILABLE"])))
    if gates:
        return dict(result, status="SOURCE_BLOCKED", reasons=gates)
    lines, blocks, tables = source
    markers, raw_tokens = _raw_signatures(row)
    witnesses = _table_witnesses(row, tables, blocks, markers, raw_tokens)
    witnesses += _narrative_witnesses(row, blocks, markers)
    if not witnesses:
        witnesses = _existing_native(row, lines, blocks)
    if not witnesses:
        return dict(result, status="INSUFFICIENT", reasons=["UNBOUND_OR_UNREADABLE_NATIVE_CELL"])
    certain = [pair for pair in witnesses if any(
        _matches_text(m, pair[0]["token"]) for m in markers
    ) or pair[0]["token"] in raw_tokens]
    if certain:
        witnesses = certain
    # Multiple geometrical positions with equal printed values are distinct.
    table_witnesses = [(n, aa) for n, aa in witnesses if "column" in aa[0]]
    if len(table_witnesses) == 1 and all(
        n["token_state"] == "NUMBER" and _decimal(n["token"]) == _decimal(table_witnesses[0][0]["token"]) and
        n["unit"].casefold() == table_witnesses[0][0]["unit"].casefold() for n, _ in witnesses
    ):
        # Prefer the cell for its finer locator if both views repeat its value.
        witnesses = table_witnesses
    unique = {(n["token"], n["unit"], aa[0].get("table_index"), aa[0].get("row"),
               aa[0].get("column"), tuple(aa[0].get("bbox", [])), aa[0].get("offset")):
              (n, aa) for n, aa in witnesses}
    if len(unique) > 1:
        return dict(result, status="INSUFFICIENT", reasons=["COMPETING_SOURCE_WITNESSES"],
                    alternatives=[{"native": n, "anchors": aa} for n, aa in unique.values()])
    native, anchors = next(iter(unique.values()))
    context = _context(row, anchors)
    if anchors[0].get("text_span"):
        context.update(prior_extractor_version=VERSION, extraction_change_reason="EXPLICIT_PRINTED_TOKEN_SPAN")
        result["extraction_version"] = LOCATED_VERSION
    return dict(result, native=native, anchors=anchors, context=context, status="EXTRACTED", reasons=[])


def extract_resource_observations(candidate_rows, assets, *, documents=None):
    """Re-read verified static PDF pages for a frozen source-bound frame."""
    if documents is None:
        with PdfDocumentCache(assets) as cache:
            return extract_resource_observations(candidate_rows, assets, documents=cache)
    sources = defaultdict(list)
    for row in candidate_rows:
        sources[row["source_sha256"]].append(row)
    results = []
    for sha, rows in sorted(sources.items(), key=lambda item: str(item[0])):
        pages = sorted({r["physical_page"] for r in rows
                        if type(r["physical_page"]) is int and r["physical_page"] > 0 and not r.get("source_gates")})
        captures, errors = {}, {}
        if pages:
            try:
                document = documents.open(sha)
            except DocumentUnavailable:
                document = None
            if document is not None:
                for page in pages:
                    if page > len(document):
                        continue
                    lines = [clean(line) for line in document.text(page).splitlines() if clean(line)]
                    blocks = [(list(block[:4]), clean(block[4])) for block in document.blocks(page) if block[6] == 0]
                    tables, error = document.tables(page)
                    captures[page] = lines, blocks, tables
                    if error:
                        errors[page] = error
        for row in rows:
            page = row["physical_page"]
            captured = _resolve(row, captures.get(page))
            if page in errors:
                captured["table_parser_error"] = errors[page]
            results.append(captured)
    return sorted(results, key=lambda r: r["candidate_id"])


_CLASSIFIED_ROW = re.compile(
    r"(?:grand\s+)?total(?:\s*\(\d+\))?|"
    r"(?:(?:measured|indicated|inferred)(?:\s*(?:and|[+/&])\s*)?)+(?:\s*total)?", re.I,
)


def discover_resource_page(source_sha256, physical_page, blocks, tables):
    """Visit physical classified rows and reported resource clauses without seed values."""
    source = {"source_sha256": source_sha256, "physical_page": physical_page}
    captures = []
    for table in tables:
        caption_witness = page_table_caption(tables, table, blocks)
        caption = caption_witness[1] if caption_witness else None
        category_header = bool(caption and re.search(r"mineral resources?|resource estimate|JORC", caption, re.I))
        # Require an independently read resource body or a source classification
        # heading. A generic grade/tonnage summary is an ambiguous document.
        classified = any(_CLASSIFIED_ROW.fullmatch(clean(cell)) and clean(cell).casefold() not in ("total", "grand total")
                         for row in table["cells"] for cell in row if cell)
        if not classified and not category_header:
            continue
        for index, row in enumerate(table["cells"]):
            labels = [clean(cell) for cell in row if cell and _CLASSIFIED_ROW.fullmatch(clean(cell))]
            if len(labels) != 1:
                continue
            category = "_".join(word.upper() for word in ("measured", "indicated", "inferred")
                                if re.search(r"\b" + word + r"\b", labels[0], re.I))
            row_source = {**source, "scope": caption, "category": category or None,
                          "statement_kind": "MINERAL_RESOURCE" if category_header else None, "basis": "TREO"}
            for quantity in ("ore_mt", "grade", "contained_treo_kt"):
                row_source["target_variable"] = quantity
                witnesses = _table_witnesses(row_source, tables, blocks, (), (),
                                             location=(table["table_index"], index), caption_witness=caption_witness)
                for native, anchors in witnesses:
                    captures.append({"native": native, "anchors": anchors, "context": _context(row_source, anchors)})
    for quantity in ("ore_mt", "grade"):
        row_source = {**source, "target_variable": quantity, "statement_kind": "MINERAL_RESOURCE", "basis": "TREO"}
        for native, anchors in _narrative_witnesses(row_source, blocks, None):
            captures.append({"native": native, "anchors": anchors, "context": _context(row_source, anchors)})
    return captures


def _cell_key(record):
    anchor = next((a for a in record["anchors"] if a["field"] == "token" and "column" in a), None)
    if anchor:
        return tuple(anchor[k] for k in ("source_sha256", "page", "table_index", "row", "column"))
    return None


def _quote(record, field):
    return " ".join(a["quote"] for a in record["anchors"] if a["field"] == field)


def _can_round_to_same_value(left, right):
    first, second = _decimal(left["token"]), _decimal(right["token"])
    if first is None or second is None or left["unit"] != right["unit"] or first == second:
        return False
    half_first = abs(Decimal(5).scaleb(first.as_tuple().exponent - 1))
    half_second = abs(Decimal(5).scaleb(second.as_tuple().exponent - 1))
    return abs(first - second) <= half_first + half_second


def _references_table(left, right):
    if any(left[k] != right[k] for k in ("source_sha256", "physical_page")):
        return False
    for prose, table in ((left, right), (right, left)):
        caption = CAPTION.search(_quote(table, "scope"))
        if caption and re.search(r"\b(?:summaris(?:ed|es)|summariz(?:ed|es)|shown|presented)"
                                 r"\s+in\s+Table\s+" + re.escape(caption[1]) + r"\b",
                                 _quote(prose, "estimate_reference"), re.I):
            return True
    return False


def _relation(left, right):
    a, b = left["context"], right["context"]
    cell = _cell_key(left)
    if cell and cell == _cell_key(right) and left["native"] == right["native"]:
        return "SAME_REPORTED_CELL", "CONFIRMED", [], []
    supported, missing = [], []
    for field in ("scope", "category", "estimate_date", "cutoff", "chemical_basis", "material", "denominator"):
        x, y = a[field], b[field]
        if not x or not y:
            missing.append(field)
        elif x == y:
            supported.append(field)
    if (a["category"] == b["category"] and a["chemical_basis"] == b["chemical_basis"]
            and a["material"] == b["material"] and a["denominator"] == b["denominator"]
            and _references_table(left, right) and _can_round_to_same_value(left["native"], right["native"])):
        return "SAME_ESTIMATE_ROUNDING_ONLY", "REVIEW_REQUIRED", [*supported, "explicit_table_reference"], missing
    left_scope, right_scope = _quote(left, "scope"), _quote(right, "scope")
    if left_scope and right_scope and (
        a["cutoff"] and b["cutoff"] and a["cutoff"] != b["cutoff"]
    ):
        return "POSSIBLE_DIFFERENT_RESOURCE_SCOPE", "REVIEW_REQUIRED", supported, missing
    if ({"scope", "category", "estimate_date", "cutoff", "chemical_basis"} <= set(supported)
            and left["source_sha256"] != right["source_sha256"]
            and any(re.search(r"\b(?:reprint(?:ed)?|previously reported|originally announced|restat(?:ed|ement))\b", q["quote"], re.I)
                    for d in (left, right) for q in d["anchors"] if q["field"] in {"scope", "estimate_reference"})):
        kind = "REPRINTS_SAME_ESTIMATE" if left["native"] == right["native"] else "POSSIBLE_SAME_ESTIMATE_DIFFERENT_PRECISION"
        return kind, "REVIEW_REQUIRED", supported, missing
    return "UNRESOLVED_ESTIMATE_RELATION", "REVIEW_REQUIRED", supported, missing


def resource_relations(observations):
    """Propose relations within a confirmed Project and a single quantity kind."""
    grouped = defaultdict(list)
    for r in observations:
        if r["status"] == "EXTRACTED" and r["project_id"]:
            grouped[r["project_id"], r["native"]["quantity"]].append(r)
    relations = []
    for (project, quantity), members in sorted(grouped.items()):
        for left, right in combinations(sorted(members, key=lambda r: r["candidate_id"]), 2):
            kind, status, shared, missing = _relation(left, right)
            ids = left["candidate_id"], right["candidate_id"]
            relations.append({"relation_id": digest([VERSION, *ids]), "candidate_ids": list(ids),
                              "project_id": project, "quantity": quantity, "relation": kind, "status": status,
                              "supported_constraints": shared, "missing_constraints": missing,
                              "conflicts": [k for k in ("scope", "category", "estimate_date", "cutoff", "chemical_basis")
                                            if left["context"][k] and right["context"][k]
                                            and left["context"][k] != right["context"][k]],
                              "sides": [{k: r[k] for k in ("candidate_id", "source_sha256", "physical_page", "anchors", "context", "native")}
                                        for r in (left, right)], "version": VERSION})
    return relations
