"""Re-read physical resource rows eligible for automatic admission checks."""

from collections import defaultdict
from contextlib import nullcontext
from datetime import date
from decimal import Decimal
from pathlib import Path
import re

from .document_processing import DocumentUnavailable, PdfDocumentCache
from .normalization import MASS_FRACTION, MASS_FRACTION_UNIT_PATTERN, RESOURCE_CUTOFF_ANALYTE, date_precision, unit_factor
from .numeric_evidence import numeric_token_spans, scalar_decimal
from .observation_pipeline import raw_from_candidate
from .observation_schema import value_evidence_issue
from .pdf_extract import _matches
from .resource_discourse import clause_spans, changes_estimate_subject, older_estimate, other_estimate
from .resource_estimate import cutoff_signature, normalize_cutoff
from .resource_jorc import (
    VERSION as JORC_VERSION, SCOPE_TO_ROLE, estimate_heading, evaluate as assess_jorc, scope_stem, section_matches,
    table_numbers,
)
from .resource_table_layout import (
    FRACTION_DENOMINATOR, FRACTION_MATERIAL, co_commodity_summary, composite_grade_basis, fraction_grade_summary,
    has_resource_value_row, particle_size, row_quantities,
)
from .semantic_resource import (
    CAPTION, CUTOFF, ESTIMATE_DATE, GRADE_PHRASE, MONTHS, RISKY, _CLASSIFIED_ROW, _anchors, _header_unit,
    clean, column_header_anchors, located_column_headers, page_table_caption,
)
from .store import digest
from .technical_tables import cells


VERSION = "native-resource-row-v6"
_VARIABLES = ("ore_mt", "grade", "contained_treo_kt")
_RESOURCE = re.compile(r"\b(?:mineral resources?|resource estimate|MRE)\b", re.I)
_TABLE_PROSE = re.compile(r"^table\s+\d+(?:[-.]\d+)*\s+(?:(?:above|below)\s+)?"
                         r"(?:is|are|was|were|has|had|does|contains?|includes?|lists?|presents?|shows?|"
                         r"summari[sz]es?|sets?\s+out|compares?|provides?|records?|gives?)\b", re.I)
_TOTAL = re.compile(r"(?:(?:grand|global|project|combined)\s+)?total(?:\s*\(\d+\))?", re.I)
_CATEGORY = re.compile(r"\b(measured|indicated|inferred)\b", re.I)
_CLASSIFICATION = re.compile(r"(?:JORC\s+)?(?:category|classification|resource classification)", re.I)
_CLASSIFICATION_ASSIGNMENT = re.compile(r"\b(?:classified|reported|assigned(?:\s+a\s+classification\s+of)?|classification\s+(?:is|of))"
                                        r"\s*(?:(?:as|in|to)\s+)?(?:entirely\s+)?(?:measured|indicated|inferred)\b", re.I)
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
_CUTOFF_COLUMN = re.compile(
    rf"cut[- ]?off\s*\(\s*(?:(?P<basis_first>{RESOURCE_CUTOFF_ANALYTE})\s*(?P<unit_last>{MASS_FRACTION_UNIT_PATTERN})|"
    rf"(?P<unit_first>{MASS_FRACTION_UNIT_PATTERN})\s*(?P<basis_last>{RESOURCE_CUTOFF_ANALYTE}))\s*\)", re.I,
)
_CUTOFF_COMPARISON = re.compile(r"(?P<operator>>=|<=|[≥≤><=]|\bat least|\bat most|\babove|\bbelow|\bgreater than|\bless than)"
                                r"(?:\s+(?:an?|the))?\s*$", re.I)
_CUTOFF_MARKER = re.compile(r"\bcut[- ]?off(?:\s+grade)?\s+(?:(?:of|is|was)\s+)?(?:[:=]\s*)?"
                            r"(?P<operator>>=|<=|[≥≤><=])?\s*(?P<x>[0-9][0-9,.]*)\s*"
                            rf"(?P<u>{MASS_FRACTION_UNIT_PATTERN})\s*(?P<b>{RESOURCE_CUTOFF_ANALYTE})", re.I)
_CUTOFF_CELL = re.compile(r"(?P<operator>>=|<=|[≥≤><=])?\s*(?P<x>[0-9][0-9,.]*)\Z")
_REVERSE_CUTOFF = re.compile(rf"\b(?P<b>{RESOURCE_CUTOFF_ANALYTE})\s+cut[- ]?off(?:\s+grade)?\s*(?:of|is|was)\s+"
                            rf"(?P<operator>>=|<=|[≥≤><=])?\s*(?P<x>[\d,.]+)\s*(?P<u>{MASS_FRACTION_UNIT_PATTERN})(?!\w)", re.I)
_CUTOFF_SUBSCRIPTS = str.maketrans("₂₃₅", "235")
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
_EFFECTIVE_PERIOD = re.compile(rf"\b(?:as\s+at|effective(?:\s+date)?(?:\s*of)?)\s+"
                               rf"(?P<date>{_MONTH}\s+20\d{{2}}|20\d{{2}}-\d{{2}})\b(?!-\d)", re.I)
_EDITION_NAME = r"(?:mineral resource(?:s| estimates?| summary)*|resource estimates?|MRE)"
_CAPTION_EDITION_PERIOD = re.compile(
    rf"(?:\b{_EDITION_NAME}[\s–—:,-]+(?P<after>{_MONTH}\s+20\d{{2}})\b|"
    rf"\b(?P<before>{_MONTH}\s+20\d{{2}})\s+{_EDITION_NAME}\b)", re.I,
)
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
_POTENTIAL_BYPRODUCT = re.compile(
    r"\b(?:TREO|REE|REO|rare earth oxides?)\b[^.;!?]{0,180}\b(?:potential|possible)\s+by[- ]?product\b", re.I,
)
_MATERIAL_TOPIC = re.compile(r"^\s*(?:(?:for|regarding|as to|with respect to)\s+)?(?:the\s+)?"
                             r"(?:concentrates?|tailings?|stockpiles?|fine fraction|coarse fraction|bulk ore|"
                             r"(?:fine|coarse|screened|sieved|processed) material|[+−–-]\s*\d+\s*[µμu]m)\b", re.I)
_SUBAREA_TOPIC = re.compile(r"^\s*(?:for|in|within|at|regarding|with respect to)\s+(?:the\s+)?"
                            r"(?:[\w'-]+\s+){0,4}(?:zone|block|domain|pit|subset|portion|subarea|sub-area)\b", re.I)
_SCOPE_INTRO = re.compile(r"^(?:summary of|estimate for)\s+(?:the\s+)?", re.I)
_SHORT_RESOURCE_TITLE = re.compile(r"^(?P<scope>[\w -]+?)\s+resources?\s+(?:at|as adjusted for)\b", re.I)
_CUTOFF_SCENARIOS = re.compile(r"\b(?:at\s+various|as\s+adjusted\s+for\s+different)\b[^.!?;]{0,70}\bcut[- ]?offs?\b", re.I)
_NAMED_DOMAIN = re.compile(r"\bwithin\s+(?:the\s+)?([\w-]+)\s+domain\b", re.I)
_MATERIAL_COLUMN = re.compile(r"(?:geology|material(?: type)?|ore type)", re.I)
_MATERIAL_ROWS = frozenset({"oxide", "fresh"})


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
        result.update(period for match in _EFFECTIVE_PERIOD.finditer(text)
                      if (period := _normalized_month(match['date'])) is not None)
    return result


def _normalized_month(literal):
    if (month := _PERIOD.fullmatch(literal)) is not None:
        literal = f"{month[2]}-{MONTHS.index(month[1][:3].lower()) + 1:02d}"
    return literal if date_precision(literal) == "MONTH" else None


