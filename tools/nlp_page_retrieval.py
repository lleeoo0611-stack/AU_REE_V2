"""Compare the existing Census rule page trail with an additional BM25 review queue."""
import csv
import json
import math
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path


# Field vocabulary is fixed for the experiment. No document, project, expected page,
# mineral deposit label, or text from an adjudication is part of this vocabulary.
FIELD_TERMS = {
    "coordinate": "latitude longitude coordinate coordinates datum projection grid easting northing "
                  "location map tenement tenements licence licences license licenses granted relinquished "
                  "boundary boundaries locality gda94 gda2020 mga94 mga2020 wgs84",
    "deposit": "deposit deposits geology geological mineralisation mineralization host hosted lithology "
               "regolith saprolite laterite clay ionic adsorption hardrock carbonatite pegmatite "
               "alkaline alluvial placer heavy mineral sands",
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
SHA = re.compile(r"[0-9a-f]{64}")
WORDS = re.compile(r"[^\W_]+", re.UNICODE)


def _tokens(text):
    text = unicodedata.normalize("NFKC", text).casefold()
    text = re.sub(r"(?<=\w)[-‐‑]\s*\n\s*(?=\w)", "", text)
    return WORDS.findall(text)


def _page_numbers(value):
    # A single source can have multiple explicit pages. Never take the Cartesian
    # product of multiple source hashes and multiple unpaired page numbers.
    fields = str(value or "").split(";")
    if all(re.fullmatch(r"[1-9][0-9]*", number.strip()) for number in fields):
        return [int(number) for number in fields]
    return []


def _source_pages(record):
    if isinstance(record, list):
        for item in record:
            yield from _source_pages(item)
    elif isinstance(record, dict):
        for sha_field, page_field in (("source_sha256", "pdf_page"),
                                      ("source_sha256", "physical_page"), ("source_sha256", "page"),
                                      ("notice_sha256", "physical_page"), ("scope_report_sha256", "scope_report_page")):
            sha = record.get(sha_field, "")
            if isinstance(sha, str) and SHA.fullmatch(sha):
                for number in _page_numbers(record.get(page_field)):
                    yield sha, number
        for item in record.values():
            if isinstance(item, (dict, list)):
                yield from _source_pages(item)


def rule_pages(release_dir):
    """Read page witnesses emitted by the unchanged rules, keyed by (project_id, family).

    Page pairs from supportive and rejected witnesses both count as retrieval candidates.
    Only explicit source-page bindings are used. Reviewer-authored gap notes and gold
    references never enter this baseline. Within a file, retain its emitted row order.
    """
    directory = Path(release_dir)
    queues = defaultdict(dict)
    files = (("field_provenance.csv", None, None), ("field_status.csv", None, "findings"),
             ("milestone_events.csv", "stage", None),
             ("spatial_point_quality.csv", "coordinate", "review_details"))
    for filename, default_family, nested_field in files:
        with (directory / filename).open(encoding="utf-8-sig", newline="") as stream:
            for row in csv.DictReader(stream):
                family = default_family or FAMILIES.get(row["column"])
                if not family:
                    continue
                record = json.loads(row[nested_field] or "[]") if nested_field else row
                for pair in _source_pages(record):
                    queues[row["project_id"], family][pair] = None
    return {key: tuple(pairs) for key, pairs in queues.items()}


class PageIndex:
    """One SHA/page-addressed text pool, shared by both arms of a query."""

    def __init__(self, pages):
        self.page_keys = set()
        self.documents = {}
        self.lengths = {}
        self.df = Counter()
        for sha, number, text in pages:
            key = sha, number
            if not SHA.fullmatch(sha) or type(number) is not int or number < 1 or not isinstance(text, str):
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
            augmented.extend(key for _, key in sorted(ranked)[:k-len(baseline)])
        return {"rules": baseline, "rules_nlp": augmented}


def rank_pair(pages, aliases, field, baseline_pages=(), *, k=5):
    """Convenience wrapper when a project has only one field query."""
    return PageIndex(pages).rank_pair(aliases, field, baseline_pages, k=k)
