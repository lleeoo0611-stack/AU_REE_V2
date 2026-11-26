"""Freeze and audit source-based reference packets for semantic extraction."""
import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

import pymupdf

from au_ree_v2.store import filehash
from tools.ontology_gain_inventory import RELEASE, ROOT, jsonl, report, rows, stable_id


BASE = ROOT / "results/ontology-gain-20261126"
PORTFOLIO = ROOT / "config/ontology/portfolio_statement_evidence_v1.json"
OUTPUT = ROOT / "results/observation-shadow-20261126"
SEED = "AU-REE-OBSERVATIONS-20261126-R1"
COMMIT = "d993ebd5bcbe8915e98d469ad91d6646f04ff3ab"
INVENTORY = ("document_candidates.csv", "document_versions.csv", "document_entity_relations.csv",
             "technical_cells.csv")
PROFILES = ("DIRECT_RESOURCE_UNIT_COMPARISON_V1", "WITHIN_TABLE_ELEMENT_LEACH")
OLD_NORMALIZATION = ROOT / "results/normalization-pilot-20261125/case_review.json"
OLD_ONTOLOGY = ROOT.parent / "ie20/data/validation/ontology_reference_20261126.json"
# Named earlier follow-up reviews that predate the ontology comparison fixtures.
EARLIER_REVIEWED_PROJECTS = ("AU-216d0983f6892f9b58f9", "AU-6d807eb7caec9db0f35e",
                            "AU-447261eed0e81eae88bf", "AU-d9fb1b1e3e2ec9fa0851")
STATE = {"CONFIRMED", "INCOMPATIBLE", "INSUFFICIENT", "NOT_REVIEWED"}
PDF_HEADINGS = {
    "RESOURCE": re.compile(r"\b(mineral resources?|resource estimate|ore reserves?)\b", re.I),
    "TECHNICAL": re.compile(r"\b(leach\w*|recovery|flotation|metallurg\w*)\b", re.I),
}
ARMS = ("E0V0", "E0V1", "E1V0", "E1V1")
REVIEW_FIELDS = ("project_id", "quantity", "token", "unit", "context", "verdict",
                 "quote", "token_occurrence_in_quote")


def clean(source):
    return " ".join(str(source).split()) if source is not None else ""


def json_rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def historical_case_ids(baseline, assertions):
    candidate_ids = {row["candidate_id"] for path in baseline.glob("source_review_*.jsonl") for row in json_rows(path)}
    for section in ("assertions", "negative_controls", "selected_witnesses", "selected_witnesses_excluded"):
        for record in assertions[section]:
            candidate_ids.add(record["candidate_id"])
            if record.get("target_candidate_id"):
                candidate_ids.add(record["target_candidate_id"])
    return candidate_ids


class Components:
    def __init__(self):
        self.parent = {}

    def root(self, node):
        self.parent.setdefault(node, node)
        while self.parent[node] != node:
            self.parent[node] = self.parent[self.parent[node]]
            node = self.parent[node]
        return node

    def link(self, nodes):
        roots = sorted({self.root(node) for node in nodes})
        for node in roots[1:]:
            self.parent[node] = roots[0]

    def grouped(self):
        groups = defaultdict(set)
        for node in self.parent:
            groups[self.root(node)].add(node)
        return list(groups.values())


