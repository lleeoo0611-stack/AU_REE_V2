"""Freeze an automatic, source-first Phase 10 resource and technical holdout."""

import argparse
from collections import Counter, defaultdict
import csv
from hashlib import sha256
from io import StringIO
import json
from pathlib import Path
import re
import subprocess

import pymupdf

from .document_processing import DocumentUnavailable, PdfDocumentCache
from .selection_rules import date_end
from .store import digest


BASELINE = "dcda87e"
PRIOR_NLP = "76b429a8449acd3f34a952b6dce2fa95a8a2a937"
RELEASE = "results/ree-project-census/coverage-locked-20261125"
LOCK = "results/phase22-2026-11-06/snapshot_lock.json"
SEED = "AU-REE-PHASE10-SOURCE-FAMILIES-20261127"
OUTPUT = "results/phase10-2026-11-27/holdout_manifest.json"
KNOWN_INPUTS = (
    "results/normalization-pilot-20261125/case_review.json",
    "results/observation-shadow-20261126/review_split.json",
    "results/observation-shadow-20261126/decisions.jsonl",
    "results/ontology-gain-20261126/candidates.jsonl",
    "data/technical_benchmark.json",
    "data/phase16_remediation_held_labels.json",
)
NLP_INPUTS = (
    "results/nlp-census-ab-20261126/predictions.json",
    "data/validation/nlp_classification_adjudication_20261126.json",
    "data/validation/nlp_coordinate_adjudication_20261126.json",
    "data/validation/nlp_classification_pages_20261126.json",
    "data/validation/nlp_coordinate_pages_20261126.json",
    "data/validation/ontology_reference_20261126.json",
)
TOKENS = re.compile(r"\b(?:AU-[a-f0-9]{20}|[a-z0-9_]+)\b")
SHA = re.compile(r"[a-f0-9]{64}")
PROJECT = re.compile(r"AU-[a-f0-9]{20}")
RESOURCE = re.compile(r"\b(?:mineral resources?|resource estimates?|ore reserves?)\b", re.I)
TECHNICAL = re.compile(r"\b(?:leach\w*|metallurg\w*|beneficiation|flotation|recovery|pilot plant)\b", re.I)
REE = re.compile(r"\b(?:rare earths?|REE|REO|TREO|scandium|monazite|xenotime)\b", re.I)
UNIT = re.compile(r"(?<!\w)\d[\d, .]*\s*(%|ppm\b|g/t\b|Mt\b|kt\b|tonnes?\b)", re.I)
TECH_AMOUNT = re.compile(r"\b(?:recover\w*|extract\w*|leach\w*)\b[^.]{0,65}?"
                         r"\b\d+(?:\.\d+)?\s*%(?!\s*(?:owned|ownership))", re.I)
CLASS = re.compile(r"\b(?:Measured|Indicated|Inferred|Proved|Probable)\b", re.I)
TABLE = re.compile(r"\btable\s+[A-Z0-9]+(?:[.:–-]|\b)", re.I)
CUTOFF = re.compile(r"\bcut[- ]?off\b", re.I)
DENOMINATOR = re.compile(r"\b(?:whole[- ]ore|head grade|feed|concentrate|product|heavy mineral)\b", re.I)
SCOPE_BOUNDARY = re.compile(r"\b(?:ore reserves?|exploration target|historical estimate|"
                            r"targeted|conditional|previous estimate|proposed)\b", re.I)


