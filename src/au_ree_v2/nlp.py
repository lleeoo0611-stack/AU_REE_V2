"""Rule-based source-bound extraction and BM25 evidence-page retrieval."""
import json
import math
import re
import unicodedata
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Protocol

from .derived_cache import code_fingerprint
from .document_processing import (
    DocumentUnavailable, PdfDocumentCache, SHA256, _file_sha, ocr_model_sha, pdf_view_spec,
)
from .numeric_evidence import numeric_token_spans
from .pdf_extract import DOCUMENT_VERSION, NUMBER, extraction_dependencies, readable, recognize_document
from .store import digest
from .semantic_resource import extract_resource_observations
from .semantic_technical import reextract_technical


# Field vocabulary is fixed for the experiment. No document, project, expected page,
# mineral deposit label, or text from an adjudication is part of this vocabulary.
FIELD_TERMS = {
    "coordinate": "latitude longitude coordinate coordinates datum projection grid easting northing "
                  "location map tenement tenements licence licences license licenses granted relinquished "
                  "boundary boundaries locality gda94 gda2020 mga94 mga2020 wgs84",
    "deposit": "deposit deposits geology geological mineralisation mineralization host hosted lithology "
               "regolith saprolite laterite clay ionic adsorption hardrock carbonatite pegmatite "
               "alkaline alluvial placer heavy mineral sands",
    "resource": "mineral resource estimate JORC measured indicated inferred tonnes tonnage grade "
                "cutoff reserve exploration target TREO ppm contained",
    "resource_context": "estimate estimation effective dated reporting standard JORC classification scope "
                        "dry wet moisture basis density denominator definition defined comprises "
                        "calculated oxide oxides TREO cutoff cut-off threshold table footnote tonnage",
    "strategic_composition": "REE REO TREO assemblage composition neodymium praseodymium dysprosium terbium "
                             "Nd Nd2O3 Pr Pr6O11 Dy Dy2O3 Tb Tb4O7 feed concentrate product",
    "technical": "mineralogy feed composite sample beneficiation flotation leach separation extraction "
                 "recovery laboratory pilot demonstration commercial design metallurgical",
    "stage": "exploration drilling completed commenced resource estimate scoping pre-feasibility "
             "prefeasibility feasibility definitive study trial pilot permitting construction "
             "commissioning production operating operations suspended relinquishment surrendered",
}
FAMILIES = {
    "緯度": "coordinate", "經度": "coordinate",
    "礦床型態": "deposit", "礦床型態代碼": "deposit",
    "開發階段": "stage", "開發階段代碼": "stage", "開發階段類別": "stage",
}
# Focus the project-name terms on their distinguishing part. Domain vocabulary
# still contributes via FIELD_TERMS when no project name occurs on a relevant page.
GENERIC_NAMES = set("project projects the and for of at in by on within australia australian company "
                    "minerals mineral exploration limited ltd plc pty rare earth earths elements ree "
                    "deposit prospect resource resources scope historical areas holdings".split())
WORDS = re.compile(r"[^\W_]+", re.UNICODE)


def _tokens(text):
    text = unicodedata.normalize("NFKC", text).casefold()
    text = re.sub(r"(?<=\w)[-‐‑]\s*\n\s*(?=\w)", "", text)
    return WORDS.findall(text)


class PageRetriever(Protocol):
    """Alternate rankers retain the same identified-page contract."""

    def rank_pair(self, aliases, field, baseline_pages=(), *, k=5): ...


def _page_key(sha, number):
    if not isinstance(sha, str) or not SHA256.fullmatch(sha) or type(number) is not int or number < 1:
        raise ValueError("A page needs a SHA-256 and a positive physical page")
    return sha, number


def _term_counts(text):
    if not isinstance(text, str):
        raise ValueError("A page needs text")
    return dict(Counter(_tokens(text)))


def _term_rows(value):
    if not isinstance(value, list):
        raise ValueError("Invalid indexed term rows")
    for row in value:
        if (not isinstance(row, (list, tuple)) or len(row) != 3
                or not isinstance(row[2], dict)
                or any(not isinstance(term, str) or type(frequency) is not int or frequency < 1
                       for term, frequency in row[2].items())):
            raise ValueError("Invalid indexed term frequencies")
        _page_key(*row[:2])