def caption_estimate_periods(caption):
    """Locate dated estimate labels in a title without treating publication dates as effective dates."""
    for match in _CAPTION_EDITION_PERIOD.finditer(caption):
        group = "before" if match["before"] else "after"
        yield _normalized_month(match[group]), match.span(group), "ESTIMATE_EDITION_DATE"
    for match in _EFFECTIVE_PERIOD.finditer(caption):
        if (period := _normalized_month(match["date"])) is not None:
            yield period, match.span("date"), "STATEMENT_EFFECTIVE_DATE"


def resolved_estimate_date(dates):
    """Allow one located exact day to refine a corroborating month from the same estimate."""
    if len(dates) == 1:
        return next(iter(dates))
    days = {day for day in dates if date_precision(day) == "DAY"}
    if len(days) == 1:
        day = next(iter(days))
        if dates == {day, day[:7]}:
            return day
    return None


def _cutoff(texts):
    declarations = {}
    for text in texts:
        printable = text.translate(_CUTOFF_SUBSCRIPTS)
        for m in [*CUTOFF.finditer(printable), *_CUTOFF_MARKER.finditer(printable), *_REVERSE_CUTOFF.finditer(printable)]:
            if m.re is CUTOFF:
                leading = _CUTOFF_COMPARISON.search(text[:m.start()])
                operator = leading["operator"].casefold() if leading else None
                original = text[leading.start() if leading else m.start():m.end()]
            else:
                operator = m["operator"]
                leading = _CUTOFF_COMPARISON.search(text[:m.start()])
                if leading and not operator:
                    operator = leading["operator"].casefold()
                original = text[leading.start() if leading else m.start():m.end()]
            declared = {"value": m["x"], "unit": m["u"].lower(), "basis": m["b"].upper(),
                        "operator": _COMPARISONS.get(operator, operator), "text": original}
            if normalized := normalize_cutoff(declared):
                declared["basis"] = normalized["basis"]
                declarations.setdefault(cutoff_signature(normalized), declared)
    return declarations


def cutoff_column_declaration(header, token):
    """Read a threshold only from a located matching cut-off header and cell."""
    column = _CUTOFF_COLUMN.fullmatch(header.translate(_CUTOFF_SUBSCRIPTS))
    value = _CUTOFF_CELL.fullmatch(token.strip())
    if not column or not value:
        return None
    declared = {"value": value["x"], "unit": (column["unit_first"] or column["unit_last"]).lower(),
                "basis": column["basis_first"] or column["basis_last"], "operator": value["operator"], "text": token}
    if normalized := normalize_cutoff(declared):
        return cutoff_signature(normalized), {**declared, "basis": normalized["basis"]}
    return None


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
    factors = {"t": 1, "kt": 1_000, "mt": 1_000_000, "million tonnes": 1_000_000, "m tonnes": 1_000_000,
               **{unit: unit_factor(unit, "ppm", MASS_FRACTION) for unit in MASS_FRACTION}}

    def agrees(printed, unit, witness, witness_unit):
        value, stated = scalar_decimal(printed, unit), scalar_decimal(witness, witness_unit)
        factor = factors.get(unit.casefold())
        witness_factor = factors.get(witness_unit.casefold())
        if value is None or stated is None or factor is None or witness_factor is None:
            return False
        half_place = Decimal(5).scaleb(value.as_tuple().exponent - 1)
        return abs(stated * witness_factor - value * factor) <= half_place * factor

    phrases = list(_REPORT_GRADE_PHRASE.finditer(quote))
    if len(phrases) != 1:
        return False
    phrase = phrases[0]
    return all(agrees(located[field][0][0]["text"], located[field][0][1], phrase[name], phrase[f"{name}_unit"])
               for field, name in (("ore_mt", "mass"), ("grade", "grade")))


def _subject_regions(quote):
    """Separate independently scoped assertions while retaining original offsets."""
    region_start = region_end = 0
    for start, end in clause_spans(quote):
        clause = quote[start:end]
        if region_end > region_start and (changes_estimate_subject(clause, quote[region_start:region_end])
                                           or _MATERIAL_TOPIC.match(clause) or _SUBAREA_TOPIC.match(clause)):
            yield region_start, region_end
            region_start = start
        region_end = end
    if region_end > region_start:
        yield region_start, region_end


def locally_bound_span(quote, table, project, registry):
    """Keep only the initial subject of a physically bound table note."""
    for start, end in _subject_regions(quote):
        text = quote[start:end]
        if (table_numbers(text) - {table} or older_estimate(text) or other_estimate(text) or _MATERIAL_TOPIC.match(text)
                or _SUBAREA_TOPIC.match(text)
                or any(item['entity_id'] != project for item in _matches(text, registry))):
            return None
        return start, end
    return None


def _context_spans(quote, relation, scope, table, declared_dates, periods, located, *, allowed=lambda text: True):
    """Locate regions that have an independent identity link to the target estimate."""
    matches = []
    for start, end in _subject_regions(quote):
        text = quote[start:end]
        if (older_estimate(text) or other_estimate(text) or _MATERIAL_TOPIC.match(text)
                or _SUBAREA_TOPIC.match(text) or not allowed(text)):
            continue
        names = table_numbers(text)
        dates = _effective_dates((text,))
        if relation == _MATCHED_TABLE:
            if (not table or names != {table} or not _scope_is_named(scope, text) or not _RESOURCE.search(text)
                    or dates and resolved_estimate_date(dates) is None
                    or (dates and declared_dates and resolved_estimate_date(dates | declared_dates) is None)):
                continue
            bound = bool(dates and dates == declared_dates) or _row_values_match(text, located)
        elif relation == _MATCHED_PERIOD:
            days = _estimate_dates_in_context(text, relation)
            bound = (not names and _RESOURCE.search(text) and not RISKY.search(text) and len(days) == len(periods) == 1
                     and any(tuple(map(int, day[:7].split("-"))) in periods for day in days)
                     and _row_values_match(text, located))
        else:
            bound = relation == _MATCHED_FOOTNOTE and bool(_MARKED_TREO.search(text))
        if bound:
            matches.append((start, end))
    return tuple(matches)


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
    if duplicate_label:
        return

    def no_foreign_project(text):
        return all(item["entity_id"] == project for item in _matches(text, registry))

    for number, page_blocks in sorted(pages.items()):
        named_reporting_period = any(_scope_is_named(scope, quote) and _RESOURCE.search(quote) for _, quote in page_blocks)
        for box, quote in page_blocks:
            if not 0 < len(quote) <= 1800 or (CAPTION.match(quote) and not _TABLE_PROSE.match(quote)):
                continue
            spans = _context_spans(quote, _MATCHED_TABLE, scope, reported_table, declared_dates,
                                   period_matches, located, allowed=no_foreign_project)
            if spans:
                yield number, box, quote, _MATCHED_TABLE, spans
            elif number != page and named_reporting_period and len(period_matches) == 1:
                spans = _context_spans(quote, _MATCHED_PERIOD, scope, reported_table, declared_dates,
                                       period_matches, located, allowed=no_foreign_project)
                if spans:
                    yield number, box, quote, _MATCHED_PERIOD, spans


