"""Rebuildable, content-addressed products for the shadow processing stages."""

from collections import Counter, defaultdict
from contextlib import contextmanager
from datetime import datetime, timezone
import inspect
import json
import os
from pathlib import Path
import platform
import tempfile
from time import perf_counter, sleep
from uuid import uuid4

from .store import canonical, digest, filehash


FORMAT = "au-ree-derived-product-v1"
DEPENDENCIES = {
    "pdf": (),
    "ocr": ("pdf",),
    "recognition": ("pdf", "ocr"),
    "extraction": ("pdf", "ocr", "recognition"),
    "bm25-index": ("pdf",),
    "bm25-query": ("bm25-index",),
    "projection": ("extraction", "recognition"),
    "normalization": ("projection",),
    "assessment": ("projection", "normalization"),
}


def code_fingerprint(*objects, files=()):
    """Hash selected definitions and explicit transitive files without checkout paths."""
    return digest({
        "definitions": [inspect.getsource(obj) for obj in objects],
        "files": [filehash(path) for path in files],
    })


def downstream(stages):
    forced = set(stages)
    if unknown := forced - DEPENDENCIES.keys():
        raise ValueError("Unknown cache stage: " + ", ".join(sorted(unknown)))
    for stage, parents in DEPENDENCIES.items():
        if forced.intersection(parents):
            forced.add(stage)
    return sorted(forced)


@contextmanager
def exclusive_lock(path):
    """An advisory writer lock is released if its process is interrupted."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as stream:
        if os.name == "nt":
            import msvcrt

            stream.seek(0)
            if not stream.read(1):
                stream.write(b"0")
                stream.flush()
            stream.seek(0)
            deadline = perf_counter() + 330
            while True:
                try:
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    if perf_counter() >= deadline:
                        raise
                    sleep(0.1)
        else:
            import fcntl

            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        yield


def atomic_json(path, data):
    """A completed product becomes visible as a single directory entry."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix="." + path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(canonical(data) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def _read(path):
    return json.loads(path.read_bytes())