@lru_cache
def _tokenizer_signature():
    return code_fingerprint(_tokens, _term_counts), WORDS.pattern, WORDS.flags, unicodedata.unidata_version


class PageIndex:
    """One verified SHA/page-addressed corpus, shared by both arms of a query."""

    def __init__(self, pages):
        self._load_terms((sha, number, _term_counts(text)) for sha, number, text in pages)

    def _load_terms(self, pages):
        self._cache = None
        self._index_sha = None
        self.page_keys = set()
        self.documents = {}
        self.lengths = {}
        self.df = Counter()
        for sha, number, terms in pages:
            key = _page_key(sha, number)
            if key in self.page_keys:
                raise ValueError("Duplicate PDF edition and physical page")
            self.page_keys.add(key)
            if terms:
                self.documents[key] = terms
                self.lengths[key] = sum(terms.values())
                self.df.update(terms.keys())
        count = len(self.documents)
        self.average_length = sum(self.lengths.values()) / count if count else 0

    @classmethod
    def from_documents(cls, documents: PdfDocumentCache, source_hashes, *,
                       expected_pages=None, missing=None, page_diagnostics=None):
        """Validate original editions and use the positioned text view for BM25."""
        cache = documents.cache
        if cache is None and expected_pages is None and missing is None and page_diagnostics is None:
            return cls((sha, page, document.text(page, positioned=True))
                       for sha in dict.fromkeys(source_hashes)
                       for document in (documents.open(sha),)
                       for page in range(1, len(document) + 1))
        corpus = []
        for sha in sorted(set(source_hashes)):
            try:
                documents.verify(sha)
            except DocumentUnavailable as exc:
                if missing is None:
                    raise
                missing[sha] = str(exc)
                continue
            corpus.append(sha)
        settings = {"format": "bm25-term-counts-v2", "tokenizer": _tokenizer_signature(),
                    "text_parser": pdf_view_spec("positioned_text"), "page_count": pdf_view_spec("page_count"),
                    "code": _index_signature()}
        if page_diagnostics is not None:
            settings["page_diagnostics"] = "positioned-readability-v1"

        def terms(sha):
            document = documents.open(sha)
            rows, issues = [], []
            for page in range(1, len(document) + 1):
                try:
                    text = document.text(page, positioned=True)
                except (OSError, RuntimeError, ValueError) as exc:
                    if page_diagnostics is None:
                        raise
                    text = ""
                    issues.append([page, "INDEX_PARSE_FAILED", type(exc).__name__])
                else:
                    if page_diagnostics is not None and not readable(text):
                        text = ""
                        issues.append([page, "PAGE_TEXT_UNREADABLE", "NO_READABLE_POSITIONED_TEXT"])
                rows.append([sha, page, _term_counts(text)])
            return {"terms": rows, "page_issues": issues}

        def validate_document(product, sha):
            rows = product["terms"]
            _term_rows(rows)
            if [tuple(row[:2]) for row in rows] != [(sha, n) for n in range(1, len(rows) + 1)]:
                raise ValueError("BM25 document term counts disagree with their source edition")
            issues = product["page_issues"]
            if (not isinstance(issues, list) or any(not isinstance(row, list) or len(row) != 3
                    or type(row[0]) is not int or not 1 <= row[0] <= len(rows) or rows[row[0] - 1][2]
                    or row[1] not in {"INDEX_PARSE_FAILED", "PAGE_TEXT_UNREADABLE"} or not isinstance(row[2], str)
                    for row in issues) or len({row[0] for row in issues}) != len(issues)):
                raise ValueError("Invalid BM25 page diagnostics")

        def build_index():
            rows, errors, issues = [], {}, {}
            for sha in corpus:
                try:
                    if cache is None:
                        document_terms = terms(sha)
                        validate_document(document_terms, sha)
                    else:
                        document_terms = cache.compute(
                            "bm25-index", f"document:{sha}", settings,
                            lambda: terms(sha), upstream={"source_snapshot": sha},
                            validate=lambda rows: validate_document(rows, sha),
                        )
                    rows.extend(document_terms["terms"])
                    if document_terms["page_issues"]:
                        issues[sha] = document_terms["page_issues"]
                except DocumentUnavailable as exc:
                    if missing is None:
                        raise
                    errors[sha] = str(exc)
            return {"terms": rows, "errors": errors, "page_issues": issues}

        def validate_index(value):
            if (not isinstance(value, dict) or not isinstance(value.get("errors"), dict)
                    or not isinstance(value.get("page_issues"), dict)
                    or any(sha not in corpus or not isinstance(reason, str)
                           for sha, reason in value["errors"].items())):
                raise ValueError("Invalid BM25 corpus artifact")
            _term_rows(value.get("terms"))
            documents_by_sha = defaultdict(list)
            for row in value["terms"]:
                documents_by_sha[row[0]].append(row)
            if not (documents_by_sha.keys() | value["page_issues"].keys()) <= set(corpus) - value["errors"].keys():
                raise ValueError("BM25 index differs from its verified corpus manifest")
            for sha in corpus:
                if sha not in value["errors"]:
                    validate_document({"terms": documents_by_sha[sha],
                                       "page_issues": value["page_issues"].get(sha, [])}, sha)

        value = build_index() if cache is None else cache.compute(
            "bm25-index", "verified-corpus", {**settings, "corpus": corpus}, build_index,
            upstream={sha: sha for sha in corpus}, validate=validate_index,
        )
        if value["errors"]:
            if missing is None:
                raise DocumentUnavailable(next(iter(value["errors"].values())))
            missing.update(value["errors"])
        if page_diagnostics is not None:
            page_diagnostics.update(value["page_issues"])
        if expected_pages is not None:
            actual_pages = Counter(row[0] for row in value["terms"])
            for sha in corpus:
                if sha not in value["errors"] and actual_pages[sha] != expected_pages[sha]:
                    raise ValueError(f"Physical page count differs from the frozen edition: {sha}")
        index = cls.__new__(cls)
        index._load_terms(value["terms"])
        index._cache = cache
        if cache is not None:
            index._index_sha = digest(value)
        return index

    def rank_pair(self, aliases, field, baseline_pages=(), *, k=5):
        """Rules keep their original pages; add BM25 pages only to unused slots.

        Page-index order and alias order have no effect. Without a searchable text
        layer, a page can still be returned by a prior explicit rule reference.
        Each result is an ordered list of (SHA-256, physical page) tuples.
        """
        family = FAMILIES.get(field, field)
        if family not in FIELD_TERMS:
            raise ValueError(f"Unsupported evidence field {field!r}")
        if type(k) is not int or k < 1:
            raise ValueError("k must be a positive integer")
        supplied_baseline = list(dict.fromkeys(tuple(pair) for pair in baseline_pages))
        baseline = [pair for pair in supplied_baseline if pair in self.page_keys][:k]
        if isinstance(aliases, str):
            aliases = [aliases]
        names = {word for alias in aliases for word in _tokens(alias)
                 if len(word) > 1 and word not in GENERIC_NAMES}
        terms = set(_tokens(FIELD_TERMS[family]))
        if self._cache is None:
            return self._rank(baseline, names, terms, k)
        inputs = {"baseline": baseline, "names": sorted(names), "terms": sorted(terms), "k": k,
                  "family": family, "code": _query_signature()}
        value = self._cache.compute(
            "bm25-query", f"{family}:{digest([sorted(names), supplied_baseline])}", inputs,
            lambda: self._rank(baseline, names, terms, k),
            upstream={"corpus_index": self._index_sha}, validate=self._validate_queue,
        )
        return {key: [tuple(pair) for pair in queue] for key, queue in value.items()}

    def _validate_queue(self, value):
        if not isinstance(value, dict) or set(value) != {"rules", "rules_nlp"}:
            raise ValueError("Invalid BM25 ranking queues")
        for queue in value.values():
            if not isinstance(queue, list) or any(not isinstance(pair, (list, tuple)) or len(pair) != 2
                                                  or _page_key(*pair) not in self.page_keys for pair in queue):
                raise ValueError("BM25 queue refers to an unknown indexed page")

    def _rank(self, baseline, names, terms, k):
        augmented = list(baseline)
        if len(augmented) < k and self.documents:
            weights = {term: 1 + int(term in names) for term in sorted(names | terms)}
            count = len(self.documents)
            idf = {term: math.log1p((count - self.df[term] + 0.5) / (self.df[term] + 0.5))
                   for term in weights}
            ranked = []
            for key, frequencies in self.documents.items():
                if key in baseline or terms.isdisjoint(frequencies):
                    continue
                # Robertson BM25, k1=1.2, b=0.75. The aliases receive weight 2.
                length_penalty = 1.2 * (0.25 + 0.75 * self.lengths[key] / self.average_length)
                score = sum(weights[t] * idf[t] * frequencies[t] * 2.2 / (frequencies[t] + length_penalty)
                            for t in weights if t in frequencies)
                ranked.append((-score, key))
            augmented.extend(key for _, key in sorted(ranked)[:k - len(baseline)])
        return {"rules": baseline, "rules_nlp": augmented}