def study_frame(release, run, baseline, assertions, legacy_exclusions):
    """Group by durable Project, duplicate page/statement family and document versions."""
    census_ids = {r["專案ID"] for r in rows(release / "REE project census.csv")}
    receipts = {row["source_sha256"]: row for row in rows(release / "source_selection.csv")
                if row["kind"] == "pdf" and row["cutoff_status"] == "WITHIN_CUTOFF"}
    observations = json_rows(baseline / "candidates.jsonl")
    historically_reviewed = historical_case_ids(baseline, assertions)
    components = Components()
    known = {"source:" + sha for sha in legacy_exclusions["normalization_source_sha256"]}
    known.update("project:" + p for p in legacy_exclusions["older_ontology_projects"])
    known.update("project:" + p for p in EARLIER_REVIEWED_PROJECTS)
    bindings = defaultdict(set)
    strata = defaultdict(set)
    for row in observations:
        project, source = row["project_id"], row["source_sha256"]
        if row["split"] == "HOLDOUT" or row["candidate_id"] in historically_reviewed:
            known.add("project:" + project)
        if row["source_kind"] != "pdf":
            continue
        components.link(["project:" + project, "source:" + source, *row["report_families"]])
        if project in census_ids and source in receipts:
            bindings[source].add(project)
            strata[source].add("RESOURCE")
    for row in rows(run / "document_candidates.csv"):
        project, source = row["project_id"], row["source_sha256"]
        if project and source:
            components.link(["project:" + project, "source:" + source])
        domain = row["domain"].upper()
        if project in census_ids and source in receipts and domain in PDF_HEADINGS:
            bindings[source].add(project)
            strata[source].add(domain)
    for row in rows(run / "document_versions.csv"):
        if row["project_id"] and row["source_sha256"]:
            keys = ["project:" + row["project_id"], "source:" + row["source_sha256"]]
            if row["replaces_source_sha256"]:
                keys.append("source:" + row["replaces_source_sha256"])
            components.link(keys)
    for row in rows(run / "document_entity_relations.csv"):
        if row["parent_id"] and row["child_id"]:
            components.link(["project:" + row["parent_id"], "project:" + row["child_id"]])
    for row in rows(run / "technical_cells.csv"):
        known.add("project:" + row["project_id"])
    for path in (ROOT / "data/validation").glob("ontology_reference_*.json"):
        for control in json.loads(path.read_bytes())["controls"]:
            for side in ("left", "right"):
                known.add("project:" + control[side]["project_id"])
    groups = []
    for nodes in components.grouped():
        all_sources = sorted(n[7:] for n in nodes if n.startswith("source:"))
        sources = [source for source in all_sources if source in bindings]
        if sources:
            groups.append({"group_id": stable_id(sorted(nodes)), "members": sorted(nodes),
                           "projects": sorted(n[8:] for n in nodes if n.startswith("project:")),
                           "source_sha256": sources, "linked_source_sha256": all_sources,
                           "strata": sorted({d for s in sources for d in strata[s]}),
                           "historical_review": any(node in known for node in nodes)})
    groups.sort(key=lambda g: g["group_id"])
    return groups, bindings, strata, receipts


def choose_groups(groups):
    """Choose two available components per stratum; components can cover both."""
    selected = set()
    for stratum in sorted(PDF_HEADINGS):
        choices = [g for g in groups if stratum in g["strata"] and not g["historical_review"]]
        order = sorted(choices, key=lambda g: stable_id(SEED, stratum, g["group_id"]))
        selected.update(g["group_id"] for g in order[:2])
    return selected


def packet_sources(groups, quarantined, bindings, strata, receipts):
    result = []
    for group in groups:
        if group["group_id"] not in quarantined:
            continue
        for sha in group["source_sha256"]:
            r = receipts[sha]
            result.append({"source_sha256": sha, "source_key": r["key"], "project_ids": sorted(bindings[sha]),
                           "group_id": group["group_id"], "strata": sorted(strata[sha]),
                           "publication_date": r["publication_date"], "available_date": r["available_date"]})
    return sorted(result, key=lambda r: r["source_sha256"])


def freeze_manifest(release, run, baseline, legacy_exclusions):
    assertion_rules = json.loads(PORTFOLIO.read_bytes())
    groups, bindings, strata, receipts = study_frame(release, run, baseline, assertion_rules, legacy_exclusions)
    selected = choose_groups(groups)
    if not selected:
        raise ValueError("No source component remains after historical review quarantine")
    chosen = [g for g in groups if g["group_id"] in selected]
    for group in groups:
        group["partition"] = "HELD_OUT" if group["group_id"] in selected else "DEVELOPMENT"
    checksums = {f: filehash(run / f) for f in INVENTORY}
    checksums.update({f: filehash(release / f) for f in ("source_selection.csv", "REE project census.csv")})
    checksums.update({f.name: filehash(f) for f in baseline.glob("source_review_*.jsonl")})
    checksums.update({"portfolio_statement_evidence_v1.json": filehash(PORTFOLIO),
                      "candidates.jsonl": filehash(baseline / "candidates.jsonl")})
    release_data = json.loads((release / "census_release.json").read_bytes())
    return {"schema": "source-holdout-v1", "commit": COMMIT, "cutoff": release_data["cutoff"], "seed": SEED,
            "profile_slots": list(PROFILES), "selection": "Two SHA-seeded Project/source/statement components per domain; "
            "prior review, worked assertions, previous holdout and prior technical table projects blocked from reuse. "
            "Scope is projects with source receipts plus preexisting document or resource registry bindings.",
            "historical_review_exclusions": legacy_exclusions,
            "earlier_followup_review_projects": list(EARLIER_REVIEWED_PROJECTS),
            "independent_validation_pending": True, "input_sha256": checksums, "groups": groups,
            "quarantine_projects": sorted({p for g in chosen for p in g["projects"]}),
            "quarantine_source_sha256": sorted({s for g in chosen for s in g["linked_source_sha256"]}),
            "packet_sources": packet_sources(groups, selected, bindings, strata, receipts)}