def _nearby_marked_treo(page, table, tables, blocks, header_text):
    if not re.search(r"\bTREO\s*\*", header_text, re.I):
        return ()
    found = [(page, box, quote, _MATCHED_FOOTNOTE) for box, quote in blocks if _MARKED_TREO.search(quote)
             and table["bbox"][3] - 25 <= box[1] <= table["bbox"][3] + 28
             and not any(other is not table and other["bbox"][1] < box[3] and other["bbox"][3] > box[1]
                         for other in tables)]
    if len(found) != 1:
        return ()
    source_page, box, quote, relation = found[0]
    spans = _context_spans(quote, relation, None, None, (), (), {})
    return ((source_page, box, quote, relation, spans),) if spans else ()


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
                                                or _BULK.search(text) or _DRY_METHOD.search(text) or _WET_METHOD.search(text)
                                                or _CLASSIFICATION_ASSIGNMENT.search(text))):
            notes.append((box, text))
    return context, notes


def _registered_scope_aliases(registry):
    """Recognize exact named scopes already declared in the existing Project registry."""
    result = []
    for project in registry:
        aliases = set(project.get("aliases", ()))
        scope_only = set(project.get("scope_only_aliases", ()))
        if annotated := _SCOPE_ALIAS.search(project.get("name", "")):
            name = re.sub(r"\s+(?:mineral\s+)?resource$", "", annotated[1], flags=re.I)
            scope_only.update((annotated[1], name, re.sub(r"(?<=[A-Za-z])(?=\d)", " ", name)))
        if aliases:
            result.append(dict(project, aliases=sorted(aliases | scope_only), scope_only_aliases=sorted(scope_only)))
    return result


def _layout_note_chain(page, caption_entry, table_label, project, registry, located, supporting_pages):
    """Locate a table-linked note or the same physical estimate's repeated presentation."""
    box, caption = caption_entry
    result = []
    for number, blocks in sorted(supporting_pages.items()):
        captions = [(bounds, text) for bounds, text in blocks if text == caption]
        if number == page:
            captions = [(box, caption)]
        if len(captions) != 1:
            continue
        heading, _ = captions[0]
        if number != page:
            row_tokens = [re.escape(located[key][0][0]["text"].strip()) for key in ("ore_mt", "grade")
                          if len(located[key]) == 1]
            same_values = any(0 <= bounds[1] - heading[3] <= 65 and len(row_tokens) == 2
                              and all(re.search(r"(?<![\w.,])" + token + r"(?![\w.,])", text)
                                      for token in row_tokens)
                              for bounds, text in blocks)
            same_headers = any(0 <= bounds[1] - heading[3] <= 45 and re.search(r"\btonnage\b", text, re.I)
                               and re.search(r"\bTREO\b", text, re.I) for bounds, text in blocks)
            if not (same_values and same_headers):
                continue
        for bounds, quote in blocks:
            span = locally_bound_span(quote, table_label, project, registry)
            if span and co_commodity_summary(quote[slice(*span)], located["ore_mt"], located["grade"]):
                result.append((number, bounds, quote, span, "MATCHED_COMMODITY_ROW_VALUES"))
        before = [(bounds, text) for bounds, text in blocks if 0 <= heading[1] - bounds[3] <= 220
                  and bounds[0] <= heading[2] and bounds[2] >= heading[0]]
        before.sort(key=lambda item: (item[0][1], item[0][0]))
        if not before:
            continue
        bridge, bridge_text = before[-1]
        bridge_span = locally_bound_span(bridge_text, table_label, project, registry)
        if (heading[1] - bridge[3] > 65 or table_numbers(bridge_text) != {table_label}
                or not _RESOURCE.search(bridge_text) or not bridge_span):
            continue
        references = []
        for bounds, text in reversed(before[:-1][-2:]):
            span = locally_bound_span(text, table_label, project, registry)
            if not span or not 0 <= bridge[1] - bounds[3] <= 20 or table_numbers(text):
                break
            # Keep the note's original physical text and locator. The bridge
            # expressly identifies the table, and no other estimate may intervene.
            if _POTENTIAL_BYPRODUCT.search(text[slice(*span)]) or _cutoff((text[slice(*span)],)):
                references.append((number, bounds, text, span, "ADJACENT_NAMED_TABLE_NOTE_CHAIN"))
            bridge = bounds
        if references:
            result.append((number, before[-1][0], bridge_text, bridge_span, "NAMED_TABLE_NOTE_BRIDGE"))
            result.extend(references)
    return result


def _fraction_row(row, table, located, all_values, supporting_pages, project, registry, table_label):
    fraction_mass, bulk_mass = all_values["fraction_mass"], all_values["bulk_ore_mt"]
    grade_markers = [(piece, size) for _, _, headers in located["grade"] for piece in headers
                     if (size := particle_size(piece["text"]))]
    if not (fraction_mass or grade_markers):
        return None, (), ()
    if not fraction_mass:
        located["ore_mt"] = []
        issues = ("RESOURCE_PARTICLE_SIZE_FRACTION_NOT_COMPARABLE", "RESOURCE_PARTICLE_SIZE_FRACTION_MASS_UNBOUND")
        marks = {(size["operator"], size["value"]) for _, size in grade_markers}
        grade_witnesses = tuple(_cell_anchor("particle_size", row, table, piece) for piece, _ in grade_markers)
        return (grade_markers[0][1] if len(marks) == 1 else None), grade_witnesses, issues
    if len(fraction_mass) != 1:
        located["ore_mt"] = []
        return None, (), ("RESOURCE_PARTICLE_SIZE_FRACTION_AMBIGUOUS",)
    _, _, pieces = fraction_mass[0]
    size_headers = [part for part in pieces if particle_size(part["text"])]
    if not size_headers:
        located["ore_mt"] = []
        return None, (), ("RESOURCE_PARTICLE_SIZE_FRACTION_HEADER_UNBOUND",)
    size = particle_size(size_headers[0]["text"])
    quantity_witnesses = [_cell_anchor("particle_size", row, table, part) for part in size_headers]
    for number, blocks in sorted(supporting_pages.items()):
        named = [hit["entity_id"] for _, text in blocks for hit in _matches(text, registry)]
        if project is None or set(named) != {project}:
            continue
        for box, quote in blocks:
            span = locally_bound_span(quote, table_label, project, registry)
            if span and fraction_grade_summary(quote[slice(*span)], bulk_mass or fraction_mass, located["grade"], size):
                quantity_witnesses.append(_resource_context_anchor("fraction_grade_basis", row, number, box, quote,
                                                                  "NAMED_REPORT_AND_MATCHED_FRACTION_VALUES",
                                                                  start=span[0], end=span[1]))
    explicit_grade_sizes = {(marker["operator"], marker["value"]) for _, marker in grade_markers}
    header_binds_grade = explicit_grade_sizes == {(size["operator"], size["value"])}
    issues = ["RESOURCE_PARTICLE_SIZE_FRACTION_NOT_COMPARABLE"]
    if header_binds_grade or (not explicit_grade_sizes and len(quantity_witnesses) > len(size_headers)):
        located["ore_mt"] = fraction_mass
    else:
        located["ore_mt"] = []
        issues.append("RESOURCE_PARTICLE_SIZE_FRACTION_GRADE_UNBOUND")
    return size, tuple(quantity_witnesses), tuple(issues)