class FrozenInputs:
    """Read the two pinned Git trees so later rule and test edits cannot change the draw."""

    def __init__(self, root):
        self.root = Path(root)
        self.baseline = self.git("rev-parse", f"{BASELINE}^{{commit}}").decode().strip()
        self.hashes = {}

    def git(self, *args):
        return subprocess.check_output(["git", "-C", self.root, *args])

    def read(self, path, *, revision=None):
        rev = revision or self.baseline
        contents = self.git("show", f"{rev}:{path}")
        label = path if revision is None else f"{revision}:{path}"
        self.hashes[label] = sha256(contents).hexdigest()
        return contents

    def json(self, path):
        return json.loads(self.read(path))

    def csv(self, path):
        return list(csv.DictReader(StringIO(self.read(path).decode("utf-8-sig"))))

    def audited_history(self):
        paths = self.git("ls-tree", "-r", "--name-only", self.baseline, "tests", "tools", "config/ontology")
        for path in sorted(set(paths.decode().splitlines()) | set(KNOWN_INPUTS)):
            if Path(path).suffix in {".py", ".json", ".jsonl"}:
                yield self.read(path).decode("utf-8")
        for path in NLP_INPUTS:
            yield self.read(path, revision=PRIOR_NLP).decode("utf-8")


def _entity_id(namespace, native_id):
    return "AU-" + digest([namespace, str(native_id)])[:20]


def _connect(graph, nodes):
    nodes = set(nodes)
    if nodes:
        first = min(nodes)
        for node in nodes - {first}:
            graph[first].add(node)
            graph[node].add(first)


def _reachable(graph, roots):
    visited = set(roots)
    remaining = list(roots)
    while remaining:
        fresh = graph[remaining.pop()] - visited
        visited.update(fresh)
        remaining.extend(fresh)
    return visited


def _source_graph(inputs, registry, snapshots, lock):
    graph, projects, native_projects = defaultdict(set), defaultdict(set), defaultdict(set)
    claims = inputs.json("data/claims.json")
    for row in claims["projects"]:
        project = _entity_id(row.get("entity_namespace", "project_registry_v1"), row["id"])
        native_projects[str(row["id"])].add(project)
        projects["key:" + row["identity_source"]].add(project)
        for observation in row["observations"]:
            key, sha = observation.get("source_key"), observation.get("source_sha256")
            if key:
                projects["key:" + key].add(project)
            if sha:
                projects["sha:" + sha].add(project)
                if estimate := observation.get("statement_id"):
                    _connect(graph, ["sha:" + sha, "statement_id:" + estimate])
    identity = inputs.json("data/identity_links.json")
    for relation in [*identity["links"], *identity["relations"]]:
        _connect(graph, [_entity_id(*relation[k]) for k in ("left", "right", "canonical") if k in relation])
    for row in (*registry, *snapshots, *lock):
        if row["kind"] != "pdf":
            continue
        key = "key:" + row["key"]
        nodes = [key, *("sha:" + row[k] for k in
                       ("sha256", "source_sha256", "committed_snapshot_sha256", "reviewed_static_pdf_sha256")
                       if row.get(k) and SHA.fullmatch(row[k]))]
        for attr in ("url", "document_identity", "report_native_id"):
            if row.get(attr):
                nodes.append(attr + ":" + str(row[attr]))
        _connect(graph, nodes)
        projects[key].update(row.get("summary_project_ids") or [])
        projects[key].update(native_projects.get(row.get("recognition_project_native_id"), ()))
    for row in inputs.csv(f"{RELEASE}/resource_statement_observations.csv"):
        if not row["source_sha256"] or not row["project_id"]:
            continue
        source = "sha:" + row["source_sha256"]
        projects[source].add(row["project_id"])
        _connect(graph, [source, *(f"{field}:{row[field]}" for field in ("statement_id", "statement_group_id",
                                                                       "source_statement_key") if row[field])])
    return graph, projects


def _exclusions(inputs, known_keys, projects, graph):
    known, known_pages = set(), set()
    for text in inputs.audited_history():
        known_pages.update(re.findall(r'"(?:page:|source_page_sha256"\s*:\s*")([a-f0-9]{64})"', text))
        for token in set(TOKENS.findall(text)):
            if token in known_keys:
                known.add("key:" + token)
            elif PROJECT.fullmatch(token):
                known.add(token)
            elif SHA.fullmatch(token):
                known.add("sha:" + token)
    # Earlier automatic recognition/sealed page outputs are previous source-use evidence.
    for snapshot in inputs.json("data/manifest.json")["snapshots"]:
        if snapshot["kind"] in {"document_extraction", "pdf_page_extraction"} and snapshot.get("source_sha256"):
            known.add("sha:" + snapshot["source_sha256"])
    known = _reachable(graph, known)
    # Multi-project collections are excluded themselves. They do not imply that an
    # estimate for one project is the same as an unrelated project in that PDF.
    project_nodes = {project for node in known for project in projects[node]}
    return _reachable(graph, known | project_nodes), known_pages


