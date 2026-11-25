"""Prepare complementary blind PDF-page reviews and record actual human review time."""
import argparse
import hashlib
import json
import re
import secrets
import statistics
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


ARMS = ("rules", "rules_nlp")
SHA = re.compile(r"[0-9a-f]{64}")
TOKEN = re.compile(r"[0-9a-f]{16}")
INSTRUCTIONS = """# Independent evidence-page review

The coordinator gives each reviewer only their own packet and optional local page
images. Keep the allocation key, predictions, reference pages, and the other
reviewer's packet private until both independent reviews finish. Use a neutral
reviewer ID. A reviewer sees one condition per project and the opposite reviewer
sees the other. Queue length and document content can still suggest the condition.

The coordinator can render the assigned pages before the session:
    python -m tools.nlp_blind_review render --packet PACKET --assets KIT/assets --out work/local-pages

Start the session in a terminal:
    python -m tools.nlp_blind_review review --packet PACKET --reviewer YOUR_ID --session work/local-session --images work/local-pages

Review only the supplied pages, during the timed interval. For each project/field
case type start, read its pages, then type stop. Record each field as supported,
insufficient, or conflicting. For a supported field record the literal value,
the source page number(s) in your queue and a scope reason. Time from start to
stop measures active page checking, excluding rendering and verdict entry.
An empty queue can be inspected and marked insufficient after actual timing.
Use skip before starting, incomplete for interrupted work, and quit to end.
A restarted session skips prior records; an interrupted start remains incomplete
with unknown duration. Never infer unseen data, convert a candidate into a Census
value, or enter machine time as a human measurement.

The coordinator can summarize completed sessions:
    python -m tools.nlp_blind_review report --allocation ALLOCATION --session FIRST --session SECOND

Run prepare, render and session writes in local scratch storage. Within this
repository output must be inside work/. Preserve individual journals privately.
The report counts each case once. It reports incomplete groups and leaves a
group's total time unmeasured until every assigned case in that group finishes.
"""


def load(path):
    return json.loads(Path(path).read_bytes())