def _scope(caption, registry):
    title = _SCOPE_INTRO.sub("", CAPTION.sub("", caption, count=1))
    explicit = _SCOPE_AFTER.match(title)
    marker = _SCOPE_END.search(title)
    short = _SHORT_RESOURCE_TITLE.match(title)
    label = (explicit[1] if explicit else title[:marker.start()] if marker else short["scope"] if short else "")
    label = re.sub(rf"\s+{_MONTH}\s+20\d{{2}}$", "", label.strip(" :-–—,;"), flags=re.I)
    domain = _NAMED_DOMAIN.search(title)
    if domain and label:
        label = f"{label} / {domain[1]} domain"
    hits = _matches(label, registry) if label else []
    # Short pre-registered scope names require an exact caption subject; the
    # broader document alias scan deliberately ignores three-character words.
    if short and not hits:
        hits = [project for project in registry if label.casefold() in {
            alias.casefold() for alias in project.get("scope_only_aliases", ())}]
    caption_ids = {p["entity_id"] for p in _matches(caption, registry)}
    if len(hits) != 1 or caption_ids - {hits[0]["entity_id"]} or (not caption_ids and not short):
        return None, label or None, False, False
    plain = _SCOPE_SUFFIX.sub("", label).casefold()
    declared = {name.casefold() for name in (*hits[0]["aliases"], hits[0].get("name", ""))}
    scope_only = {name.casefold() for name in hits[0].get("scope_only_aliases", ())}
    names = {label.casefold(), plain}
    return hits[0]["entity_id"], label, bool(names & (declared - scope_only)), bool(names & scope_only)


def _caption_lines(words):
    """Positioned lines can separate a caption from a PDF block merged with headers."""
    lines = defaultdict(list)
    for word in words:
        lines[tuple(word[5:7])].append(word)
    for line in lines.values():
        quote = clean(" ".join(word[4] for word in sorted(line, key=lambda word: word[0])))
        if CAPTION.match(quote) and not _TABLE_PROSE.match(quote):
            yield [min(word[0] for word in line), min(word[1] for word in line),
                   max(word[2] for word in line), max(word[3] for word in line)], quote


def _resource_caption(tables, table, blocks, lines):
    caption = page_table_caption(tables, table, [(box, text) for box, text in blocks if not _TABLE_PROSE.match(text)])
    if caption or not lines:
        return caption
    # Only separate a caption line from its own physically overlapping block.
    top = table["bbox"][1]
    merged = [(box, quote) for box, quote in blocks if box[1] < top < box[3] and CAPTION.match(quote)]
    return page_table_caption(tables, table, [(box, quote) for box, quote in lines if any(
        bounds[0] - .1 <= box[0] and bounds[1] - .1 <= box[1] < top < bounds[3]
        and original.startswith(quote + " ") for bounds, original in merged)])


def _caption_section(caption, scope, blocks, tables, table, project, registry):
    """Associate a classified heading only with its next named estimate table."""
    box, _ = caption
    prior = max((item["bbox"][3] for item in tables if item["bbox"][3] < box[1]), default=0)
    matches = [(bounds, quote) for bounds, quote in blocks if prior <= bounds[1] < bounds[3] <= box[1]
               and box[1] - bounds[3] <= 10 and bounds[3] - bounds[1] <= 22
               and table["bbox"][0] - 30 <= bounds[0] <= box[0] + 10
               and _scope_is_named(scope, quote) and _CATEGORY.search(quote)
               and re.search(r"\bresources?\s*[.]?$", quote, re.I) and not RISKY.search(quote)
               and not older_estimate(quote) and not other_estimate(quote)
               and not any(item["entity_id"] != project for item in _matches(quote, registry))
               and not _TABLE_PROSE.match(quote) and not CAPTION.match(quote)]
    return matches[0] if len(matches) == 1 else None


def _contained_from_blocks(row_cells, headers, blocks, table):
    """Recover one contained-oxide column when native header text crosses its border."""
    top = table["bbox"][1]
    owned = []
    for cell in row_cells:
        left, _, right, _ = cell["bbox"]
        _, pieces = _column_parts(cell, headers)
        if not pieces or not any(re.search(r"\bcontained\b", piece["text"], re.I) for piece in pieces):
            continue
        bottom = max(piece["bbox"][3] for piece in pieces)
        blocks_in_column = sorted(((bounds, quote) for bounds, quote in blocks if (
            left <= bounds[0] < bounds[2] <= right and top - .1 <= bounds[1] < bounds[3] <= bottom + .5)),
            key=lambda entry: (entry[0][1], entry[0][0]))
        header = " ".join(quote for _, quote in blocks_in_column)
        if unit := _header_unit(header, "contained_treo_kt", native=True):
            physical_headers = [dict(row=pieces[0]["row"], column=cell["column"], bbox=bounds, text=quote)
                                for bounds, quote in blocks_in_column]
            owned.append((cell, unit, physical_headers))
    return owned if len(owned) == 1 else []


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
    factors = {"t": 1, "kt": 1000, "mt": 10**6, "million tonnes": 10**6, "m tonnes": 10**6,
               **{unit: unit_factor(unit, "ppm", MASS_FRACTION) for unit in MASS_FRACTION}}

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
    return quantities == tuple(value(located[key][0][0]["text"], located[key][0][1]) for key in _VARIABLES)


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
    bound_locations = {(number, tuple(box), quote): spans for number, box, quote, relation, spans in bound_context
                       if number != page and relation == _MATCHED_TABLE}
    for (number, box, quote), spans in sorted(bound_locations.items()):
        collect(number, list(box), quote, "BOUND_ESTIMATE_CONTEXT", bound_spans=spans)
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
    anchors.extend(_anchors("jorc_discourse_context", {**row, "physical_page": block["physical_page"]}, block["quote"],
                            bbox=block["bbox"], table_index=block.get("table"), row=block.get("row"),
                            column=block.get("column"), locator=block["origin"])
                   for block in assessment["discourse_context"])
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


def _typed(source, row, table, cell, quantity, unit, pieces, context, witnesses, *, row_cells):
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
    heading = column_header_anchors(row, table, pieces, unit, value_cell=cell, row_cells=row_cells)
    anchor_list = [first, *heading, *witnesses]
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
    elif scalar < 0 or quantity in {"grade", "grade_treosc"} and scalar > (100 if unit == "%" else 1_000_000):
        issue = issue or "RESOURCE_VALUE_OUT_OF_RANGE"
    return observation, issue


def _context_fields(text, relation, scope):
    """Derive field locations and their values within one bound subject region."""
    fields = {}
    dates, cutoffs = set(), {}
    for start, end in clause_spans(text):
        clause = text[start:end]
        if relation != _MATCHED_FOOTNOTE and (found_dates := _estimate_dates_in_context(clause, relation)):
            dates |= found_dates
            fields.setdefault("effective_date", []).append((start, end))
        if relation == _MATCHED_TABLE and (found_cutoffs := _cutoff((clause,))):
            cutoffs.update(found_cutoffs)
            fields.setdefault("cutoff_grade", []).append((start, end))
    wet = relation == _MATCHED_TABLE and bool(_WET_METHOD.search(text))
    if relation == _MATCHED_TABLE:
        if match := _DRY_METHOD.search(text):
            fields["material_basis"] = fields["denominator_basis"] = [match.span()]
        if match := _documented_extent(scope, text):
            fields["scope_coverage"] = [match.span()]
    if match := (_MARKED_TREO if relation == _MATCHED_FOOTNOTE else _CHEMICAL).search(text):
        fields["chemical_basis"] = [match.span()]
    return fields, dates, cutoffs, wet, bool(_EXCLUDED_OXIDE.search(text))


def _bound_field_witnesses(row, scope, bound_context):
    """Keep the original physical block with exact bound subject and field spans."""
    identities, fields, dates, cutoffs = [], {}, set(), {}
    wet, excluded = False, False
    for number, bbox, quote, relation, spans in bound_context:
        for start, end in spans:
            identities.append(_resource_context_anchor("estimate_identity_reference", row, number, bbox, quote, relation,
                                                     start=start, end=end))
            locations, extra_dates, extra_cutoffs, scope_wet, scope_excluded = _context_fields(quote[start:end], relation, scope)
            for field, locations_in_region in locations.items():
                fields.setdefault(field, []).extend(
                    _resource_context_anchor(_CONTEXT_ROLES[field], row, number, bbox, quote, relation,
                                             start=start + left, end=start + right)
                    for left, right in locations_in_region)
            dates |= extra_dates
            cutoffs.update(extra_cutoffs)
            wet |= scope_wet
            excluded |= scope_excluded
    return identities, fields, dates, cutoffs, wet, excluded