@lru_cache
def _index_signature():
    return code_fingerprint(PageIndex.from_documents, _page_key, PageIndex._load_terms, readable)


@lru_cache
def _query_signature():
    return code_fingerprint(PageIndex.rank_pair, PageIndex._rank, _tokens)



class BoundObservationExtractor(Protocol):
    """Contract for candidate extraction from the fixed source and page frame."""

    def __call__(self, resource_candidates, technical_captures, documents: PdfDocumentCache): ...


@lru_cache
def _extraction_spec(domain):
    package = Path(__file__).parent
    module = "semantic_resource.py" if domain == "resource" else "semantic_technical.py"
    readers = ("content_order_text", "text_blocks", "native_tables") if domain == "resource" else (
        "content_order_text", "positioned_text", "page_bounds", "native_tables",
    )
    return {
        "format": "source-bound-captures-v1",
        "domain": domain,
        "code": code_fingerprint(_source_captures, files=(
            package / module, package / "technical_tables.py", package / "numeric_evidence.py",
        )),
        "unicode": unicodedata.unidata_version if domain == "resource" else None,
        "numeric_pattern": NUMBER if domain == "resource" else None,
        "parser": {kind: pdf_view_spec(kind) for kind in readers},
    }


def _source_captures(domain, sha, rows, documents):
    if not rows:
        return []
    extractor = extract_resource_observations if domain == "resource" else reextract_technical
    rows = sorted(rows, key=lambda row: row["candidate_id"])

    def build():
        documents.counts[f"{domain}_extractions"] += 1
        return extractor(rows, documents.assets, documents=documents)

    if documents.cache is None:
        return build()
    requires_original = (any(type(row["physical_page"]) is int and row["physical_page"] > 0
                             and not row.get("source_gates") for row in rows) if domain == "resource"
                         else any(row["native"]["quantity"] == "extraction_pct" for row in rows))
    upstream = {}
    if requires_original:
        # Pinned bytes are always reverified before a previously extracted
        # candidate can be reused. Missing originals keep the extractor's
        # existing blocked dispositions and never populate this cached key.
        try:
            length = len(documents.open(sha))
        except DocumentUnavailable as exc:
            documents.cache.record("extraction", f"{domain}:{sha}", "SOURCE_BLOCKED", reason=str(exc),
                                   affected_candidates=len(rows))
            return build()
        upstream = {"source_snapshot": sha, "pdf_page_count": digest(length)}

    def validate(captures):
        if (not isinstance(captures, list) or sorted(row["candidate_id"] for row in rows)
                != [capture.get("candidate_id") for capture in captures]
                or any(capture.get("source_sha256") != sha for capture in captures)):
            raise ValueError("Cached captures differ from their frozen source frame")

    return documents.cache.compute(
        "extraction", f"{domain}:{sha}", {**_extraction_spec(domain), "candidates": digest(rows)},
        build, upstream=upstream, validate=validate,
    )