class DerivedCache:
    """Keep cache writes and diagnostics separate from canonical source history."""

    def __init__(self, directory=None, *, mode="use", force=()):
        if mode not in {"use", "off", "refresh"}:
            raise ValueError("Unknown cache mode")
        if directory is None and (mode == "refresh" or force):
            raise ValueError("A cache directory is required to refresh or force stages")
        if mode == "off" and force:
            raise ValueError("Forced stages require an enabled cache")
        self.directory = Path(directory).resolve() if directory is not None else None
        self.mode = mode if directory is not None else "off"
        self.requested_force = sorted(set(force))
        self.force = frozenset(downstream(force))
        self.events = []
        self.environment = {"python": platform.python_version(), "implementation": platform.python_implementation(),
                            "platform": platform.system(), "machine": platform.machine()}

    @staticmethod
    def _describe(stage, subject, inputs, upstream):
        if stage not in DEPENDENCIES:
            raise ValueError(f"Unknown cache stage {stage}")
        return {
            "format": FORMAT, "stage": stage, "subject": subject,
            "input_sha256": {name: digest(value) for name, value in inputs.items()},
            "upstream_sha256": dict(upstream or {}),
        }

    @staticmethod
    def _load(path, spec, validate):
        artifact = _read(path)
        if (not isinstance(artifact, dict) or artifact.get("contract") != spec
                or artifact.get("state") != "SUCCESS" or "value" not in artifact
                or artifact.get("output_sha256") != digest(artifact["value"])):
            raise ValueError("Product format, input contract or checksum mismatch")
        if validate is not None:
            validate(artifact["value"])
        return artifact

    def record(self, stage, subject, state, **details):
        """Record source and scientific dispositions independently of I/O failures."""
        self.events.append({"stage": stage, "subject": subject, "state": state, **details})

    def compute(self, stage, subject, inputs, build, *, upstream=None, validate=None):
        spec = self._describe(stage, subject, inputs, upstream)
        key = digest(spec)
        started = perf_counter()
        event = {**spec, "key": key}
        event_index = len(self.events)
        try:
            if self.mode == "off":
                value = json.loads(canonical(build()))
                if validate is not None:
                    validate(value)
                event.update(state="COMPUTED", reason="CACHE_DISABLED", output_sha256=digest(value))
                return value
            return self._cached(key, spec, event, build, validate)
        except Exception as exc:
            event.update(state="FAILED", error=type(exc).__name__, detail=str(exc))
            raise
        finally:
            duration = perf_counter() - started
            nested = sum(child.get("seconds", 0) for child in self.events[event_index:])
            event["seconds"] = round(max(0, duration - nested), 6)
            event["inclusive_seconds"] = round(duration, 6)
            self.events.append(event)

    def _cached(self, key, spec, event, build, validate):
        stage = spec["stage"]
        folder = self.directory / "products" / stage / key[:2]
        product = folder / (key + ".json")
        slot_key = digest(spec["subject"])
        slot = self.directory / "lineage" / stage / slot_key[:2] / (slot_key + ".json")
        try:
            previous = _read(slot)
        except (FileNotFoundError, ValueError, OSError):
            previous = {}
        if not isinstance(previous, dict):
            previous = {}
        for field in ("input_sha256", "upstream_sha256"):
            old = previous.get(field, {})
            if isinstance(old, dict):
                changed = sorted(name for name in old.keys() | spec[field].keys()
                                 if old.get(name) != spec[field].get(name))
                if changed and previous:
                    event["changed_" + field] = changed

        forced = self.mode == "refresh" or stage in self.force
        # Completed entries are immutable. Read hits without writer locks.
        if not forced:
            try:
                cached = self._load(product, spec, validate)
            except (OSError, ValueError, TypeError, KeyError):
                pass
            else:
                self._hit(event, cached, slot, spec, key, previous)
                return cached["value"]

        with exclusive_lock(folder / (key + ".lock")):
            existing = None
            reason = "DEPENDENCIES_CHANGED" if previous and previous.get("key") != key else "NO_PRODUCT"
            try:
                existing = self._load(product, spec, validate)
            except FileNotFoundError:
                pass
            except (ValueError, TypeError, KeyError) as exc:
                reason = "PRODUCT_INVALID"
                quarantine = self.directory / "quarantine"
                quarantine.mkdir(parents=True, exist_ok=True)
                os.replace(product, quarantine / (key + "-" + uuid4().hex + ".json"))
                event["invalid_reason"] = str(exc)
            if existing is not None and not forced:
                self._hit(event, existing, slot, spec, key, previous)
                return existing["value"]
            if forced and reason != "PRODUCT_INVALID":
                reason = "FORCED_REFRESH"
            event["reason"] = reason
            # Roundtrip the newly built object too so cold and warm consumers see the same format.
            value = json.loads(canonical(build()))
            if validate is not None:
                validate(value)
            output_sha = digest(value)
            if existing is not None and output_sha != existing["output_sha256"]:
                raise ValueError(f"Nondeterministic product for unchanged {stage} dependencies")
            if existing is None:
                atomic_json(product, {"contract": spec, "state": "SUCCESS", "value": value,
                                      "output_sha256": output_sha, "environment": self.environment,
                                      "created_at": datetime.now(timezone.utc).isoformat(), "producer": "COMPUTED"})
            if previous.get("key") != key:
                atomic_json(slot, {**spec, "key": key, "output_sha256": output_sha})
            event.update(state="COMPUTED", output_sha256=output_sha)
            return value

    @staticmethod
    def _hit(event, artifact, slot, spec, key, previous):
        event.update(state="HIT", reason="CHECKSUM_VERIFIED", output_sha256=artifact["output_sha256"])
        if previous.get("key") != key:
            atomic_json(slot, {**spec, "key": key, "output_sha256": artifact["output_sha256"]})

    def receipt(self):
        counts = defaultdict(Counter)
        elapsed = Counter()
        for event in self.events:
            stage = event["stage"]
            counts[stage][event["state"]] += 1
            elapsed[stage] += event.get("seconds", 0)
        return {"format": FORMAT, "mode": self.mode, "forced_stages": sorted(self.force),
                "environment": self.environment, "dependency_graph": DEPENDENCIES,
                "counts": {stage: dict(total) for stage, total in counts.items()},
                "stage_seconds": {stage: round(value, 6) for stage, value in elapsed.items()},
                "events": self.events}


def read_receipt(path, *, events=False):
    receipt = _read(Path(path))
    if receipt.get("format") != FORMAT:
        raise ValueError("Unsupported cache receipt")
    if events:
        return receipt
    reasons = Counter((event["stage"], event["state"], event.get("reason"))
                      for event in receipt["events"])
    return {**{name: value for name, value in receipt.items() if name != "events"},
            "reasons": [{"stage": stage, "state": state, "reason": reason, "count": count}
                        for (stage, state, reason), count in reasons.items()]}