def _candidate_alias(name):
    return re.split(r"\s+[—–]|\s+(?:REE\b|Rare Earths?\b|Mineral Sands\b|Li[–-]REE|"
                    r"Scandium\b|Project\b|Kaolin\b)", name, maxsplit=1, flags=re.I)[0].strip()


def _page_signals(document, alias, known_pages, other_projects):
    """Stratify source text only. These indicators are neither values nor reference labels."""
    bound = re.compile(r"(?<!\w)" + re.escape(alias) + r"(?!\w)", re.I)
    signals = {}
    for page in range(1, len(document) + 1):
        positioned = " ".join(document.text(page, positioned=True).split())
        if len(positioned) >= 160 and sha256(positioned.encode()).hexdigest() in known_pages:
            return {}, "DUPLICATE_PRIOR_PAGE"
        # A different project can dominate an annual report, even when the
        # registry uses it as identity evidence for the held-out Project.
        if RESOURCE.search(positioned) and other_projects.search(positioned):
            for match in other_projects.finditer(positioned):
                nearby = positioned[max(0, match.start() - 55):match.end() + 145]
                if RESOURCE.search(nearby) and UNIT.search(nearby) and REE.search(nearby):
                    return {}, "PRIOR_PROJECT_ESTIMATE_REPRINT_CUE"
        if not bound.search(positioned):
            continue
        blocks = [" ".join(block[4].split()) for block in document.blocks(page) if block[6] == 0]
        local = [block for block in blocks if bound.search(block)]
        flags = {"PROJECT_TEXT"}
        if any(RESOURCE.search(block) and UNIT.search(block) for block in local):
            flags.add("RESOURCE_QUANTITY_CUE")
        if any(TECH_AMOUNT.search(block) and not other_projects.search(block) for block in local):
            flags.add("TECHNICAL_QUANTITY_CUE")
        elif TECHNICAL.search(positioned) and other_projects.search(positioned):
            flags.add("TECHNICAL_CROSS_PROJECT_CONTEXT_CUE")
        if REE.search(positioned):
            flags.add("REE_MENTION")
        for key, pattern in (("TABLE_CAPTION_CUE", TABLE), ("CUTOFF_CUE", CUTOFF),
                             ("JORC_CLASS_CUE", CLASS), ("MATERIAL_DENOMINATOR_CUE", DENOMINATOR),
                             ("ALTERNATE_SCOPE_CUE", SCOPE_BOUNDARY)):
            if any(pattern.search(block) for block in local):
                flags.add(key)
        for block in local:
            flags.update("UNIT:" + unit.lower() for unit in UNIT.findall(block))
        if flags & {"RESOURCE_QUANTITY_CUE", "TECHNICAL_QUANTITY_CUE"} and DENOMINATOR.search(positioned):
            flags.add("PAGE_MATERIAL_DENOMINATOR_CUE")
        signals[page] = flags
    return signals, None


def _sample_pages(signals, sha):
    priority = {"RESOURCE_QUANTITY_CUE", "TECHNICAL_QUANTITY_CUE", "TECHNICAL_CROSS_PROJECT_CONTEXT_CUE"}
    candidates = sorted(signals, key=lambda page: (-len(signals[page] & priority), -len(signals[page]),
                                                    digest([SEED, sha, page])))
    values = [page for page in candidates if signals[page] & priority][:3]
    if not values:
        values = candidates[:2]
    # Adjacent pages are potential context. This is a page-layout test, not a
    # declaration that the adjacent text proves the quantity or its scope.
    context = {neighbor for page in values for neighbor in (page - 1, page + 1)
               if neighbor in signals and neighbor not in values}
    return sorted(values), sorted(context)[:4]