def history(source):
    older = json.loads(source.read_bytes())
    projects = {r[side]["project_id"] for r in older["controls"] for side in ("left", "right")}
    return {"normalization_source_sha256": sorted(json.loads(OLD_NORMALIZATION.read_bytes())["documents"]),
            "normalization_input_sha256": filehash(OLD_NORMALIZATION),
            "older_ontology_input_sha256": filehash(source),
            "older_ontology_projects": sorted(projects)}


def freeze(output, release, run, baseline, legacy_exclusions):
    output.mkdir(parents=True, exist_ok=True)
    manifest = freeze_manifest(release, run, baseline, legacy_exclusions)
    destination = output / "review_split.json"
    if destination.exists() and json.loads(destination.read_bytes()) != manifest:
        raise ValueError("Use a new output path for a different source partition")
    report(destination, manifest)
    return manifest


def check_asset(assets, sha):
    asset = assets / sha
    if not asset.is_file() or filehash(asset) != sha:
        raise ValueError(f"Expected hash-verified original {sha}")
    return asset


def select_pages(texts, strata, source_sha):
    """Stratify original pages by topic cues, independent of either extractor's output."""
    selected = defaultdict(set)
    for stratum in strata:
        population = [n for n, body in texts.items() if PDF_HEADINGS[stratum].search(body)]
        order = sorted(population, key=lambda n: stable_id(SEED, source_sha, stratum, n))
        for number in order[:3]:
            selected[number].add(stratum)
    control = [n for n, body in texts.items() if body and not any(PDF_HEADINGS[s].search(body) for s in strata)]
    if control:
        selected[min(control, key=lambda n: stable_id(SEED, source_sha, "GENERAL", n))].add("GENERAL")
    return {n: sorted(strata) for n, strata in sorted(selected.items())}


def prepare_packet(split, assets, output, release=RELEASE):
    manifest = json.loads(split.read_bytes())
    receipt_path = release / "source_selection.csv"
    if filehash(receipt_path) != manifest["input_sha256"]["source_selection.csv"]:
        raise ValueError("The source receipt differs from the frozen packet input")
    receipts = {row["source_sha256"]: row for row in rows(receipt_path)}
    pages, documents = [], []
    for source in manifest["packet_sources"]:
        sha = source["source_sha256"]
        receipt = receipts[sha]
        source = {**source, "cutoff_date_basis": receipt["date_basis"],
                  "cutoff_date_used": receipt["date_used"], "cutoff_status": receipt["cutoff_status"]}
        with pymupdf.open(check_asset(assets, sha)) as pdf:
            texts = {i + 1: clean(page.get_text(sort=True)) for i, page in enumerate(pdf)}
        selected = select_pages(texts, source["strata"], sha)
        documents.append({**source, "physical_pages": len(texts),
                          "empty_native_text_pages": sum(not body for body in texts.values()),
                          "sample_frame_counts": {
                              s: sum(bool(PDF_HEADINGS[s].search(t)) for t in texts.values()) for s in source["strata"]},
                          "sampled_physical_pages": list(selected)})
        for number, strata in selected.items():
            pages.append({**source, "page_id": stable_id(sha, number), "physical_page": number,
                          "selection_strata": strata, "text_available": bool(texts[number]),
                          "cross_page_context_available_from_same_original": True})
    output.mkdir(parents=True, exist_ok=True)
    packet = output / "review_pages.jsonl"
    jsonl(packet, pages)
    report(output / "review_packet_manifest.json", {
        "source_group_manifest_sha256": filehash(split), "source_page_packet_sha256": filehash(packet),
        "seed": manifest["seed"], "cutoff": manifest["cutoff"], "page_count": len(pages),
        "source_count": len(documents), "documents": documents,
        "sampling": "Three source-topic-cue pages and one non-cue page per frozen document and topical stratum. "
                    "Sampled pages are fixed by a seeded SHA order; no predictions or reference answers enter selection.",
        "denominator_scope": "Sampled physical pages. Counts do not estimate whole-corpus extraction performance.",
        "independent_review": "PENDING", "reference_fields": list(REVIEW_FIELDS),
    })
    report(output / "review_reference_template.json", {
        "schema": "semantic-observation-reference-v1", "packet_sha256": filehash(packet),
        "review_kind": "PENDING", "reviewer_id": "", "reviewed_without_predictions": None,
        "adjudication_reference": "", "pages": [{"page_id": p["page_id"], "enumeration": "NOT_REVIEWED",
                                                "observations": []} for p in pages],
        "relation_review": "NOT_REVIEWED", "relations": [],
    })
    return pages