def extract_bound_observations(resource_candidates, technical_captures, documents: PdfDocumentCache):
    """Apply the existing quantity and context rules with both domains sharing each PDF."""
    resource_sources = defaultdict(list)
    technical_sources = defaultdict(list)
    for row in resource_candidates:
        resource_sources[row["source_sha256"]].append(row)
    for row in technical_captures:
        technical_sources[row["source_sha256"]].append(row)
    resource, technical = [], []
    for sha in sorted(resource_sources.keys() | technical_sources.keys(), key=str):
        resource.extend(_source_captures("resource", sha, resource_sources[sha], documents))
        technical.extend(_source_captures("technical", sha, technical_sources[sha], documents))
    return (sorted(resource, key=lambda row: row["candidate_id"]),
            sorted(technical, key=lambda row: row["candidate_id"]))


def recognize_source(root, source, registry, *, cache=None, tessdata=None, page_numbers=None):
    """Reuse the existing document recognizer's report without registering a source artifact."""
    root = Path(root)
    pages = sorted(set(page_numbers)) if page_numbers is not None else None
    if source["kind"] != "pdf":
        tessdata = None
    if cache is None:
        return recognize_document(root, source, registry, tessdata, page_numbers=pages)
    sha = source["sha256"]
    try:
        original_sha = _file_sha(root / source["path"])
    except OSError as exc:
        cache.record("recognition", source["key"], "SOURCE_BLOCKED", reason="PDF_BYTES_UNAVAILABLE")
        raise DocumentUnavailable("PDF_BYTES_UNAVAILABLE") from exc
    if original_sha != sha:
        cache.record("recognition", source["key"], "SOURCE_BLOCKED", reason="SOURCE_HASH_MISMATCH")
        raise DocumentUnavailable("SOURCE_HASH_MISMATCH")
    # Entity identity can change while the report's bytes stay the same. Only
    # claims that bind this source enter the report dependency fingerprint.
    claims = json.loads((root / "data/claims.json").read_bytes())["projects"]
    linked = sorted((p.get("entity_namespace", "project_registry_v1"), str(p["id"]),
                     p.get("entity_kind", "PROJECT")) for p in claims if
                    any(o.get("source_sha256") == sha for o in p.get("observations", [])))
    inputs = {
        "format": DOCUMENT_VERSION, "recognizer": extraction_dependencies(), "registry": digest(registry),
        "code": code_fingerprint(recognize_source),
        "source_bindings": digest(linked),
        "publication_metadata": {key: source.get(key) for key in
                                 ("kind", "key", "url", "publication_date", "recognition_project_native_id",
                                  "project_binding_status")},
        "pages": pages, "ocr_model_sha256": ocr_model_sha(tessdata),
        "native_parser": pdf_view_spec("pypdf_text") if tessdata is not None else None,
    }

    def validate(report):
        if (not isinstance(report, dict) or report.get("source_sha256") != sha
                or report.get("source_key") != source["key"] or report.get("version") != DOCUMENT_VERSION
                or report.get("requested_physical_pages") != pages or not isinstance(report.get("candidates"), list)):
            raise ValueError("Cached recognition differs from its source and parser contract")

    return cache.compute(
        "recognition", source["key"], inputs,
        lambda: recognize_document(root, source, registry, tessdata, page_numbers=pages),
        upstream={"source_snapshot": sha}, validate=validate,
    )


