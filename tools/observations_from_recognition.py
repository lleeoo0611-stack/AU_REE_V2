"""Export typed raw review candidates from a frozen or read-only recognition report."""

import argparse
from datetime import date
import json
from pathlib import Path

from au_ree_v2.acquisition import select_snapshots
from au_ree_v2.derived_cache import DerivedCache
from au_ree_v2.nlp import automatic_observations, recognize_source
from au_ree_v2.observation_schema import payload
from au_ree_v2.pdf_extract import project_registry
from au_ree_v2.store import canonical


def _recognize(args):
    if not args.as_of:
        raise ValueError("Read-only source recognition requires --as-of")
    cutoff = date.fromisoformat(args.as_of).isoformat()
    sources = select_snapshots(args.root, cutoff, keys={args.source_key})
    sources = [source for source in sources if source["key"] == args.source_key and source["kind"] in {"pdf", "html"}]
    if len(sources) != 1:
        raise ValueError("The selected source must resolve to one eligible PDF or HTML snapshot")
    if args.receipt is not None and args.receipt.resolve() == args.out.resolve():
        raise ValueError("Choose separate output and receipt destinations")
    if args.cache_directory is not None:
        cache_path = args.cache_directory.resolve()
        protected = [args.root / name for name in ("data", "config", "results")]
        protected.extend(path for path in (args.out, args.receipt) if path is not None)
        if any(cache_path.is_relative_to(path.resolve()) or path.resolve().is_relative_to(cache_path)
               for path in protected):
            raise ValueError("Choose a cache directory separate from the research inputs and outputs")
    cache = DerivedCache(args.cache_directory, mode=args.cache_mode)
    report = recognize_source(args.root, sources[0], project_registry(args.root), cache=cache,
                              tessdata=args.tessdata, page_numbers=args.pages)
    if args.receipt is not None:
        with args.receipt.open("x", encoding="utf-8", newline="\n") as receipt:
            receipt.write(json.dumps(cache.receipt(), ensure_ascii=False, indent=2) + "\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--report", type=Path)
    source.add_argument("--source-key")
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--as-of")
    parser.add_argument("--pages", type=int, nargs="+")
    parser.add_argument("--tessdata", type=Path)
    parser.add_argument("--cache-directory", type=Path)
    parser.add_argument("--cache-mode", choices=("use", "off", "refresh"), default="use")
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = json.loads(args.report.read_bytes()) if args.report else _recognize(args)
    records = [payload(observation) for observation in automatic_observations(report)]
    with args.out.open("x", encoding="utf-8", newline="\n") as output:
        for observation in records:
            output.write(canonical(observation) + "\n")


if __name__ == "__main__":
    main()