def located_token(source_text, quote, token, occurrence=None):
    """Canonical token offset in the original page. Ambiguous quotations stay unresolved."""
    quote = clean(quote)
    token = clean(token)
    if not quote or not token:
        return None
    hits = list(re.finditer(re.escape(quote), source_text))
    if len(hits) != 1:
        return None
    local = list(re.finditer(r"(?<![0-9,.])" + re.escape(token) + r"(?![0-9,.])", quote))
    if occurrence is None:
        if len(local) != 1:
            return None
        occurrence = 0
    if type(occurrence) is not int or occurrence < 0 or occurrence >= len(local):
        return None
    return hits[0].start() + local[occurrence].start()


def rate(count, denominator):
    return {"numerator": count, "denominator": denominator,
            "rate": count / denominator if denominator else None}


def identify_predictions(decisions, packet, texts, arm):
    predictions = defaultdict(list)
    unlocated = []
    extractor = arm[:2].lower()
    for row in decisions:
        slot = row["source_sha256"], row["physical_page"]
        page = packet.get(slot)
        if page is None:
            continue
        observed = row.get(extractor)
        if not observed or not observed.get("native") or observed["native"].get("token") is None:
            continue
        native = observed["native"]
        extracted = {
            "candidate_id": row["candidate_id"], "project_id": row["project_id"], "native": native,
            "context": observed.get("context", {}), "disposition": row[arm]["status"],
        }
        position = measurement_location(observed, page, texts[page["page_id"]])
        if position is not None:
            predictions[position].append(extracted)
        else:
            unlocated.append(extracted)
    return predictions, unlocated


def measurement_location(observed, page, source_text):
    positions = set()
    for anchor in observed.get("anchors", []):
        if (anchor.get("source_sha256", page["source_sha256"]) != page["source_sha256"]
                or anchor.get("page", anchor.get("physical_page", page["physical_page"])) != page["physical_page"]):
            continue
        quote = anchor.get("quote", anchor.get("text", anchor.get("snippet", "")))
        position = located_token(source_text, quote, observed["native"]["token"])
        if position is not None:
            positions.add(position)
    return (page["page_id"], positions.pop()) if len(positions) == 1 else None