def verified_context_anchors(observations, registry=()):
    """Verify the same-estimate linkage for typed contextual field witnesses."""
    first = observations[0]
    source = (first.evidence.sha256, first.evidence.source_id)
    anchors = [anchor for anchor in first.evidence_anchors if (anchor.sha256, anchor.source_id) == source
               and anchor.page and anchor.bbox and anchor.quote and anchor.text_span]
    props = dict(first.context.conditions)
    caption = next((anchor.quote for anchor in first.evidence_anchors if anchor.role == "scope"
                    and (anchor.sha256, anchor.page, anchor.table) == (source[0], first.evidence.page, first.evidence.table)), "")
    scope_dates = _effective_dates((caption,)) | {value for value, _, _ in caption_estimate_periods(caption)}
    table_label = props.get("reported_table_label")
    periods = {(int(match[2]), MONTHS.index(match[1][:3].lower()) + 1) for match in _PERIOD.finditer(caption)}
    registry = _registered_scope_aliases(registry)
    located = {field: [] for field in ("ore_mt", "grade")}
    for item in observations:
        if item.variable in located:
            located[item.variable].append(({"text": item.original_value}, item.original_unit, ()))

    def key(anchor):
        return anchor.page, anchor.bbox, anchor.quote, anchor.locator

    def no_foreign_project(text):
        return all(item["entity_id"] == first.project_id for item in _matches(text, registry))

    verified = set()
    for identity in (anchor for anchor in anchors if anchor.role == "estimate_identity_reference"
                     and anchor.locator in _CONTEXT_RELATIONS):
        relation = identity.locator
        if relation == _MATCHED_PERIOD and not any(
                witness.role == "estimate_report_scope" and witness.page == identity.page
                and _scope_is_named(first.scope_id, witness.quote) and _RESOURCE.search(witness.quote)
                for witness in anchors):
            continue
        if relation == _MATCHED_FOOTNOTE and (identity.page != first.evidence.page or not any(
                item.variable == "grade" and any(header.role == "unit" and "TREO*" in header.quote.upper().replace(" ", "")
                for header in item.evidence_anchors if header.quote) for item in observations)):
            continue
        spans = _context_spans(identity.quote, relation, first.scope_id, table_label, scope_dates, periods, located,
                               allowed=no_foreign_project)
        if identity.text_span.in_quote not in spans:
            continue
        start, end = identity.text_span.in_quote
        fields, _, _, _, _ = _context_fields(identity.quote[start:end], relation, first.scope_id)
        verified.update((key(identity), _CONTEXT_ROLES[field], (start + left, start + right))
                        for field, locations in fields.items() for left, right in locations)
    selected = [anchor for anchor in anchors if (key(anchor), anchor.role, anchor.text_span.in_quote) in verified]
    # All observation tokens must carry the same proof set for this estimate.
    if any(not set(selected).issubset(set(item.evidence_anchors)) for item in observations):
        return ()
    return tuple(selected)


