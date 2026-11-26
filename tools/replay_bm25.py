"""Replay the frozen Census evidence-page queries using the shared document and BM25 code."""

import argparse
import json
from pathlib import Path
import re
from time import perf_counter

from au_ree_v2.derived_cache import DerivedCache
from au_ree_v2.document_processing import PdfDocumentCache
from au_ree_v2.nlp import PageIndex
from au_ree_v2.store import digest, filehash


def project_alias(name):
    """Remove the historical Census scope note and standard activity suffix."""
    return re.split(r"\s+[—–]|\s+(?:Li[–-]REE|REE[–-]|REE\b|Rare Earth|Critical Mineral|"
                    r"Project\b|Mineral Sands)", name, maxsplit=1, flags=re.I)[0].strip()


def replay(historical, assets, output, *, allow_incomplete=False, cache=None):
    historical, assets, output = map(Path, (historical, assets, output))
    if any(output.resolve().is_relative_to(path.resolve()) for path in (historical, assets)):
        raise ValueError("Choose a separate experiment output directory")
    start = perf_counter()
    split_path, queries_path = (historical / name for name in ("split.json", "predictions.json"))
    split, predictions = (json.loads(path.read_bytes()) for path in (split_path, queries_path))
    frame = [doc for doc in split["documents"] if doc["split"] == "holdout"]
    if not frame or len(frame) != len({doc["sha256"] for doc in frame}):
        raise ValueError("Historical holdout documents must have distinct source fingerprints")
    expected_pages = {source["sha256"]: source["pages"] for source in frame}
    unsupported = {}
    with PdfDocumentCache(assets, max_documents=1, cache=cache) as documents:
        index = PageIndex.from_documents(
            documents, expected_pages, expected_pages=expected_pages,
            missing=unsupported if allow_incomplete else None,
        )
        document_counts = dict(documents.counts)
    missing = [{"sha256": source["sha256"], "reason": unsupported[source["sha256"]]}
               for source in frame if source["sha256"] in unsupported]
    included = [source for source in frame if source["sha256"] not in unsupported]
    if not index.page_keys:
        raise ValueError("No verified historical holdout pages")

    cases = []
    matches = 0
    for case in predictions["cases"]:
        ranks = index.rank_pair(project_alias(case["project_name"]), case["field"], case["rules"], k=predictions["k"])
        matches += ranks["rules_nlp"] == [tuple(pair) for pair in case["rules_nlp"]]
        cases.append({**case, **ranks})
    if not missing and matches != len(cases):
        raise ValueError("Full-frame BM25 replay differs from the frozen rankings")
    output.mkdir(parents=True, exist_ok=False)
    reduced_split = {**split, "documents": included}
    reranked = {"k": predictions["k"], "cases": cases}
    receipt = {
        "status": "REDUCED_DOCUMENT_POOL" if missing else "EXACT_HOLDOUT_RANKINGS_REPRODUCED",
        "expected_holdout_documents": len(frame),
        "verified_holdout_documents": len(included),
        "physical_pages": len(index.page_keys),
        "searchable_pages": len(index.documents),
        "missing_documents": missing,
        "identical_historical_queues": matches,
        "queries": len(cases),
        "rules_page_slots": sum(len(case["rules"]) for case in cases),
        "bm25_page_slots": sum(len(case["rules_nlp"]) for case in cases),
        "input_sha256": {path.name: filehash(path) for path in (split_path, queries_path)},
        "rankings_sha256": digest(reranked),
        "document_processing": document_counts,
        "elapsed_seconds": perf_counter() - start,
    }
    for filename, value in (("split.json", reduced_split), ("predictions.json", reranked), ("replay.json", receipt)):
        (output / filename).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if cache is not None:
        (output / "cache_receipt.json").write_text(
            json.dumps(cache.receipt(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
        )
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ("historical", "assets", "out"):
        parser.add_argument(f"--{option}", type=Path, required=True)
    parser.add_argument("--allow-incomplete", action="store_true")
    parser.add_argument("--cache-directory", type=Path)
    parser.add_argument("--cache-mode", choices=("use", "off", "refresh"), default="use")
    args = parser.parse_args()
    if args.cache_directory is not None:
        cache_path = args.cache_directory.resolve()
        protected = [path.resolve() for path in (args.historical, args.assets, args.out)]
        if any(cache_path.is_relative_to(path) or path.is_relative_to(cache_path) for path in protected):
            parser.error("Choose a cache separate from historical inputs, source assets and output")
    if args.cache_directory is None and args.cache_mode == "refresh":
        parser.error("Refresh requires --cache-directory")
    cache = DerivedCache(args.cache_directory, mode=args.cache_mode) if args.cache_directory is not None else None
    replay(args.historical, args.assets, args.out, allow_incomplete=args.allow_incomplete, cache=cache)


if __name__ == "__main__":
    main()
