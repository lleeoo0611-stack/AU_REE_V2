"""Verify a frozen source review against original PDFs, separately from either experiment arm."""
import argparse
import hashlib
import json
import re
import unicodedata
from pathlib import Path

import pymupdf


VERDICTS = {"SUPPORTED", "INCOMPATIBLE", "INSUFFICIENT", "NOT_REVIEWED"}
ACCESS = {"VERIFIED", "NO_ORIGINAL", "NO_PHYSICAL_LOCATOR", "NOT_REVIEWED"}


def read_rows(path):
    with path.open(encoding="utf-8-sig") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def tokens(text):
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def keyed(rows):
    result = {}
    for row in rows:
        identifier = row["candidate_id"]
        if not identifier or identifier in result:
            raise ValueError(f"Empty or repeated candidate identifier {identifier!r}")
        result[identifier] = row
    return result


def verify(sample, labels, assets):
    sample_rows, review_rows = keyed(read_rows(sample)), keyed(read_rows(labels))
    if sample_rows.keys() != review_rows.keys():
        raise ValueError("The reference must cover exactly the frozen review packet")
    pages, verified = {}, set()
    for cid, annotation in review_rows.items():
        candidate = sample_rows[cid]
        source, verdict, access = (annotation[k] for k in ("source_sha256", "verdict", "source_access"))
        if source != candidate["source_sha256"] or verdict not in VERDICTS or access not in ACCESS:
            raise ValueError(f"Invalid source or reference label for {cid}")
        if not annotation["reason"].strip():
            raise ValueError(f"Missing source rationale for {cid}")
        anchors = annotation["anchors"]
        if access != "VERIFIED":
            if anchors or verdict in {"SUPPORTED", "INCOMPATIBLE"}:
                raise ValueError(f"Unavailable original cannot substantiate a verdict for {cid}")
            continue
        if not anchors or not re.fullmatch(r"[a-f0-9]{64}", source):
            raise ValueError(f"Missing PDF identity or anchors for {cid}")
        path = assets / source
        if source not in verified:
            with path.open("rb") as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() != source:
                    raise ValueError(f"Original checksum mismatch for {cid}")
            verified.add(source)
        for anchor in anchors:
            number = anchor["page"]
            key = (source, number)
            if key not in pages:
                with pymupdf.open(path) as doc:
                    if not isinstance(number, int) or not 1 <= number <= len(doc):
                        raise ValueError(f"Invalid physical PDF page for {cid}: {number}")
                    page = doc[number - 1]
                    pages[key] = [tokens(page.get_text(sort=sort)) for sort in (False, True)]
            quote = tokens(anchor["text"])
            if not quote or not any(quote in text for text in pages[key]):
                raise ValueError(f"Source anchor mismatch for {cid}, physical page {number}: {anchor['text']!r}")
    return {"packet_candidates": len(sample_rows), "originals_verified": len(verified),
            "physical_pages_verified": len(pages),
            "verdicts": {v: sum(r["verdict"] == v for r in review_rows.values()) for v in sorted(VERDICTS)}}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample", required=True, type=Path)
    parser.add_argument("--labels", required=True, type=Path)
    parser.add_argument("--assets", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(verify(args.sample, args.labels, args.assets), sort_keys=True))
