"""Tests for applying decisions in one step (claimguard.ui.apply, M9): the
same result as the three separate commands."""
import contextlib
import io
import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from claimguard._pack import load_jsonl
from claimguard.audit import chain
from claimguard.review.correction import original
from claimguard.review.gate import main as gate_main
from claimguard.run import main as run_main
from claimguard.ui.__main__ import main as ui_main
from claimguard.ui.apply import main as apply_main
from claimguard.ui.decisions import main as decisions_main

ROOT = Path(__file__).resolve().parents[1]
DEV = ROOT / "data" / "development"
CLAIM = "CG-785C09BD9CC8"  # R003 and R004 FAIL


def page_data(path):
    """The embedded data, read back the way the browser does."""
    html = Path(path).read_text(encoding="utf-8")
    return json.loads(re.search(r'<script type="application/json" id="claimguard-data">(.*?)</script>', html, re.S).group(1))


def without_times(data):
    """Page data minus what differs between two appends of the same events
    to two copies of a log: the copy's path, when each row was recorded, its
    hashes, and the command that appended."""
    data = json.loads(json.dumps(data))
    data["sources"]["audit_log"] = None
    audit = data["audit"]
    audit["head"] = audit["log"] = None
    for row in audit["events"]:
        for key in ("recorded_at", "hash", "previous_hash"):
            row.pop(key)
        row["event"].pop("command", None)
    return data


class ApplyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.base = Path(cls._tmp.name)
        cls.results = cls.base / "pred.jsonl"
        cls.run_log = cls.base / "run_audit.jsonl"
        with contextlib.redirect_stdout(io.StringIO()):
            run_main(["--input", str(DEV / "claims.jsonl"), "--output", str(cls.results), "--audit-log", str(cls.run_log)])
        claims = {c["claim_id"]: c for c in load_jsonl(DEV / "claims.jsonl")}
        cls.hash = original(claims[CLAIM]).input_hash

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(dir=self.base))
        self.directory = self.dir / "actors.json"
        self.directory.write_text(json.dumps({"Reviewer 01": "reviewer"}), encoding="utf-8")

    def fresh_log(self, name):
        log = self.dir / f"{name}.jsonl"
        shutil.copy(self.run_log, log)
        shutil.copy(chain.default_anchor(self.run_log), chain.default_anchor(log))
        return log

    def decisions(self, **changes):
        events = [{"event": "review_decision", "claim_id": CLAIM, "rule_id": rule, "action": "dismiss_with_reason",
                   "actor": "Reviewer 01", "reason": "Checked at the source.", "created_at": "2026-10-01T10:00:00Z",
                   "original_status": "FAIL", "input_hash": self.hash, **changes} for rule in ("R003", "R004")]
        path = self.dir / "decisions.jsonl"
        path.write_text("".join(json.dumps(e) + "\n" for e in events), encoding="utf-8")
        return path

    def common(self, log):
        return ["--log", str(log), "--directory", str(self.directory),
                "--claims", str(DEV / "claims.jsonl"), "--results", str(self.results)]

    def apply(self, log, *extra):
        with contextlib.redirect_stdout(io.StringIO()) as printed:
            code = apply_main(["--decisions", str(self.decisions()), *self.common(log),
                               "--output", str(self.dir / "apply.html"), *extra])
        return code, printed.getvalue()

    def test_one_command_matches_the_three_separate_ones(self):
        decisions = self.decisions()
        three, one = self.fresh_log("three"), self.fresh_log("one")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(decisions_main(["--decisions", str(decisions), *self.common(three)]), 0)
            gate_code = gate_main([*self.common(three), "--output", str(self.dir / "gate_three.jsonl")])
            ui_main(["--results", str(self.results), "--claims", str(DEV / "claims.jsonl"),
                     "--audit-log", str(three), "--output", str(self.dir / "three.html")])
        with contextlib.redirect_stdout(io.StringIO()) as printed:
            code = apply_main(["--decisions", str(decisions), *self.common(one), "--output", str(self.dir / "one.html"),
                               "--gate-output", str(self.dir / "gate_one.jsonl")])
        self.assertEqual(code, gate_code)
        self.assertEqual(code, 1)  # development has blocked claims

        events = {name: [row["event"] for row in load_jsonl(log)] for name, log in (("three", three), ("one", one))}
        self.assertEqual([e.get("command") for e in events["one"] if e["event"] == "append_performed"],
                         ["claimguard.run", "claimguard.ui.apply"])  # the event names the command that ran
        for name in events:
            for e in events[name]:
                e.pop("command", None)
        self.assertEqual(events["one"], events["three"])
        self.assertEqual(load_jsonl(self.dir / "gate_one.jsonl"), load_jsonl(self.dir / "gate_three.jsonl"))
        self.assertEqual(without_times(page_data(self.dir / "one.html")), without_times(page_data(self.dir / "three.html")))
        self.assertTrue(page_data(self.dir / "one.html")["audit"]["valid"])

        head, count = chain.verify(one, chain.default_anchor(one))
        self.assertIn("2 decision(s) appended, 0 already in the audit log.", printed.getvalue())
        self.assertIn("400 claims:", printed.getvalue())
        self.assertTrue(printed.getvalue().rstrip().endswith(chain.record_hint(count, head)))  # the last line

    def test_applying_the_same_file_again_adds_nothing(self):
        log = self.fresh_log("again")
        self.apply(log)
        before = log.read_bytes()
        code, printed = self.apply(log)
        self.assertEqual(code, 1)
        self.assertEqual(log.read_bytes(), before)  # no decision, no append_performed
        self.assertIn("0 decision(s) appended, 2 already in the audit log.", printed)
        self.assertTrue((self.dir / "apply.html").exists())

    def test_a_refused_decision_appends_nothing_and_rebuilds_nothing(self):
        log = self.fresh_log("refused")
        before = log.read_bytes()
        bad = self.decisions(original_status="PASS")  # a stale status
        with contextlib.redirect_stdout(io.StringIO()) as printed:
            code = apply_main(["--decisions", str(bad), *self.common(log), "--output", str(self.dir / "apply.html")])
        self.assertEqual(code, 2)
        self.assertIn("Nothing appended: no decision appended", printed.getvalue())
        self.assertEqual(log.read_bytes(), before)
        self.assertFalse((self.dir / "apply.html").exists())

    def test_the_head_recorded_outside_is_checked_before_appending(self):
        log = self.fresh_log("expect")
        head, count = chain.verify(log, chain.default_anchor(log))
        before = log.read_bytes()
        code, printed = self.apply(log, "--expect-count", str(count), "--expect-head", "0" * 64)
        self.assertEqual(code, 2)
        self.assertIn("does not match the head recorded outside", printed)
        self.assertEqual(log.read_bytes(), before)
        self.assertEqual(self.apply(log, "--expect-count", str(count), "--expect-head", head)[0], 1)
        self.assertEqual(chain.verify(log, chain.default_anchor(log))[1], count + 3)  # 2 decisions, 1 append_performed

    def test_a_missing_anchor_names_the_way_out(self):
        log = self.fresh_log("noanchor")
        Path(chain.default_anchor(log)).unlink()
        code, printed = self.apply(log)
        self.assertEqual(code, 2)
        self.assertIn("--restore-anchor", printed)


if __name__ == "__main__":
    unittest.main()
