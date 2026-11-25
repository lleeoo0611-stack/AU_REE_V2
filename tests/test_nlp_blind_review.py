"""Blind assignment and timers on synthetic packets only."""
from contextlib import redirect_stdout
import hashlib
import io
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import pymupdf

from tools.nlp_blind_review import load, prepare, render, report, run_review, scratch


def case(pid, category, columns, ident):
    return dict(case_id=ident, project_id=pid, project_name="Example " + pid, field=category, columns=columns,
                rules=[], rules_nlp=[["a"*64, 1]])


class BlindReviewTests(unittest.TestCase):
    def test_project_balance_case_grouping_separate_key_and_missing_time(self):
        with TemporaryDirectory() as directory:
            base = Path(directory)
            rows = [case("p0", "coordinate", ["longitude"], "first"),
                    case("p0", "coordinate", ["latitude"], "same"),
                    case("p0", "stage", ["stage"], "another"),
                    case("p1", "deposit", ["deposit"], "last")]
            folder = prepare({"cases": rows}, base/"pack", "private-seed")
            allocation = load(folder/"coordinator/allocation.json")
            self.assertEqual(len(allocation["assignments"]), 6)
            packets = [load(folder/f"reviewer-{i}/packet.json") for i in (1, 2)]
            for packet in packets:
                self.assertTrue(all(set(x) == {"id", "project", "field", "columns", "pages"} for x in packet["cases"]))
                self.assertEqual(len(set(x["id"] for x in packet["cases"])), 3)
                geo = next(x for x in packet["cases"] if x["field"] == "coordinate")
                self.assertEqual(geo["columns"], ["latitude", "longitude"])
            mapping = {}
            for r in allocation["assignments"]:
                mapping.setdefault((r["packet_id"], r["project_id"]), set()).add(r["arm"])
            self.assertTrue(all(len(v) == 1 for v in mapping.values()))
            for pid in ("p0","p1"):
                self.assertNotEqual(mapping[packets[0]["packet_id"],pid], mapping[packets[1]["packet_id"],pid])
            summary = report(allocation, [])
            self.assertEqual(summary["completed_matched_cases"], 0)
            self.assertIsNone(summary["mean_paired_seconds_change"])
            self.assertTrue(all(a["full_arm_seconds"] is None and a["completed_seconds"] is None
                                for a in summary["arms"].values()))
            with self.assertRaises(FileExistsError):
                prepare({"cases": rows}, folder, "seed")

    def test_timed_complete_skip_abort_and_resume_without_double_count(self):
        with TemporaryDirectory() as directory, redirect_stdout(io.StringIO()):
            base = Path(directory)
            rows = [case(str(i), "deposit", ["code"], str(i)) for i in range(3)]
            folder = prepare({"cases": rows}, base/"pack", "s")
            packet = load(folder/"reviewer-1/packet.json")
            allocation = load(folder/"coordinator/allocation.json")
            session = base/"session"
            answers = iter(["human", "start", "stop", "insufficient", "out of scope",
                            "skip", "start", "incomplete"])
            ticks = iter([10_000_000_000,15_000_000_000,20_000_000_000,22_000_000_000])
            run_review(packet,"r1",session,reader=lambda _:next(answers),timer=lambda:next(ticks))
            self.assertEqual(load(session/(packet["cases"][0]["id"]+".result.json"))["seconds"],5)
            run_review(packet, "r1", session, reader=lambda _:"human")
            summarized = report(allocation, [session])
            self.assertEqual(sum(a["completed_cases"] for a in summarized["arms"].values()),1)
            self.assertEqual(sum(a["skipped_cases"] for a in summarized["arms"].values()),1)
            self.assertEqual(sum(a["incomplete_cases"] for a in summarized["arms"].values()),1)
            self.assertTrue(all(a["full_arm_seconds"] is None for a in summarized["arms"].values()))
            with self.assertRaisesRegex(ValueError,"duplicated"):
                report(allocation, [session,session])

    def test_matching_requires_both_independent_reviewers(self):
        with TemporaryDirectory() as directory, redirect_stdout(io.StringIO()):
            base = Path(directory)
            output = prepare({"cases": [case("one", "stage", ["code"], "q")]}, base/"pack", "s")
            allocation = load(output/"coordinator/allocation.json")
            paths = []
            for i in (1, 2):
                packet = load(output/f"reviewer-{i}/packet.json")
                arm = next(row["arm"] for row in allocation["assignments"] if row["packet_id"] == packet["packet_id"])
                seconds = 6 if arm == "rules_nlp" else 10
                ticks = iter([2_000_000_000, (seconds+2)*1_000_000_000])
                answers = iter(["human", "start", "stop", "insufficient", "Missing exact support"])
                session = base / f"session-{i}"
                run_review(packet, f"auditor-{i}", session, reader=lambda _:next(answers), timer=lambda:next(ticks))
                paths.append(session)
            actual = report(allocation, paths)
            self.assertEqual(actual["completed_matched_cases"], 1)
            self.assertEqual(actual["mean_paired_seconds_change"], -4)
            self.assertEqual(actual["arms"]["rules_nlp"]["full_arm_seconds"], 6)
            same_person = base/"duplicate"
            inputs = iter(["human", "quit"])
            run_review(packet, "auditor-1", same_person, reader=lambda _:next(inputs))
            with self.assertRaisesRegex(ValueError, "shares a reviewer"):
                report(allocation, [paths[0], same_person])

    def test_render_hash_page_and_scratch_protection(self):
        with TemporaryDirectory() as directory:
            base=Path(directory)
            assets=base/"assets"
            assets.mkdir()
            with pymupdf.open() as doc:
                doc.new_page().insert_text((30,50),"Synthetic evidence.")
                data=doc.tobytes()
            sha=hashlib.sha256(data).hexdigest()
            (assets/sha).write_bytes(data)
            row=case("1","stage",["stage"],"1")
            row["rules"]=row["rules_nlp"]=[[sha,1]]
            output=prepare({"cases":[row]},base/"pack","S")
            packet=load(output/"reviewer-1/packet.json")
            render(packet,assets,base/"images")
            self.assertTrue((base/"images"/packet["cases"][0]["id"]/"page-01.png").is_file())
            with self.assertRaises(FileExistsError):render(packet,assets,base/"images")
            (assets/sha).write_bytes(b"Not original")
            with self.assertRaisesRegex(ValueError,"checksum"):render(packet,assets,base/"bad")
            self.assertFalse((base/"bad/ready.json").exists())
            repo=base/"repo"
            (repo/".git").mkdir(parents=True)
            with self.assertRaises(ValueError):scratch(repo/"results/replace")
            with self.assertRaises(ValueError):scratch(repo/".git"/"objects")
            self.assertEqual(scratch(repo/"work/local"),repo/"work/local")