def select(root, assets):
    """Use fixed publications, group editions, then select one report per Project family."""
    inputs = FrozenInputs(root)
    registry = inputs.json("config/sources.json")["sources"]
    lock = inputs.json(LOCK)
    receipt = inputs.json(f"{RELEASE}/source_acquisition.json")
    snapshots = receipt["snapshots"]
    cutoff = receipt["cutoff"]
    decisions = {(r["key"], r["source_sha256"]): r for r in inputs.csv(f"{RELEASE}/source_selection.csv")}
    census = {r["專案ID"]: r for r in inputs.csv(f"{RELEASE}/REE project census.csv")}
    graph, projects = _source_graph(inputs, registry, snapshots, lock)
    known, known_pages = _exclusions(inputs, {r["key"] for r in (*registry, *snapshots, *lock)}, projects, graph)
    locked_shas = {r["sha256"] for r in lock if r["kind"] == "pdf"}
    prior_aliases = {_candidate_alias(census[pid]["專案名稱"]) for pid in known & census.keys()}
    aliases = sorted((alias for alias in prior_aliases if len(alias) >= 5), key=lambda alias: (-len(alias), alias))
    other_projects = re.compile(r"(?<!\w)(?:" + "|".join(map(re.escape, aliases)) + r")(?!\w)", re.I) \
        if aliases else re.compile(r"(?!)")
    counts, choices = Counter(), []
    eligible_shas = set()
    with PdfDocumentCache(assets, max_documents=1) as documents:
        for source in sorted(snapshots, key=lambda row: (row["key"], row["sha256"])):
            if source["kind"] != "pdf":
                continue
            sha, key = source["sha256"], source["key"]
            result = decisions.get((key, sha), {})
            group = _reachable(graph, {"sha:" + sha})
            bound = {p for node in group for p in projects[node]}
            canonical = set()
            for project in bound:
                linked = _reachable(graph, {project}) & census.keys()
                canonical.update(linked or {project})
            if (result.get("cutoff_status") != "WITHIN_CUTOFF"
                    or result.get("version_status") not in {"PINNED_SHA_VERIFIED", "RECEIPT_SHA_VERIFIED"}
                    or not result.get("date_used") or date_end(result["date_used"]) > cutoff):
                counts["OUTSIDE_VERIFIED_CUTOFF"] += 1
            elif group & known or bound & known or canonical & known:
                counts["PRIOR_USE_OR_LINKED_FAMILY"] += 1
            elif len(canonical) != 1 or not canonical <= census.keys():
                counts["PROJECT_BINDING_ABSENT_OR_AMBIGUOUS"] += 1
            elif sha in eligible_shas:
                counts["SAME_SHA"] += 1
            else:
                eligible_shas.add(sha)
                project, = canonical
                metadata = census[project]
                alias = _candidate_alias(metadata["專案名稱"])
                if len(alias) < 4:
                    counts["NO_DISTINCT_PROJECT_MARKER"] += 1
                    continue
                try:
                    document = documents.open(sha)
                    signals, reuse_issue = _page_signals(document, alias, known_pages, other_projects)
                except (DocumentUnavailable, RuntimeError):
                    counts["UNAVAILABLE_OR_UNREADABLE_ORIGINAL"] += 1
                    continue
                if reuse_issue:
                    counts[reuse_issue] += 1
                    continue
                if not signals:
                    counts["NO_NATIVE_PROJECT_MARKER"] += 1
                    continue
                pages, context = _sample_pages(signals, sha)
                tags = {tag for page in pages + context for tag in signals[page]} - {"PROJECT_TEXT"}
                quantitative = tags & {"RESOURCE_QUANTITY_CUE", "TECHNICAL_QUANTITY_CUE"}
                if not quantitative and not tags & {"REE_MENTION", "ALTERNATE_SCOPE_CUE"}:
                    counts["NO_SOURCE_TOPIC_CUE"] += 1
                    continue
                family_members = sorted(group | _reachable(graph, {project}))
                choices.append({
                    "source_key": key, "source_sha256": sha, "pages": pages, "context_pages": context,
                    "validation": {
                        "role": "UNSEEN_REGISTERED_FAMILY", "project_id": project,
                        "project_name": metadata["專案名稱"], "document_family": digest([project, family_members]),
                        "edition_bound_family_nodes": family_members, "physical_page_count": len(document),
                        "publication_date": source.get("publication_date"), "acquired_at": source["acquired_at"],
                        "available_date": source["available_date"],
                        "cutoff_date_basis": result["date_basis"], "source_url": source["url"],
                        "also_in_phase22_lock": sha in locked_shas,
                        "deposit": metadata["礦床型態代碼"] or None, "stage": metadata["開發階段代碼"] or None,
                        "selection_cues": sorted(tags),
                        "page_cues": {str(page): sorted(signals[page]) for page in pages + context},
                    }
                })
    # Prefer more distinct substantive topics within each fully held-out Project.
    priorities = {"RESOURCE_QUANTITY_CUE", "TECHNICAL_QUANTITY_CUE", "TECHNICAL_CROSS_PROJECT_CONTEXT_CUE"}
    family_choices = {}
    for choice in sorted(choices, key=lambda row: (-len(priorities & set(row["validation"]["selection_cues"])),
                                                   -len(row["validation"]["selection_cues"]),
                                                   digest([SEED, row["source_sha256"]]))):
        family_choices.setdefault(choice["validation"]["project_id"], choice)
    rows = sorted(family_choices.values(), key=lambda row: row["source_key"])
    counts["AVAILABLE_ELIGIBLE_BEFORE_PROJECT_DEDUP"] = len(choices)
    return {
        "schema": "resource-admission-frame-v1", "classification": "PUBLIC_REAL_SOURCE_REPLAY",
        "design": "Pre-rule SHA-bound document families and physical pages selected from registered originals.",
        "retrieval": {"mode": "fixed"},
        "validation": {
            "frozen_before_phase10_rule_evaluation": True, "baseline_commit": inputs.baseline,
            "cutoff": cutoff, "seed": SEED, "source_receipt": f"{RELEASE}/source_acquisition.json",
            "selection_strategy": "Group pinned SHA, source key, report ID, URL, canonical Project and estimate "
                                  "identity. Exclude historical reference, fixture, benchmark, prior retrieval "
                                  "queues, recognition families, duplicate pages and prior estimate reprints. Rank "
                                  "same-block topic/unit cues, then seeded "
                                  "hash, without any extractor, validator or admission result.",
            "screened_census_projects_with_prior_use": len(known & census.keys()),
            "selection_counts": dict(counts),
            "selected_cue_counts": dict(Counter(cue for row in rows for cue in row["validation"]["selection_cues"])),
            "known_limitations": [
                "Unseen relative to the audited repository evidence, tests and reference artifacts.",
                "Archived deposit and stage are sampling descriptors only; prior identity-registration use is "
                "eligible absent a prior scientific/verification case or linked estimate.",
                "Text signals identify possible scope and context. JORC, contradiction, scientific completeness and "
                "independent accuracy remain unmeasured without an independent reference.",
                "Originals required for rerun are byte-identical to the frozen receipt. Keep missing editions blocked.",
            ],
            "inputs_sha256": inputs.hashes,
            "generator_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
            "pymupdf": pymupdf.VersionBind,
        },
        "sources": rows,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--assets", type=Path, required=True)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    manifest = select(args.root, args.assets)
    if not manifest["sources"]:
        raise SystemExit("No verified unseen source family remains")
    out = args.out or args.root / OUTPUT
    out.parent.mkdir(exist_ok=True, parents=True)
    payload = json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if out.exists():
        if out.read_text(encoding="utf-8") != payload:
            raise SystemExit("Existing holdout differs. Freeze a separate manifest and keep the original.")
    else:
        with out.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(payload)


if __name__ == "__main__":
    main()