RECOGNITION_PROJECTION_VERSION = "document-recognition-observations-v1"
LOCATED_RECOGNITION_VERSION = "document-recognition-observations-v2-typed-span"
STRATEGIC_ANALYTES = frozenset({"Nd2O3", "Pr6O11", "Dy2O3", "Tb4O7"})


def _reported_quantities(candidate):
    """Yield the native tokens already bound by the document recognizer."""
    kind = candidate["kind"]
    if kind == "RESOURCE_TABLE_TOTAL":
        tokens = candidate["original_tokens"]
        for default_index, variable in enumerate(("ore_mt", "grade")):
            index = (candidate.get("row_token_indices") or {}).get(variable, default_index)
            if index < len(tokens):
                yield "RESOURCE", variable, tokens[index], candidate["units"].get(variable), {"row_token_index": index}
        position = candidate.get("positioned_column_evidence") or {}
        if position.get("method") == "positioned-resource-columns-v4":
            for value in candidate.get("extra_values", []):
                if value["label"] in STRATEGIC_ANALYTES and value.get("unit"):
                    yield ("STRATEGIC_COMPOSITION", "reported_oxide_concentration", value["original_token"],
                           value["unit"], {"chemical_basis": value["label"]})
    elif kind == "TECHNICAL_TABLE_CELL":
        yield ("TECHNICAL", "reported_technical_" + candidate["quantity"], candidate.get("original_token"),
               candidate.get("unit"), {"token_state": candidate.get("token_state"), "bounds": candidate.get("bounds")})
    elif kind == "SCOPED_TEXT_DISCLOSURE":
        if candidate.get("domain") == "Technical":
            for number in candidate.get("numbers", ()):
                if number.get("quantity_role"):
                    yield ("TECHNICAL", number["quantity_role"].lower(), number["token"], number["unit"],
                           {"offset": number["start"], "chemical_basis": number.get("basis"),
                            "claim_nature": number.get("evidence_nature"), "token_state": number.get("token_state"),
                            "bounds": number.get("bounds")})
        elif candidate.get("domain") in {"Development", "Commercial"}:
            yield "EVENT", candidate["domain"].lower() + "_event_mention", None, None, {}