def write_new(path, data):
    with path.open("x", encoding="utf-8", newline="\n") as output:
        output.write(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def key(*values):
    payload = json.dumps(values, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def scratch(path):
    """Resolve symlinks and allow repository writes only inside local work storage."""
    folder = Path(path).resolve()
    for parent in (folder, *folder.parents):
        if parent.name.casefold() == ".git":
            raise ValueError("Git metadata is not an output location")
        if (parent / ".git").exists():
            if not folder.is_relative_to(parent / "work") or folder == parent / "work":
                raise ValueError("Use a local output directory under work/ or outside Git")
            break
    return folder


def page_pairs(items):
    result = []
    for item in items:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            raise ValueError("Expected a document checksum and physical page number")
        sha, n = item
        if not isinstance(sha, str) or not SHA.fullmatch(sha) or type(n) is not int or n < 1:
            raise ValueError("Invalid physical page reference")
        result.append((sha, n))
    if len(set(result)) != len(result):
        raise ValueError("Duplicate page within a review queue")
    return result


def prepare(predictions, out, seed=None):
    if seed is None:
        seed = secrets.token_hex(32)
    if not seed:
        raise ValueError("A fixed assignment seed is required")
    groups = {}
    ids = set()
    for row in predictions["cases"]:
        project, field, case = (row[k] for k in ("project_id", "field", "case_id"))
        if not all(isinstance(s, str) and s.strip() for s in (project, field, case, row["project_name"])):
            raise ValueError("Incomplete case identity")
        if case in ids:
            raise ValueError("Duplicate case ID")
        ids.add(case)
        columns = row["columns"]
        if not isinstance(columns, list) or not columns or not all(isinstance(c, str) and c.strip() for c in columns):
            raise ValueError("Expected explicit Census columns")
        queues = {arm: page_pairs(row[arm]) for arm in ARMS}
        unit = groups.setdefault((project, field), dict(name=row["project_name"], columns=set(), cases=[], queues=queues))
        if unit["queues"] != queues or unit["name"] != row["project_name"]:
            raise ValueError("Copies of one project/field must have the same blinded retrieval unit")
        unit["columns"].update(columns)
        unit["cases"].append(case)
    if not groups:
        raise ValueError("No cases to assign")
    # Greedy size-balanced complementary crossover. Keep projects intact, including
    # those with multiple requested fields. The fixed hash resolves assignment ties.
    sizes = Counter(pid for pid, field in groups)
    loads = [0, 0]
    side = {}
    for pid in sorted(sizes, key=lambda pid: (-sizes[pid], key(seed, "assignment", pid))):
        choice = min(range(2), key=lambda i: (loads[i], key(seed, "tie", pid, i)))
        side[pid] = choice
        loads[choice] += sizes[pid]
    allocations, packets = [], []
    for reviewer in (0, 1):
        packet = {"packet_id": key(seed, "packet", reviewer, sorted(ids))[:16], "cases": []}
        for pid, field in sorted(groups, key=lambda unit: (key(seed, reviewer, unit[0]), unit[1])):
            unit = groups[pid, field]
            arm = ARMS[side[pid] ^ reviewer]
            token = key(seed, "case", reviewer, pid, field)[:16]
            packet["cases"].append(dict(id=token, project=unit["name"], field=field,
                                        columns=sorted(unit["columns"]), pages=unit["queues"][arm]))
            allocations.append(dict(packet_id=packet["packet_id"], id=token, project_id=pid,
                                    field=field, arm=arm, input_cases=sorted(unit["cases"])))
        packets.append(packet)
    base = scratch(out)
    base.mkdir(parents=True, exist_ok=False)
    (base / "coordinator").mkdir()
    for i, packet in enumerate(packets, 1):
        folder = base / f"reviewer-{i}"
        folder.mkdir()
        write_new(folder / "packet.json", packet)
    write_new(base / "coordinator/allocation.json", dict(seed=seed, predictions_sha256=key(predictions), assignments=allocations,
              packets={p["packet_id"]: key(p) for p in packets}))
    (base / "REVIEW.md").write_text(INSTRUCTIONS, encoding="utf-8")
    return base


def validated_packet(packet):
    if not TOKEN.fullmatch(packet["packet_id"]) or not packet["cases"]:
        raise ValueError("Invalid review packet")
    ids = set()
    for row in packet["cases"]:
        token = row["id"]
        if not TOKEN.fullmatch(token) or token in ids:
            raise ValueError("Invalid or repeated anonymous case ID")
        ids.add(token)
        page_pairs(row["pages"])
    return packet


def render(packet, assets, out):
    import pymupdf

    validated_packet(packet)
    target = scratch(out)
    target.mkdir(parents=True, exist_ok=False)
    write_new(target / "packet.json", {"packet_sha256": key(packet)})
    needed = defaultdict(list)
    for case in packet["cases"]:
        folder = target / case["id"]
        folder.mkdir()
        for index, (sha, number) in enumerate(case["pages"], 1):
            needed[sha].append((number, folder / f"page-{index:02}.png"))
    for sha, destinations in needed.items():
        path = Path(assets) / sha
        if not path.is_file():
            path = path.with_suffix(".pdf")
        data = path.read_bytes()
        if not data.startswith(b"%PDF-") or hashlib.sha256(data).hexdigest() != sha:
            raise ValueError(f"Original PDF checksum mismatch: {sha}")
        with pymupdf.open(stream=data, filetype="pdf") as doc:
            for number, destination in destinations:
                if not 1 <= number <= len(doc):
                    raise ValueError(f"Physical page outside original: {sha} p{number}")
                doc[number-1].get_pixmap(dpi=150, alpha=False).save(destination)
    write_new(target / "ready.json", {"packet_sha256": key(packet)})


def now():
    return datetime.now(timezone.utc).isoformat()


def session_start(packet, reviewer, path):
    if not reviewer.strip():
        raise ValueError("A neutral human reviewer ID is required")
    folder = scratch(path)
    folder.mkdir(parents=True, exist_ok=True)
    meta = {"packet_id": packet["packet_id"], "packet_sha256": key(packet), "reviewer": reviewer}
    header = folder / "session.json"
    if header.exists():
        if load(header) != meta:
            raise ValueError("This session already belongs to a different reviewer or packet")
    elif any(folder.iterdir()):
        raise ValueError("Existing directory is not a review session")
    else:
        write_new(header, meta)
    return folder


def ask(prompt, choices, reader=input):
    while True:
        answer = reader(prompt).strip().casefold()
        if answer in choices:
            return answer


def field_verdicts(case, reader=input):
    verdicts = []
    for column in case["columns"]:
        available = ("supported", "insufficient", "conflicting") if case["pages"] else ("insufficient",)
        state = ask(f"{column} ({', '.join(available)}): ", available, reader)
        verdict = dict(column=column, decision=state)
        if state == "supported":
            while not verdict.get("value"):
                verdict["value"] = reader("Literal or source-supported value: ").strip()
            while not verdict.get("pages"):
                raw = reader("Queue page positions, separated by spaces: ").split()
                if raw and all(v.isdecimal() and 1 <= int(v) <= len(case["pages"]) for v in raw):
                    verdict["pages"] = [case["pages"][i-1] for i in sorted({int(v) for v in raw})]
        while not verdict.get("reason"):
            verdict["reason"] = reader("Reason / scope: ").strip()
        verdicts.append(verdict)
    return verdicts


def run_review(packet, reviewer, path, images=None, *, reader=input, timer=time.monotonic_ns):
    validated_packet(packet)
    if images is not None and load(Path(images) / "ready.json") != {"packet_sha256": key(packet)}:
        raise ValueError("Rendered pages are incomplete or belong to another packet")
    if ask("Type human to confirm your independent, unassisted timing, or quit: ", ("human", "quit"), reader) == "quit":
        return
    folder = session_start(packet, reviewer, path)
    for case in packet["cases"]:
        token = case["id"]
        started, result = folder / (token + ".started.json"), folder / (token + ".result.json")
        if result.exists() or started.exists():
            continue
        print(f"Case {token}")
        try:
            action = ask("start / skip / quit: ", ("start", "skip", "quit"), reader)
        except (EOFError, KeyboardInterrupt):
            return
        if action == "quit":
            return
        # Exclusive creation also prevents two terminals recording the same case.
        try:
            write_new(started, dict(action=action, at=now()))
        except FileExistsError:
            continue
        if action == "skip":
            write_new(result, dict(status="skipped", seconds=None))
            continue
        begin = timer()
        print(case["project"], case["field"], case["columns"])
        for i, (sha, page) in enumerate(case["pages"], 1):
            print(i, sha, "physical page", page, str(Path(images) / token / f"page-{i:02}.png") if images else "")
        if not case["pages"]:
            print("The assigned queue contains no pages.")
        try:
            action = ask("Read now, then type stop, or incomplete: ", ("stop", "incomplete"), reader)
            elapsed = (timer()-begin) / 1_000_000_000
            if action == "incomplete":
                write_new(result, dict(status="incomplete", seconds=None, partial_seconds=elapsed))
                return
            verdicts = field_verdicts(case, reader)
            write_new(result, dict(status="completed", seconds=elapsed, verdicts=verdicts, at=now()))
        except (EOFError, KeyboardInterrupt):
            write_new(result, dict(status="incomplete", seconds=None))
            return


def report(allocation, sessions):
    """Count each expected case once. Partial data cannot produce full-arm times."""
    headers = {}
    people = set()
    for folder in map(Path, sessions):
        header = load(folder / "session.json")
        packet = header["packet_id"]
        if (header["packet_sha256"] != allocation["packets"].get(packet) or packet in headers
                or header["reviewer"] in people):
            raise ValueError("Session is mismatched, duplicated, or shares a reviewer with the other arm")
        headers[packet] = folder
        people.add(header["reviewer"])
    counts = {arm: Counter() for arm in ARMS}
    times = {arm: [] for arm in ARMS}
    paired = defaultdict(dict)
    for row in allocation["assignments"]:
        arm, token, packet = row["arm"], row["id"], row["packet_id"]
        if not TOKEN.fullmatch(token):
            raise ValueError("Invalid case ID in allocation")
        counts[arm]["assigned"] += 1
        where = headers.get(packet)
        result = where / (token + ".result.json") if where else None
        if result and result.exists():
            state = load(result)
            if state["status"] not in {"completed", "skipped", "incomplete"}:
                raise ValueError("Unknown review status")
            status = state["status"]
            if status == "completed":
                duration = state["seconds"]
                if type(duration) not in (int, float) or not 0 < duration < float("inf") or not state["verdicts"]:
                    raise ValueError("Invalid completed review")
                times[arm].append(duration)
                paired[row["project_id"], row["field"]][arm] = duration
        elif where and (where / (token + ".started.json")).exists():
            status = "incomplete"
        else:
            status = "unmeasured"
        counts[arm][status] += 1
    summary = {}
    for arm in ARMS:
        counts_for_arm = counts[arm]
        elapsed = times[arm]
        summary[arm] = dict(assigned_cases=counts_for_arm["assigned"], completed_cases=len(elapsed),
                            skipped_cases=counts_for_arm["skipped"], incomplete_cases=counts_for_arm["incomplete"],
                            unmeasured_cases=counts_for_arm["unmeasured"],
                            completed_seconds=sum(elapsed) if elapsed else None,
                            median_completed_seconds=statistics.median(elapsed) if elapsed else None,
                            full_arm_seconds=sum(elapsed) if elapsed and len(elapsed)==counts_for_arm["assigned"] else None)
    pairs = [r for r in paired.values() if set(r) == set(ARMS)]
    return dict(arms=summary, independent_reviewers=len(people), completed_matched_cases=len(pairs),
                mean_paired_seconds_change=(statistics.mean(r["rules_nlp"]-r["rules"] for r in pairs) if pairs else None))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="mode", required=True)
    pack = commands.add_parser("prepare")
    pack.add_argument("--predictions", type=Path, required=True)
    pack.add_argument("--out", type=Path, required=True)
    pack.add_argument("--seed", help="Optional private reproducibility seed; defaults to cryptographic randomness")
    pictures = commands.add_parser("render")
    pictures.add_argument("--packet", type=Path, required=True)
    pictures.add_argument("--assets", type=Path, required=True)
    pictures.add_argument("--out", type=Path, required=True)
    review = commands.add_parser("review")
    review.add_argument("--packet", type=Path, required=True)
    review.add_argument("--reviewer", required=True)
    review.add_argument("--session", type=Path, required=True)
    review.add_argument("--images", type=Path)
    audit = commands.add_parser("report")
    audit.add_argument("--allocation", type=Path, required=True)
    audit.add_argument("--session", type=Path, action="append", default=[])
    args = parser.parse_args()
    if args.mode == "prepare":
        print(prepare(load(args.predictions), args.out, args.seed))
    elif args.mode == "render":
        render(load(args.packet), args.assets, args.out)
    elif args.mode == "review":
        if not sys.stdin.isatty():
            parser.error("Real human review requires an interactive terminal")
        run_review(load(args.packet), args.reviewer, args.session, args.images)
    else:
        print(json.dumps(report(load(args.allocation), args.session), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