def _table_rows(source, registry, page, table, tables, blocks, supporting_pages, method_pages, table_label_pages,
                caption_lines):
    native = cells(table)
    # "Table 2 presents ..." is a reference in prose. It can bind a following
    # proposition but must not compete with the table's structural title.
    caption_entry = _resource_caption(tables, table, blocks, caption_lines)
    caption = caption_entry[1] if caption_entry else ""
    project, scope, extent_bound, annotated_scope = _scope(caption, registry)
    short_title = _SHORT_RESOURCE_TITLE.match(_SCOPE_INTRO.sub("", CAPTION.sub("", caption, count=1)))
    linked_section = _caption_section(caption_entry, scope, blocks, tables, table, project, registry) if caption_entry else None
    cutoff_scenarios = bool(_CUTOFF_SCENARIOS.search(caption) and (linked_section or short_title and project))
    declared_resource = bool(_RESOURCE.search(caption) or linked_section or cutoff_scenarios)
    body = {}
    for cell in native:
        body.setdefault(cell["row"], []).append(cell)
    numeric_rows = {index for index, members in body.items()
                    if any(scalar_decimal(cell["text"], None) is not None for cell in members)}
    # A full-width section is a scope header, and a TOTAL column heading
    # cannot act as a total row just because the issuer uses the same word.
    table_width = table["bbox"][2] - table["bbox"][0]
    sections = [cell for cell in native if cell["row"] not in numeric_rows
                and (re.search(r"\bresource\b", cell["text"], re.I) or _CLASSIFIED_ROW.fullmatch(clean(cell["text"])))
                and cell["bbox"][2] - cell["bbox"][0] >= .8 * table_width]
    labels = [cell for cell in native if cell not in sections and cell["row"] in numeric_rows
              and (_CLASSIFIED_ROW.fullmatch(clean(cell["text"])) or _TOTAL.fullmatch(clean(cell["text"])))]
    indexed = {cell["row"] for cell in labels}
    reported_table = CAPTION.match(caption)[1] if caption_entry else None
    context_blocks, notes = _supporting_blocks(caption, table, tables, blocks) if caption_entry else ([], [])
    notes = [(box, text, span) for box, text in notes
             if (span := locally_bound_span(text, reported_table, project, registry))]
    context_blocks = [(box, text, span) for box, text in context_blocks
                      if (span := locally_bound_span(text, reported_table, project, registry))]
    classification_notes = [(box, quote, span) for box, quote, span in [*context_blocks, *notes]
                            if project and _CLASSIFICATION_ASSIGNMENT.search(quote[slice(*span)])]
    caption_categories = {m[0].upper() for m in _CATEGORY.finditer(caption)} if declared_resource else set()
    linked_categories = {m[0].upper() for m in _CATEGORY.finditer(linked_section[1])} if linked_section else set()
    contextual_classification = bool(caption_categories or linked_categories or classification_notes)
    if not indexed and (contextual_classification or sections or cutoff_scenarios):
        first = next((index for index in sorted(numeric_rows) if has_resource_value_row(body[index], [
            cell for cell in native if cell["row"] < index and cell not in sections])), None)
        if first is not None:
            candidate_headers = [cell for cell in native if cell["row"] < first and cell not in sections]
            indexed = {index for index in numeric_rows if index >= first and has_resource_value_row(body[index], candidate_headers)}
    if not indexed:
        return
    first_row = min(indexed)
    headers = [cell for cell in native if cell["row"] < first_row and cell not in sections]
    if not (declared_resource or any(_RESOURCE.search(cell["text"]) for cell in sections)
            or any(_CLASSIFICATION.fullmatch(clean(cell["text"])) for cell in headers)
            and any(_header_unit(_column_parts(cell, headers)[0], "grade", native=True)
                    for cell in native if cell["row"] >= first_row)):
        return
    texts = [caption, *(text[start:end] for _, text, (start, end) in context_blocks)]
    report_pages = _related_report_pages(page, blocks, supporting_pages, registry, project) if project else {}
    external = [(number, box, text, span) for number, related in report_pages.items() for box, text in related
                if number in method_pages and (_DRY_METHOD.search(text) or _WET_METHOD.search(text))
                and (span := locally_bound_span(text, reported_table, project, registry))]
    caption_periods = tuple(caption_estimate_periods(caption)) if declared_resource else ()
    declared_dates = _effective_dates((caption,)) | {value for value, _, _ in caption_periods}
    declared_cutoffs = _cutoff((caption,))
    unique_on_page = bool(reported_table and sum(1 for _, quote in blocks if (match := CAPTION.match(quote))
                          and match[1] == reported_table and not _TABLE_PROSE.match(quote)) == 1)
    table_issues = []
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
    scoped_notes = [text[start:end] for _, text, (start, end) in notes]
    local_bulk = bool(_BULK.search(header_text) or any(_BULK.search(text) or _DRY_METHOD.search(text) for text in scoped_notes))
    local_wet = any(_WET_METHOD.search(text) for text in scoped_notes)
    local_basis = bool(_CHEMICAL.search(header_text) or any(_CHEMICAL.search(text) for text in texts + scoped_notes))
    local_exclusion = any(_EXCLUDED_OXIDE.search(text) for text in [header_text, *texts, *scoped_notes])
    marked_treo = _nearby_marked_treo(page, table, tables, blocks, header_text)
    materials = {}
    if linked_section:
        for index, members in body.items():
            named = [cell for cell in members if clean(cell["text"]).casefold() in _MATERIAL_ROWS
                     and _MATERIAL_COLUMN.fullmatch(_column_parts(cell, headers)[0])]
            if len(named) == 1:
                materials[index] = named[0]
    totals = [cell for cell in labels if cell["row"] not in materials and _TOTAL.fullmatch(clean(cell["text"]))]
    for index in sorted(indexed):
        row_labels = [cell for cell in labels if cell["row"] == index]
        row = {"source_sha256": source["sha256"], "physical_page": page, "project_id": project}
        row_issues = list(table_issues)
        is_total = len(row_labels) == 1 and row_labels[0] in totals
        complete = is_total and len(totals) == 1 or not totals and len(indexed) == 1
        active_section = next((cell for cell in reversed(sections) if cell["row"] < index), None)
        if active_section:
            title = active_section["text"]
            section_ids = {hit["entity_id"] for hit in _matches(title, registry)}
            complete &= bool((re.search(r"\btotal\b", title, re.I) and section_ids == {project}
                              or not labels and len(indexed) == 1 and declared_resource and contextual_classification
                              and section_ids <= {project})
                             and not re.search(r"\b(?:open pit|underground|stockpile|subset)\b", title, re.I))
        # A registry alias can identify a scoped project without proving that the
        # table covers that scope. Its sole Total must be in a named Total section.
        scoped_total = (annotated_scope and complete and is_total and active_section
                        and _RESOURCE.search(active_section["text"]) and _scope_is_named(scope, active_section["text"]))
        local_extent = extent_bound or bool(scoped_total)
        if cutoff_scenarios:
            row_issues.append("RESOURCE_CUTOFF_SCENARIO_NOT_PROJECT_TOTAL")
            row_role = "CUTOFF_SCENARIO"
        elif not complete:
            row_issues.append("RESOURCE_COMPONENT_OR_COMPETING_TOTALS")
            row_issues.append("RESOURCE_COMPETING_TOTALS_UNRESOLVED" if any(cell in totals for cell in row_labels)
                              else "RESOURCE_COMPONENT_EXCLUDED")
            row_role = "COMPETING_TOTAL" if any(cell in totals for cell in row_labels) else "COMPONENT"
        else:
            row_role = "ESTIMATE_TOTAL" if is_total else "SOLE_CLASSIFIED_ESTIMATE"
        first_section_row = active_section["row"] if active_section else -1
        category_cells = ([cell for cell in labels if first_section_row < cell["row"] < index] if is_total else row_labels)
        categories = {match[0].upper() for cell in category_cells for match in _CATEGORY.finditer(cell["text"])}
        section_categories = {m[0].upper() for m in _CATEGORY.finditer(active_section["text"])} if active_section else set()
        note_categories = {m[0].upper() for _, quote, span in classification_notes
                           for m in _CATEGORY.finditer(quote[slice(*span)])}
        contextual_categories = [item for item in (section_categories, caption_categories, linked_categories,
                                                   note_categories) if item]
        if categories and any(categories - declaration for declaration in contextual_categories):
            row_issues.append("RESOURCE_CLASSIFICATION_EVIDENCE_CONFLICT")
            categories = set()
        elif not categories and contextual_categories:
            categories = set.intersection(*contextual_categories)
            if not categories:
                row_issues.append("RESOURCE_CLASSIFICATION_EVIDENCE_CONFLICT")
        category = "_".join(item for item in ("MEASURED", "INDICATED", "INFERRED") if item in categories)
        if not category:
            row_issues.append("RESOURCE_CLASSIFICATION_UNRESOLVED")
        elif is_total:
            category += "_TOTAL"
        cells_for_row = [cell for cell in body[index] if cell not in row_labels]
        all_values = row_quantities(cells_for_row, headers)
        if (linked_section or cutoff_scenarios) and not all_values["contained_treo_kt"]:
            all_values["contained_treo_kt"] = _contained_from_blocks(cells_for_row, headers, blocks, table)
        located = {quantity: all_values[quantity] for quantity in _VARIABLES}
        former_mass = all_values["bulk_ore_mt"] or located["ore_mt"]
        particle, particle_witnesses, particle_issues = _fraction_row(
            row, table, located, all_values, {**supporting_pages, page: blocks}, project, registry, reported_table,
        )
        row_issues.extend(particle_issues)
        cutoffs = dict(declared_cutoffs)
        witnesses = [_cell_anchor("row", row, table, cell) for cell in row_labels]
        if not row_labels and (row_value := located["ore_mt"] or located["grade"]):
            witnesses.append(_cell_anchor("row", row, table, row_value[0][0], locator="NATIVE_CLASSIFIED_VALUE_ROW"))
        witnesses.extend(particle_witnesses)
        if is_total:
            witnesses.extend(_cell_anchor("classification", row, table, cell) for cell in category_cells)
        if caption_entry:
            witnesses.append(_anchors("scope", row, caption, table_index=table["table_index"], bbox=caption_entry[0]))
            if _CATEGORY.search(caption):
                witnesses.append(_anchors("classification", row, caption, table_index=table["table_index"],
                                          row=index, bbox=caption_entry[0], locator="TABLE_CAPTION_CLASSIFICATION"))
            for bbox, quote, (start, end) in classification_notes:
                witnesses.append(_anchors("classification", row, quote, table_index=table["table_index"], row=index,
                                          bbox=bbox, locator="TABLE_NOTE_CLASSIFICATION",
                                          text_span=_quote_span(start, end)))
        if linked_section:
            bbox, title = linked_section
            witnesses.append(_anchors("classification", row, title, table_index=table["table_index"],
                                      row=index, bbox=bbox, locator="NAMED_ESTIMATE_SECTION_HEADING"))
        material_cell = materials.get(index)
        reported_material = None
        if material_cell:
            reported_material = clean(material_cell["text"])
            witnesses.append(_cell_anchor("reported_resource_material", row, table, material_cell))
            witnesses.extend(_cell_anchor("reported_material_column", row, table, piece)
                             for piece in _column_parts(material_cell, headers)[1])
        if active_section:
            witnesses.append(_cell_anchor("resource_section", row, table, active_section,
                                          **({"locator": "NAMED_SCOPE_TOTAL_SECTION"} if scoped_total else {})))
        for box, text, (start, end) in [*context_blocks, *notes]:
            witnesses.append(_anchors("estimate_reference", row, text, table_index=table["table_index"], bbox=box,
                                      locator="SCOPED_ADJACENT_ESTIMATE_NOTE", text_span=_quote_span(start, end)))
        for cell in cells_for_row:
            header, pieces = _column_parts(cell, headers)
            if _CONTAINED_CLAIM.search(header) and not _header_unit(header, "contained_treo_kt") and not any(
                    cell is bound for bound, _, _ in all_values["contained_treo_kt"]):
                row_issues.append("RESOURCE_CONTAINED_UNIT_OR_BASIS_UNRESOLVED")
            if cutoff_cell := cutoff_column_declaration(header, cell["text"]):
                signature, declaration = cutoff_cell
                cutoffs.setdefault(signature, declaration)
                witnesses.append(_cell_anchor("cutoff_value", row, table, cell))
                witnesses.extend({**anchor, "field": "cutoff_header"} for anchor in
                                 column_header_anchors(row, table, pieces, declaration["unit"]))
        supplemental_role = None
        supplemental_basis = False
        if unique_on_page and complete and not row_labels and caption_entry:
            for number, box, quote, (start, end), relation in _layout_note_chain(
                    page, caption_entry, reported_table, project, registry, located, {**supporting_pages, page: blocks}):
                note = quote[start:end]
                if relation == "NAMED_TABLE_NOTE_BRIDGE":
                    witnesses.append(_resource_context_anchor("reported_table_link", row, number, box, quote, relation,
                                                              start=start, end=end))
                    continue
                for signature, declaration in _cutoff((note,)).items():
                    cutoffs.setdefault(signature, declaration)
                    cutoff_start = start + note.index(declaration["text"])
                    witnesses.append(_resource_context_anchor("reported_cutoff", row, number, box, quote, relation,
                                                              start=cutoff_start, end=cutoff_start + len(declaration["text"])))
                if role_match := _POTENTIAL_BYPRODUCT.search(note):
                    supplemental_role = "POTENTIAL_BYPRODUCT_REE"
                    witnesses.append(_resource_context_anchor("reported_product_role", row, number, box, quote, relation,
                                                              start=start + role_match.start(), end=start + role_match.end()))
                if relation == "MATCHED_COMMODITY_ROW_VALUES" and (chemical_match := _CHEMICAL.search(note)):
                    supplemental_basis = True
                    witnesses.append(_resource_context_anchor("reported_chemical_basis", row, number, box, quote, relation,
                                                              start=start + chemical_match.start(), end=start + chemical_match.end()))
        # Keep all target evidence located, and admit cross-page context only
        # after validating table identity, not from the retrieved page alone.
        bound_context = [*marked_treo]
        if unique_on_page and complete:
            bound_context.extend(_table_context_references(page, reported_table, scope, declared_dates, caption,
                                                           blocks, supporting_pages, located, table_label_pages,
                                                           project=project, registry=registry))
        identities, field_evidence, bound_dates, bound_cutoffs, bound_wet, bound_exclusion = _bound_field_witnesses(row, scope, bound_context)
        witnesses.extend(identities)
        for number in sorted({number for number, _, _, relation, _ in bound_context if relation == _MATCHED_PERIOD}):
            witnesses.extend(_resource_context_anchor("estimate_report_scope", row, number, box, quote, _MATCHED_PERIOD)
                             for box, quote in supporting_pages[number]
                             if _scope_is_named(scope, quote) and _RESOURCE.search(quote))
        witnesses.extend(anchor for anchors in field_evidence.values() for anchor in anchors)
        effective_dates = declared_dates | bound_dates
        effective = resolved_estimate_date(effective_dates)
        estimate_period = effective if date_precision(effective) == "MONTH" else None
        date_role = "STATEMENT_EFFECTIVE_DATE" if effective else None
        original_estimate_date = None
        for month, (start, end), role in caption_periods:
            if month == estimate_period:
                if month not in bound_dates:
                    date_role = role
                original_estimate_date = caption[start:end]
                witnesses.append(_resource_context_anchor("reported_estimate_period", row, page, caption_entry[0], caption,
                                                          "TABLE_CAPTION_ESTIMATE_PERIOD", start=start, end=end))
        if not effective:
            row_issues.append("RESOURCE_ESTIMATE_DATE_CONFLICT" if effective_dates else "RESOURCE_ESTIMATE_DATE_UNRESOLVED")
        fraction_defines_treo = any(anchor["field"] == "fraction_grade_basis" and _CHEMICAL.search(
            anchor["quote"][anchor["text_span"]["start"]:anchor["text_span"]["end"]]) for anchor in particle_witnesses)
        basis = ((local_basis or supplemental_basis or fraction_defines_treo or "chemical_basis" in field_evidence)
                 and not (local_exclusion or bound_exclusion))
        if local_exclusion or bound_exclusion:
            row_issues.append("TREO_EXCLUDED_OXIDE_BASIS")
        if not basis:
            row_issues.append("TREO_DEFINITION_UNRESOLVED")
        scope_bound = local_extent or (complete and "scope_coverage" in field_evidence)
        if project and project in (source.get("summary_project_ids") or ()) and not scope_bound:
            row_issues.append("PROJECT_SCOPE_EXTENT_UNRESOLVED")
        prior_cutoffs = set(cutoffs)
        for signature, declaration in bound_cutoffs.items():
            cutoffs.setdefault(signature, declaration)
        cutoff = next(iter(cutoffs.values())) if len(cutoffs) == 1 else None
        composite_grades = [entry for entry in all_values["grade_treosc"] if entry[0]["text"].strip() not in _MISSING]
        composite = composite_grades[0] if len(composite_grades) == 1 else None
        composite_basis = composite_grade_basis(composite[2], cutoff) if composite else None
        if len(composite_grades) > 1:
            row_issues.append("RESOURCE_COLUMN_AMBIGUOUS:grade_treosc")
        if cutoff and cutoff["basis"] != "TREO":
            row_issues.append("RESOURCE_CUTOFF_ANALYTE_NOT_TREO")
        if supplemental_role:
            row_issues.append("RESOURCE_POTENTIAL_BYPRODUCT_REE_NOT_COMPARABLE")
        if cutoff is None:
            row_issues.append("RESOURCE_CUTOFF_UNRESOLVED" if not cutoffs else "RESOURCE_CUTOFF_BASIS_OR_VALUE_CONFLICT")
        section_context = _jorc_section_proofs(page, report_pages, scope, effective, located, cutoff)
        # A footer alone identifies a report, which can contain several
        # estimates. Method text for that report additionally needs the
        # named estimate section and its exact corroborating resource row.
        external_method = external if section_context[0] else ()
        for number, box, text, (start, end) in external_method:
            witnesses.append(_anchors("estimate_reference", {**row, "physical_page": number}, text, bbox=box,
                                      locator="SAME_NAMED_REPORT_AND_MATCHED_ESTIMATE_SECTION",
                                      text_span=_quote_span(start, end)))
        report_bulk = any(_DRY_METHOD.search(text[start:end]) for _, _, text, (start, end) in external_method)
        report_wet = any(_WET_METHOD.search(text[start:end]) for _, _, text, (start, end) in external_method)
        bulk = (not particle and (local_bulk or report_bulk or "material_basis" in field_evidence)
                and not (local_wet or bound_wet or report_wet or _HOLD.search(header_text)))
        if not bulk and not particle:
            row_issues.append("DRY_BULK_ORE_BASIS_UNRESOLVED")
        estimate_key = ["source-estimate-v1", source["sha256"], page, table["table_index"], project, scope, effective]
        if cutoff_scenarios:
            estimate_key.append(cutoff or {"unresolved_cutoff_row": index})
        estimate = digest(estimate_key)
        statement = digest(["source-statement-v1", estimate, index])
        subject = {"project_id": project, "scope_id": scope, "estimate_id": estimate, "statement_id": statement,
                   "effective_date": effective, "physical_page": page, "table": table["table_index"], "row": index,
                   "reported_table_label": reported_table, "reported_table_unique_on_page": unique_on_page}
        jorc, jorc_anchors = _jorc_evidence(source, registry, page, table, tables, row, subject, caption_entry, active_section, blocks,
                                           report_pages, section_context, bound_context)
        if jorc["reason"]:
            row_issues.append(jorc["reason"])
        witnesses.extend(jorc_anchors)
        scope_coverage = "PROJECT_TOTAL" if complete and scope_bound else "RESOURCE_COMPONENT" if not complete else None
        if (complete and (supplemental_role or linked_section and not scope_bound)) or cutoff_scenarios:
            scope_coverage = "REPORTED_ESTIMATE_SCOPE"
        if particle:
            scope_coverage = "PARTICLE_SIZE_FRACTION"
        context = {"scope": scope, "statement_id": statement, "estimate_id": estimate, "effective_date": effective,
                   "category": category or None, "resource_type": "MINERAL_RESOURCE" if declared_resource and not incompatible else None,
                   "reporting_standard": "JORC" if jorc["status"] == "AFFIRMED" else None,
                   "jorc_status": jorc["status"], "jorc_rule_version": JORC_VERSION,
                   "scope_coverage": scope_coverage,
                   "cutoff_grade": cutoff,
                   # The neighboring headings distinguish the reported chemical
                   # species even when a formal bulk TREO definition is absent.
                   "basis": "TREO" if basis or len(located["grade"]) == 1 and (
                       composite_basis or linked_section or cutoff_scenarios) else None,
                   "material_basis": (FRACTION_MATERIAL if particle else reported_material
                                      or ("RESOURCE_BULK_ORE" if bulk else None)),
                   "denominator_basis": FRACTION_DENOMINATOR if particle else "RESOURCE_BULK_ORE_MASS" if bulk else None,
                   "particle_size_um": particle["value"] if particle else None, "particle_size": particle,
                   "estimate_period": estimate_period, "product_role": supplemental_role,
                   "effective_date_role": date_role,
                   "effective_date_precision": date_precision(effective),
                   "original_estimate_date": original_estimate_date,
                   "available_date": source.get("available_date"), "definition_witness": VERSION,
                   "reported_table_label": reported_table,
                   "reported_table_unique_on_page": str(unique_on_page).lower()}
        new_fields = {field: value for field, value, prior in (
            ("effective_date", effective, effective in declared_dates), ("cutoff_grade", cutoff, prior_cutoffs),
            ("material_basis", context["material_basis"] if not particle else None, local_bulk),
            ("denominator_basis", context["denominator_basis"] if not particle else None, local_bulk),
            ("chemical_basis", context["basis"], local_basis),
            ("scope_coverage", context["scope_coverage"] if scope_coverage == "PROJECT_TOTAL" else None, local_extent),
        ) if value and not prior and field in field_evidence and complete}
        gains = {field: {"value": value, "decision": "BOUND_SAME_ESTIMATE", "evidence": field_evidence[field]}
                 for field, value in new_fields.items()}
        unbound_grade = "RESOURCE_PARTICLE_SIZE_FRACTION_GRADE_UNBOUND" in particle_issues
        observation_context = ({**context, "particle_size_um": None, "particle_size": None,
                                "material_basis": None, "denominator_basis": None, "scope_coverage": None}
                               if unbound_grade else context)
        observations = []
        for quantity in _VARIABLES:
            matches = [entry for entry in located[quantity] if entry[0]["text"].strip() not in _MISSING]
            if len(matches) != 1:
                if matches or quantity != "contained_treo_kt":
                    row_issues.append(f"RESOURCE_COLUMN_{'AMBIGUOUS' if matches else 'UNBOUND'}:{quantity}")
                continue
            cell, unit, pieces = matches[0]
            observation, issue = _typed(source, row, table, cell, quantity, unit, pieces, observation_context,
                                        witnesses, row_cells=cells_for_row)
            if issue:
                row_issues.append(f"{issue}:{quantity}")
            if observation is not None:
                observations.append(observation)
        material_observations = []
        material_columns = []
        if particle and len(former_mass) == 1:
            bulk_context = {**context, "particle_size_um": None, "particle_size": None, "basis": None,
                            "scope_coverage": "REPORTED_ESTIMATE_SCOPE",
                            "material_basis": "RESOURCE_BULK_ORE", "denominator_basis": "RESOURCE_BULK_ORE_MASS"}
            material_columns.append(("bulk_ore_mt", former_mass[0], bulk_context,
                                     [witness for witness in witnesses if witness not in particle_witnesses]))
        if unbound_grade:
            material_columns.append(("fraction_ore_mt", all_values["fraction_mass"][0], {**context, "basis": None}, witnesses))
        if composite:
            composite_context = {**observation_context, "basis": composite_basis,
                                 "observation_use": "AUXILIARY_COMPOSITION_GRADE"}
            material_columns.append(("grade_treosc", composite, composite_context, witnesses))
            if not composite_basis:
                row_issues.append("RESOURCE_COMPOSITE_GRADE_BASIS_UNRESOLVED")
        for quantity, (cell, unit, pieces), material_context, material_witnesses in material_columns:
            observation, issue = _typed(source, row, table, cell, quantity, unit, pieces, material_context,
                                        material_witnesses, row_cells=cells_for_row)
            if issue:
                row_issues.append(f"{issue}:{quantity}")
            if observation is not None:
                material_observations.append(observation)
        yield {"candidate_id": statement, "physical_page": page, "table": table["table_index"], "row": index,
               "project_id": project, "observations": tuple(observations), "issues": tuple(sorted(set(row_issues))),
               "material_observations": tuple(material_observations),
               "jorc_assessment": jorc, "row_role": row_role, "context_field_gains": gains}