def compare_reference(packet_path, reference, decisions, assets, relations=None):
    records = json_rows(packet_path)
    if reference["packet_sha256"] != filehash(packet_path):
        raise ValueError("Independent labels refer to a different source packet")
    page_set = {p["page_id"]: p for p in records}
    by_id = {r["page_id"]: r for r in reference["pages"]}
    if len(by_id) != len(reference["pages"]) or set(by_id) != set(page_set):
        raise ValueError("Reference must preserve every requested physical page and its enumeration status")
    complete = {k for k, r in by_id.items() if r["enumeration"] == "COMPLETE"}
    sampled = {(row.get("source_sha256"), row.get("physical_page")) for row in records}
    sampled_decisions = [r for r in decisions if (r["source_sha256"], r["physical_page"]) in sampled]
    summary = {"page_count": len(records), "pages_fully_annotated": len(complete),
               "reference_state_counts": dict(Counter(r["enumeration"] for r in by_id.values())),
               "unseen_technical_sources": any("TECHNICAL" in row.get("strata", []) for row in records),
               "candidate_inventory_rows_on_sampled_pages": len(sampled_decisions),
               "records_with_native_token_on_sampled_pages": {
                   arm.upper(): sum(((row.get(arm) or {}).get("native") or {}).get("token") not in (None, "")
                                    for row in sampled_decisions) for arm in ("e0", "e1")},
               "independent_validation_pending": True, "accuracy": None, "relations": None}
    if (reference["review_kind"] != "INDEPENDENT_HUMAN" or not reference["reviewer_id"]
            or reference["reviewed_without_predictions"] is not True or not reference["adjudication_reference"]
            or not complete):
        return summary
    gold, texts = {}, {}
    for key in sorted(complete):
        page, reviewed = page_set[key], by_id[key]
        with pymupdf.open(check_asset(assets, page["source_sha256"])) as pdf:
            texts[key] = clean(pdf[page["physical_page"] - 1].get_text(sort=True))
        for row in reviewed["observations"]:
            if (not set(REVIEW_FIELDS) <= row.keys() or row["verdict"] not in STATE
                    or row["project_id"] not in page["project_ids"] or row["verdict"] == "NOT_REVIEWED"):
                raise ValueError("Complete reference pages require an explicit observation verdict and source identity")
            if row["verdict"] == "CONFIRMED" and (not isinstance(row["context"], dict) or not row["context"]):
                raise ValueError("A complete observation reference must include its confirmed semantic context")
            position = located_token(texts[key], row["quote"], row["token"], row["token_occurrence_in_quote"])
            if position is None or (key, position) in gold:
                raise ValueError("Reference observations must resolve to unique native token occurrences")
            gold[key, position] = row
    packet = {(p["source_sha256"], p["physical_page"]): p for k, p in page_set.items() if k in complete}
    summary["accuracy"] = {arm: score_arm(decisions, packet, texts, arm, gold) for arm in ARMS}
    if reference["relation_review"] == "COMPLETE" and relations is not None:
        summary["relations"] = score_relations(reference["relations"], relations, packet, texts, gold)
    summary["independent_validation_pending"] = (len(complete) != len(records)
                                                   or summary["relations"] is None
                                                   or not summary["unseen_technical_sources"])
    return summary


def score_arm(decisions, packet, texts, arm, gold):
    predictions, unlocated = identify_predictions(decisions, packet, texts, arm)
    valid = {k: r for k, r in gold.items() if r["verdict"] == "CONFIRMED"}
    counts = Counter()
    for loc, group in predictions.items():
        target = gold.get(loc)
        accepted = any(r["disposition"] == "ACCEPT" for r in group)
        if target is None:
            counts["unreferenced_located_token"] += 1
            counts["unreferenced_accepted"] += accepted
            continue
        if target["verdict"] != "CONFIRMED":
            key = target["verdict"].lower()
            counts[key + ("_accepted" if accepted else "_withheld")] += 1
            continue
        counts["located_confirmed"] += 1
        numeric = [r for r in group if clean(r["native"]["token"]) == clean(target["token"])
                   and clean(r["native"]["unit"]) == clean(target["unit"])]
        counts["numeric_with_own_unit"] += bool(numeric)
        supported = [
            r for r in numeric if
            r["project_id"] == target["project_id"] and r["native"]["quantity"] == target["quantity"]
            and all(r["context"].get(k) == v for k, v in target["context"].items())]
        counts["complete_observation"] += bool(supported)
        if accepted:
            if any(r["disposition"] == "ACCEPT" for r in supported):
                counts["accepted_confirmed"] += 1
            else:
                counts["accepted_with_conflicting_attributes"] += 1
    counts["unlocated_candidates"] = len(unlocated)
    counts["unlocated_accepted"] = sum(r["disposition"] == "ACCEPT" for r in unlocated)
    counts["unextracted_confirmed"] = len(set(valid) - predictions.keys())
    determinate_locations = sum(k not in gold or gold[k]["verdict"] != "INSUFFICIENT" for k in predictions)
    return {"raw_counts": dict(counts), "confirmed_reference_observations": len(valid),
            "source_locator_recall": rate(counts["located_confirmed"], len(valid)),
            "source_locator_precision_on_located_determinate": rate(counts["located_confirmed"], determinate_locations),
            "numeric_with_own_unit_recall": rate(counts["numeric_with_own_unit"], len(valid)),
            "numeric_with_own_unit_precision_on_located_determinate": rate(counts["numeric_with_own_unit"],
                                                                           determinate_locations),
            "complete_observation_recall": rate(counts["complete_observation"], len(valid)),
            "complete_observation_precision_on_located_determinate": rate(counts["complete_observation"],
                                                                          determinate_locations),
            "acceptance_precision_among_located_determinate": rate(
                counts["accepted_confirmed"], counts["accepted_confirmed"] +
                counts["incompatible_accepted"] + counts["unreferenced_accepted"] +
                counts["accepted_with_conflicting_attributes"])}