def _recognition_span(candidate, token, unit, qualifiers):
    """Locate the printed token only when its recognition convention is known."""
    if not token:
        return None
    quote = candidate["raw_text"]
    allowed = numeric_token_spans(quote, token, unit)
    kind = candidate["kind"]
    if kind == "SCOPED_TEXT_DISCLOSURE" and "offset" in qualifiers:
        start = qualifiers["offset"]
        span = (start, start + len(token))
        view = "RECOGNITION_SENTENCE"
        if span not in allowed:
            return None
    elif kind == "RESOURCE_TABLE_TOTAL" and "row_token_index" in qualifiers:
        tokens = candidate["original_tokens"]
        aligned = sorted({match for literal in set(tokens)
                          for match in numeric_token_spans(quote, literal)})
        if len(aligned) != len(tokens):
            return None
        span = aligned[qualifiers["row_token_index"]]
        if span not in allowed:
            return None
        view = "RECOGNITION_TABLE_ROW"
    elif len(allowed) == 1 and kind in {"RESOURCE_TABLE_TOTAL", "TECHNICAL_TABLE_CELL"}:
        span = allowed[0]
        view = "RECOGNITION_TABLE_ROW" if kind == "RESOURCE_TABLE_TOTAL" else "MUPDF_TABLE_CELL"
    else:
        return None
    return {"scope": "QUOTE", "view": view, "start": span[0], "end": span[1], "quote_start": 0}


