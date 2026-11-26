"""Rule-based source-bound extraction and BM25 evidence-page retrieval."""
import math
import re
import unicodedata
from collections import Counter, defaultdict
from typing import Protocol

from .document_processing import PdfDocumentCache, SHA256
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


class PageIndex:
    """One SHA/page-addressed text pool, shared by both arms of a query."""

    def __init__(self, pages):
        self.page_keys = set()
        self.documents = {}
        self.lengths = {}
        self.df = Counter()
        for sha, number, text in pages:
            key = sha, number
            if (not isinstance(sha, str) or not SHA256.fullmatch(sha) or type(number) is not int
                    or number < 1 or not isinstance(text, str)):
                raise ValueError("A page needs a SHA-256, a positive physical page and text")
            if key in self.page_keys:
                raise ValueError("Duplicate PDF edition and physical page")
            self.page_keys.add(key)
            words = _tokens(text)
            if words:
                terms = Counter(words)
                self.documents[key] = terms
                self.lengths[key] = len(words)
                self.df.update(terms.keys())
        count = len(self.documents)
        self.average_length = sum(self.lengths.values()) / count if count else 0

    @classmethod
    def from_documents(cls, documents: PdfDocumentCache, source_hashes):
        """Rank physical pages in verified editions, using the historical positioned view."""
        return cls((sha, page, document.text(page, positioned=True))
                   for sha in dict.fromkeys(source_hashes)
                   for document in (documents.open(sha),)
                   for page in range(1, len(document) + 1))

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
        baseline = list(dict.fromkeys(tuple(pair) for pair in baseline_pages
                                      if tuple(pair) in self.page_keys))[:k]
        augmented = list(baseline)
        if len(augmented) < k and self.documents:
            if isinstance(aliases, str):
                aliases = [aliases]
            names = {word for alias in aliases for word in _tokens(alias)
                     if len(word) > 1 and word not in GENERIC_NAMES}
            terms = set(_tokens(FIELD_TERMS[family]))
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


class BoundObservationExtractor(Protocol):
    """Contract for candidate extraction from the fixed source and page frame."""

    def __call__(self, resource_candidates, technical_captures, documents: PdfDocumentCache): ...


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
        resource.extend(extract_resource_observations(resource_sources[sha], documents.assets, documents=documents))
        technical.extend(reextract_technical(technical_sources[sha], documents.assets, documents=documents))
    return (sorted(resource, key=lambda row: row["candidate_id"]),
            sorted(technical, key=lambda row: row["candidate_id"]))


RECOGNITION_PROJECTION_VERSION = "document-recognition-observations-v1"
STRATEGIC_ANALYTES = frozenset({"Nd2O3", "Pr6O11", "Dy2O3", "Tb4O7"})


def _reported_quantities(candidate):
    """Yield the native tokens already bound by the document recognizer."""
    kind = candidate["kind"]
    if kind == "RESOURCE_TABLE_TOTAL":
        tokens = candidate["original_tokens"]
        for default_index, variable in enumerate(("ore_mt", "grade")):
            index = (candidate.get("row_token_indices") or {}).get(variable, default_index)
            if index < len(tokens):
                yield "RESOURCE", variable, tokens[index], candidate["units"].get(variable), {}
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
                            "claim_nature": number.get("evidence_nature")})
        elif candidate.get("domain") in {"Development", "Commercial"}:
            yield "EVENT", candidate["domain"].lower() + "_event_mention", None, None, {}


def automatic_observations(report):
    """Project a cached automatic recognition report into raw review candidates."""
    from .observation_pipeline import raw_from_candidate
    from .store import digest

    source_sha256 = report["source_sha256"]
    source_key = report["source_key"]
    extraction_version = RECOGNITION_PROJECTION_VERSION + "/" + report["version"]
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