def score_relations(reference, relations, packet, texts, gold):
    """Use native occurrences to align endpoints, independent of system candidate IDs."""
    true_relations, unsupported = {}, set()
    for row in reference:
        endpoints = []
        for side in row["sides"]:
            slot = (side["source_sha256"], side["physical_page"])
            page_id = packet[slot]["page_id"]
            position = located_token(texts[page_id], side["quote"], side["token"], side["token_occurrence_in_quote"])
            key = page_id, position
            if key not in gold:
                raise ValueError("Reviewed relationship endpoint does not identify a native observation")
            endpoints.append(key)
        if len(endpoints) != 2 or row["verdict"] not in STATE - {"NOT_REVIEWED"}:
            raise ValueError("A complete relationship reference requires two observed endpoints and a verdict")
        identity = tuple(sorted(endpoints))
        if row["verdict"] == "CONFIRMED":
            true_relations[identity] = row["relation"]
        else:
            unsupported.add(identity)
    proposed, unlocated = {}, 0
    for row in relations:
        positions = []
        for side in row["sides"]:
            slot = side["source_sha256"], side["physical_page"]
            if slot not in packet:
                break
            page = packet[slot]
            positions.append(measurement_location(side, page, texts[page["page_id"]]))
        if len(positions) != 2:
            continue
        if not all(positions):
            unlocated += 1
            continue
        key = tuple(sorted(positions))
        proposed.setdefault(key, set()).add((row["relation"], row["status"]))
    correct = sum(any(relation == expected for relation, _ in proposed.get(key, ()))
                  for key, expected in true_relations.items())
    confirmed = {(key, relation) for key, results in proposed.items()
                 for relation, status in results if status == "CONFIRMED"}
    matched = sum(true_relations.get(key) == relation for key, relation in confirmed)
    return {"confirmed_reference_pairs": len(true_relations), "unsupported_reference_pairs": len(unsupported),
            "unlocated_proposals": unlocated, "deduplicated_located_proposal_pairs": len(proposed),
            "typed_proposal_recall": rate(correct, len(true_relations)),
            "confirmed_relation_precision_on_located_pairs": rate(matched, len(confirmed))}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path)
    parser.add_argument("--release", default=RELEASE, type=Path)
    parser.add_argument("--baseline", default=BASE, type=Path)
    parser.add_argument("--output", default=OUTPUT, type=Path)
    parser.add_argument("--older-ontology-review", default=OLD_ONTOLOGY, type=Path)
    parser.add_argument("--reuse-exclusions-from", type=Path)
    parser.add_argument("--prepare-from", type=Path)
    parser.add_argument("--assets", type=Path)
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--packet", type=Path)
    parser.add_argument("--decisions", type=Path)
    parser.add_argument("--relationships", type=Path)
    args = parser.parse_args()
    if args.reference and args.packet and args.decisions and args.assets:
        related = json_rows(args.relationships) if args.relationships else None
        result = compare_reference(args.packet, json.loads(args.reference.read_bytes()),
                                   json_rows(args.decisions), args.assets, related)
        paths = [args.packet, args.reference, args.decisions, args.relationships]
        result["input_sha256"] = {path.name: filehash(path) for path in paths if path}
        args.output.mkdir(parents=True, exist_ok=True)
        report(args.output / "review_evaluation.json", result)
    elif args.prepare_from and args.assets:
        prepare_packet(args.prepare_from, args.assets, args.output, args.release)
    elif args.run:
        exclusions = (json.loads(args.reuse_exclusions_from.read_bytes())["historical_review_exclusions"]
                      if args.reuse_exclusions_from else history(args.older_ontology_review))
        freeze(args.output, args.release, args.run, args.baseline, exclusions)
    else:
        parser.error("Supply --run, --prepare-from with --assets, or reference, packet, decisions and assets")