def automatic_observations(report):
    """Project a cached automatic recognition report into raw review candidates."""
    from .observation_pipeline import raw_from_candidate

    source_sha256 = report["source_sha256"]
    source_key = report["source_key"]
    previous_version = RECOGNITION_PROJECTION_VERSION + "/" + report["version"]
    fingerprint = digest([report.get(key) for key in ("backend_version", "registry_identity_sha256",
                                                      "source_binding_sha256", "extraction_dependency_sha256")])
    for candidate in report["candidates"]:
        if candidate["source_sha256"] != source_sha256 or candidate["source_key"] != source_key:
            raise ValueError("Recognition candidate belongs to a different source edition")
        quantities = list(_reported_quantities(candidate))
        identifiers = [digest([candidate["candidate_id"], ordinal, quantity[1]])
                       for ordinal, quantity in enumerate(quantities)]
        for ordinal, (kind, variable, token, unit, qualifiers) in enumerate(quantities):
            context = {key: candidate[key] for key in (
                "scope", "category", "resource_type", "cutoff", "basis_definition", "header", "header_path",
                "sample_id", "test_id", "feed", "endpoint", "scale", "stage", "reagent", "grain_mm",
                "acid_concentration", "acid_unit", "evidence_mode", "statistic", "limitations",
                "material_basis", "denominator_basis", "table_scope_id", "case_id", "date_role",
                "project_binding", "publication_date",
            ) if key in candidate}
            context.update({"recognition_candidate_id": candidate["candidate_id"],
                            "recognition_issues": candidate.get("issues", []),
                            "chemical_basis": qualifiers.get("chemical_basis") or candidate.get("basis"),
                            "claim_nature": qualifiers.get("claim_nature")})
            anchor = {key: candidate[key] for key in ("physical_page", "table_index", "row_index",
                                                       "column_index", "bbox") if key in candidate}
            anchor.update(source_sha256=source_sha256, role="token", quote=candidate["raw_text"],
                          offset=qualifiers.get("offset"))
            span = _recognition_span(candidate, token, unit, qualifiers)
            extraction_version = previous_version
            if span is not None:
                anchor["text_span"] = span
                extraction_version = LOCATED_RECOGNITION_VERSION + "/" + report["version"]
                context["prior_extractor_version"] = previous_version
                context["extraction_change_reason"] = "EXPLICIT_PRINTED_TOKEN_SPAN"
            yield raw_from_candidate({
                "observation_id": identifiers[ordinal], "project_id": candidate.get("project_id"),
                "source_sha256": source_sha256, "physical_page": candidate["physical_page"],
                "quantity_kind": kind, "context": context, "anchors": [anchor],
                "related_observation_ids": tuple(identifier for identifier in identifiers
                                                 if identifier != identifiers[ordinal]),
                "native": {"quantity": variable, "token": token, "unit": unit,
                           "token_state": qualifiers.get("token_state"), "bounds": qualifiers.get("bounds")},
                "extraction_fingerprint": fingerprint,
            }, source_id=source_key, extractor_version=extraction_version)


SOURCE_DISCOVERY_VERSION = "source-page-discovery-v1"


def _page_captures(sha, page, text_value, text_view, blocks, tables):
    """Discover independent table cells and scoped clauses on the requested page."""
    from .semantic_resource import discover_resource_page
    from .semantic_technical import narrative_mentions

    for record in discover_resource_page(sha, page, blocks, tables):
        yield {"quantity_kind": "RESOURCE", **record}
    for mention in narrative_mentions(text_value, sha, page, text_view=text_view):
        number = mention["native"]
        anchor = mention["anchor"]
        yield {"quantity_kind": "TECHNICAL",
               "native": {"quantity": mention["quantity_role"].lower(), "token": number["token"],
                          "unit": number["unit"], "token_state": number["token_state"], "bounds": number["bounds"]},
               "anchors": [{**anchor, "role": "token", "offset": anchor["text_span"]["start"]}],
               "context": {"chemical_basis": mention["basis"], "claim_nature": mention["claim_nature"]}}


def _project_page_captures(source, page, project_id, captures):
    from .observation_pipeline import raw_from_candidate

    sha = source["sha256"]
    for capture in captures:
        witness = capture["anchors"][0]
        span = witness["text_span"]
        identity = digest([SOURCE_DISCOVERY_VERSION, sha, page, capture["native"]["quantity"],
                           witness.get("table_index"), witness.get("row"), witness.get("column"),
                           witness.get("bbox"), span])
        yield raw_from_candidate({
            **capture, "observation_id": identity, "source_sha256": sha, "physical_page": page,
            "project_id": project_id,
        }, source_id=source["key"], extractor_version=SOURCE_DISCOVERY_VERSION, metadata=source)


def _observation_discovery_key(observation):
    anchor = observation.evidence
    return (observation.variable, observation.original_value, observation.original_unit, anchor.page,
            anchor.table, anchor.row, anchor.column, anchor.bbox, anchor.quote, anchor.offset)