def candidates_on_page(source, registry, physical_page, blocks, tables, *, supporting_pages=None, method_pages=None,
                       table_label_pages=None, words=()):
    """Visit native rows and keep every disposition, including unusable components."""
    registry = _registered_scope_aliases(registry)
    supporting_pages = supporting_pages or {}
    table_label_pages = table_label_pages or {}
    if method_pages is None:
        method_pages = supporting_pages.keys()
    caption_lines = tuple(_caption_lines(words))
    return tuple(candidate for table in tables
                 for candidate in _table_rows(source, registry, physical_page, table, tables, blocks, supporting_pages, method_pages,
                                              table_label_pages, caption_lines))


def _positioned_value_issues(candidate, words):
    """Compare independent positioned words inside the same native value rectangle."""
    for observation in (*candidate["observations"], *candidate.get("material_observations", ())):
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
                merged_caption = not error and any(CAPTION.match(quote) and any(
                    bounds[1] < table["bbox"][1] < bounds[3] for table in tables) for bounds, quote in blocks)
                words = document.words(page) if merged_caption else ()
                discovered = candidates_on_page(source, registry, page, blocks, tables, supporting_pages=supporting,
                                                method_pages=context_pages, table_label_pages=known_labels,
                                                words=words) if not error else ()
                if discovered:
                    words = words or document.words(page)
                    discovered = tuple({**candidate, "issues": tuple(sorted(set(candidate["issues"]) |
                                              set(_positioned_value_issues(candidate, words))))} for candidate in discovered)
            except (OSError, RuntimeError, ValueError) as exc:
                error, discovered = type(exc).__name__, ()
            status = "PARSE_FAILED" if error else "DISCOVERED" if discovered else "NO_CANDIDATES"
            decisions.append({"physical_page": page, "status": status, "reason": error})
            candidates.extend(discovered)
    return {"pages": decisions, "context_page_dispositions": context_decisions, "candidates": tuple(candidates)}