def discover_source_observations(root, source, registry, *, page_numbers, cache=None, tessdata=None,
                                 ocr_comparison_pages=()):
    """Make a page-complete discovery record without changing or selecting formal observations."""
    from .pdf_extract import _matches, readable
    from .semantic_resource import clean

    pages = sorted(set(page_numbers))
    if not pages or any(type(page) is not int or page < 1 for page in pages):
        raise ValueError("Discovery requires positive physical page numbers")
    if source["kind"] != "pdf":
        raise ValueError("Source-page discovery requires a PDF")
    ocr_comparison = set(ocr_comparison_pages)
    if not ocr_comparison <= set(pages):
        raise ValueError("OCR comparison pages must belong to the discovery frame")
    sha, source_key = source["sha256"], source["key"]
    original = Path(root) / source["path"]
    with PdfDocumentCache(original.parent, source_paths={sha: original}, cache=cache) as documents:
        document = documents.open(sha)
        pinned = [page for page in pages if page <= len(document)]
        recognition_error = None
        try:
            report = recognize_source(root, source, registry, cache=cache,
                                      tessdata=tessdata, page_numbers=pinned) if pinned else None
        except DocumentUnavailable:
            raise
        except (RuntimeError, ValueError, OSError) as exc:
            if str(exc) == "SOURCE_HASH_MISMATCH":
                raise DocumentUnavailable(str(exc)) from exc
            recognition_error = "RECOGNITION_" + type(exc).__name__
            report = None
        raw_candidates = defaultdict(list)
        projected = defaultdict(list)
        continued = {}
        if report is not None:
            continued = {(table["physical_page"], table["table_index"]): table for table in report["tables"]
                         if table.get("continuation_candidate")}
            for candidate in report["candidates"]:
                raw_candidates[candidate["physical_page"]].append(candidate)
            for candidate in automatic_observations(report):
                projected[candidate.evidence.page].append(candidate)
        records = []
        for page in pages:
            record = {"physical_page": page, "observations": (), "recognition": (), "tables": (), "blocks": (),
                      "evidence": None, "error": recognition_error}
            if page not in pinned:
                records.append({**record, "status": "PAGE_UNAVAILABLE", "error": "PHYSICAL_PAGE_OUT_OF_RANGE"})
                continue
            ocr_error = None
            try:
                try:
                    evidence = document.evidence(page, tessdata=tessdata, compare_ocr=page in ocr_comparison)
                except (ValueError, RuntimeError, OSError) as exc:
                    if tessdata is None:
                        raise
                    ocr_error = "OCR_" + type(exc).__name__
                    evidence = document.evidence(page)
                blocks = [(list(block[:4]), clean(block[4])) for block in document.blocks(page) if block[6] == 0]
                tables, table_error = document.tables(page)
            except (ValueError, RuntimeError, OSError) as exc:
                records.append({**record, "status": "UNREADABLE", "observations": tuple(projected[page]),
                                "recognition": tuple(raw_candidates[page]), "error": "PAGE_" + type(exc).__name__})
                continue
            positioned = evidence["text_views"]["MUPDF_POSITIONED"]
            text_view = "MUPDF_POSITIONED" if readable(positioned) else evidence["method"]
            text_value = evidence["text_views"][text_view]
            hits = _matches(text_value, registry)
            project_id = hits[0]["entity_id"] if len(hits) == 1 else None
            if source.get("project_binding_status") == "UNRESOLVED_DISTINCT_PROJECT":
                project_id = None
            captures = _page_captures(sha, page, text_value, text_view, blocks, tables)
            raw = [*projected[page], *_project_page_captures(source, page, project_id, captures)]
            observations = tuple({_observation_discovery_key(row): row for row in raw}.values())
            status = "DISCOVERED" if observations else ("NO_CANDIDATES" if readable(evidence["text"]) else "UNREADABLE")
            errors = (recognition_error, ocr_error, table_error)
            grids = []
            for table in tables:
                related = continued.get((page, table["table_index"]))
                if related and related["cells"] == table["cells"] and related["bbox"] == table["bbox"]:
                    table = {**table, "continuation_candidate": related["continuation_candidate"]}
                grids.append(table)
            records.append({**record, "status": status, "observations": observations,
                            "recognition": tuple(raw_candidates[page]), "tables": tuple(grids),
                            "blocks": tuple(blocks), "evidence": evidence,
                            "error": "|".join(error for error in errors if error) or None})
        counts = dict(documents.counts)
    return {"source_sha256": sha, "source_key": source_key, "pages": records, "parser_operations": counts}
