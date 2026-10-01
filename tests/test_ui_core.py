"""Tests for the interface's consistency rules and its pure logic (core.js).

Static checks need nothing but Python. The core.js checks run it in Node and
compare it with the Python backend it mirrors; they are skipped if Node is
not installed.
"""
import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

from claimguard.review.routing import outstanding
from claimguard.ui.page import JS_FILES, STATIC

ROOT = Path(__file__).resolve().parents[1]
CORE = STATIC / "core.js"
NODE = shutil.which("node")


def js_sources():
    return {name: (STATIC / name).read_text(encoding="utf-8") for name in JS_FILES}


def sprite_ids():
    return set(re.findall(r'<symbol id="i-([a-z0-9-]+)"', (STATIC / "icons.svg").read_text(encoding="utf-8")))


def node(expr_js, payload):
    """Run core.js in Node and return JSON.stringify(<expr_js>) with `input` bound to payload."""
    code = (f"const Core = require({json.dumps(str(CORE))});\n"
            f"const input = {json.dumps(payload)};\n"
            f"process.stdout.write(JSON.stringify({expr_js}));\n")
    done = subprocess.run([NODE, "-e", code], capture_output=True, text=True, encoding="utf-8", check=True)
    return json.loads(done.stdout)


class ConsistencyTests(unittest.TestCase):
    def test_every_js_file_is_inlined_and_every_page_file_listed(self):
        on_disk = {p.name for p in STATIC.glob("*.js")}
        self.assertEqual(on_disk, set(JS_FILES))
        self.assertEqual(JS_FILES[0], "core.js")
        self.assertEqual(JS_FILES[-1], "main.js")

    def test_every_icon_named_exists_in_the_sprite(self):
        ids = sprite_ids()
        named = set()
        for text in js_sources().values():
            named |= set(re.findall(r'\bicon\(\s*"([a-z0-9-]+)"', text))
            named |= set(re.findall(r'\bicon:\s*"([a-z0-9-]+)"', text))
        self.assertTrue(named)
        self.assertEqual(sorted(named - ids), [])

    def test_each_concept_has_its_own_icon(self):
        # Core's tables map concepts to icons. A status, a route, an action and
        # an explanation source must never share a glyph with each other.
        core = CORE.read_text(encoding="utf-8")
        tables = {}
        for table in ("STATUS", "ROUTE", "ACTION", "SOURCE"):
            block = re.search(rf"const {table} = \{{(.*?)\n  \}};", core, re.S).group(1)
            tables[table] = re.findall(r'icon: "([a-z0-9-]+)"', block)
        flat = [i for icons in tables.values() for i in icons]
        self.assertEqual(len(flat), len(set(flat)), tables)

    def test_navigation_icons_are_unique(self):
        icons = {}
        for name, text in js_sources().items():
            if name.startswith("page-"):
                m = re.search(r'registerPage\(\{\s*key: "([a-z]+)",\s*label: "[^"]+",\s*icon: "([a-z0-9-]+)"', text)
                self.assertIsNotNone(m, name)
                icons[m.group(1)] = m.group(2)
        nav = {k: v for k, v in icons.items() if k != "components"}
        self.assertEqual(set(nav), {"dashboard", "queue", "claims", "audit", "rules", "evaluation", "settings"})
        self.assertEqual(len(set(nav.values())), len(nav), nav)

    def test_no_html_injection_api(self):
        banned = re.compile(r"\binnerHTML\b|\bouterHTML\b|insertAdjacentHTML|document\.write|\beval\(|new Function\(")
        for name, text in js_sources().items():
            self.assertIsNone(banned.search(text), name)

    def test_colors_live_only_in_the_tokens(self):
        css = (STATIC / "app.css").read_text(encoding="utf-8")
        root_end = css.index("}", css.index(":root"))
        self.assertEqual(re.findall(r"#[0-9A-Fa-f]{3,8}\b|rgba?\(", css[root_end:]), [])

    def test_no_external_resource(self):
        # The page must open offline: no CDN script, stylesheet or font.
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        for text in [html, (STATIC / "app.css").read_text(encoding="utf-8"), *js_sources().values()]:
            self.assertIsNone(re.search(r"(src|href)=\"https?://|@import|url\(\s*['\"]?https?:", text))


@unittest.skipUnless(NODE, "Node is not installed")
class CoreLogicTests(unittest.TestCase):
    def test_outstanding_matches_the_python_backend(self):
        reasons = [{"rule_id": "R003", "status": "FAIL", "severity": "high"},
                   {"rule_id": "R010", "status": "UNABLE_TO_ASSESS", "severity": "medium"},
                   {"rule_id": "R007", "status": "NOT_IMPLEMENTED", "severity": "high"}]
        routing = {"claim_id": "CG-1", "route": "ESCALATE", "reasons": reasons}
        ev = lambda rule, action, status, actor="A", reason="r", cid="CG-1": {
            "claim_id": cid, "rule_id": rule, "action": action, "actor": actor, "reason": reason, "original_status": status}
        cases = [
            [],
            [ev("R003", "dismiss_with_reason", "FAIL")],
            [ev("R003", "dismiss_with_reason", "FAIL"), ev("R010", "dismiss_with_reason", "UNABLE_TO_ASSESS")],
            [ev("R003", "dismiss_with_reason", "FAIL"), ev("R003", "confirm_issue", "FAIL")],   # latest counts
            [ev("R003", "dismiss_with_reason", "PASS")],                                        # stale status
            [ev("R003", "dismiss_with_reason", "FAIL", actor=" ")],                            # blank actor
            [ev("R003", "dismiss_with_reason", "FAIL", reason="")],                            # blank reason
            [ev("R003", "dismiss_with_reason", "FAIL", cid="CG-2")],                           # other claim
            [ev("R007", "dismiss_with_reason", "NOT_IMPLEMENTED")],                            # never dismissable
            [ev("R010", "request_information", "UNABLE_TO_ASSESS")],
        ]
        for events in cases:
            js = node("Core.outstanding(input.routing, input.events)", {"routing": routing, "events": events})
            self.assertEqual(js, outstanding(routing, events), events)

    def entry(self, reasons, flag=None):
        results = [{"rule_id": f"R{i:03}", "status": "PASS"} for i in range(1, 16)]
        for r in reasons:
            results[int(r["rule_id"][1:]) - 1]["status"] = r["status"]
        return {"input_hash": "h1", "flag": flag, "explanations": [], "provenance": {"adapter": "jsonl", "line_number": 3},
                "results": results, "route": {"claim_id": "CG-1", "route": "ESCALATE" if reasons else "CLEAR", "reasons": reasons}}

    def outcome(self, entry, events):
        return node("Core.outcome(input.entry, input.events)", {"entry": entry, "events": events})

    def test_outcomes(self):
        fail = [{"rule_id": "R003", "status": "FAIL", "severity": "high"},
                {"rule_id": "R010", "status": "FAIL", "severity": "medium"}]
        e = self.entry(fail)
        d = lambda rule, action, h="h1": {"claim_id": "CG-1", "rule_id": rule, "action": action, "actor": "A",
                                          "reason": "r", "original_status": "FAIL", "input_hash": h}
        self.assertEqual(self.outcome(self.entry([]), []), "ready")
        self.assertEqual(self.outcome(e, []), "to_review")
        self.assertEqual(self.outcome(e, [d("R003", "dismiss_with_reason")]), "in_review")
        self.assertEqual(self.outcome(e, [d("R003", "dismiss_with_reason"), d("R010", "dismiss_with_reason")]), "ready")
        self.assertEqual(self.outcome(e, [d("R003", "confirm_issue")]), "correction_needed")
        self.assertEqual(self.outcome(e, [d("R003", "confirm_issue"), d("R010", "request_information")]), "waiting_information")
        self.assertEqual(self.outcome(e, [d("R010", "request_information"), d("R003", "mark_corrected_for_recheck")]),
                         "awaiting_recheck")
        # Once a corrected version exists, its own results decide next.
        self.assertEqual(self.outcome(dict(e, versions=[{"version": 2}]), [d("R003", "mark_corrected_for_recheck")]), "rechecked")
        # A decision taken on another version of the claim does not count.
        self.assertEqual(self.outcome(e, [d("R003", "dismiss_with_reason", "h0"), d("R010", "dismiss_with_reason", "h0")]),
                         "to_review")

    def test_lifecycle_has_the_eight_stages(self):
        e = self.entry([{"rule_id": "R003", "status": "FAIL", "severity": "high"}],
                       flag={"hits": [{"path": "/notes", "family": "override", "layer": "text"}]})
        stages = node("Core.lifecycle(input, [])", e)
        self.assertEqual([s["key"] for s in stages],
                         ["received", "ingested", "checked", "screened", "explained", "routed", "review", "outcome"])
        by = {s["key"]: s for s in stages}
        self.assertEqual(by["checked"]["state"], "fail")
        self.assertEqual(by["screened"]["state"], "warn")
        # Plain words: no adapter, line number or zero count.
        self.assertEqual(by["received"]["summary"], "Received")
        self.assertEqual(by["checked"]["summary"], "14 passed · 1 failed")
        self.assertEqual(by["screened"]["summary"], "Flagged for injection")
        self.assertEqual(by["explained"]["summary"], "Withheld from the model")
        self.assertEqual(by["review"]["summary"], "0 / 1 decided")
        self.assertEqual(by["outcome"]["outcome"], "to_review")
        clean = {s["key"]: s for s in node("Core.lifecycle(input, [])", self.entry([]))}
        self.assertEqual(clean["screened"]["summary"], "No injection found")
        self.assertEqual(clean["checked"]["summary"], "15 passed")

    def test_run_stages_match_the_claims(self):
        data = {"run": None, "rejected": [{"stage": "json"}],
                "claims": [self.entry([]), self.entry([{"rule_id": "R003", "status": "FAIL", "severity": "high"}])]}
        stages = {s["key"]: s for s in node("Core.runStages(input, [])", data)}
        self.assertEqual(stages["received"]["summary"], "3 records")
        self.assertEqual((stages["ingested"]["state"], stages["ingested"]["summary"]), ("warn", "2 accepted · 1 rejected"))
        self.assertEqual(stages["checked"]["summary"], "30 checks")
        self.assertEqual(stages["screened"]["summary"], "No injection found")
        self.assertEqual(stages["explained"]["state"], "skipped")
        self.assertEqual(stages["routed"]["summary"], "1 escalate · 0 review · 1 clear")
        self.assertEqual(stages["review"]["summary"], "0 / 1 findings decided")
        self.assertEqual(stages["outcome"]["summary"], "1 ready · 1 open")

    def test_run_stages_mention_a_problem_only_when_there_is_one(self):
        ai = {"provider": "mock", "by_source": {"provider": 495, "skipped_flagged": 4}, "failures": {}}
        data = {"run": {"input": {"records": 2}, "rule_errors": [], "ai": {"summary": ai}}, "rejected": [],
                "claims": [self.entry([]), self.entry([])]}
        stages = {s["key"]: s for s in node("Core.runStages(input, [])", data)}
        self.assertEqual(stages["ingested"]["summary"], "2 accepted")
        self.assertEqual(stages["explained"]["summary"], "495 explained · 4 withheld")
        data["run"]["rule_errors"] = [{"rule_id": "R003"}]
        ai["failures"] = {"timeout": 2}
        stages = {s["key"]: s for s in node("Core.runStages(input, [])", data)}
        self.assertEqual(stages["checked"]["summary"], "30 checks · 1 rule error")
        self.assertEqual((stages["explained"]["state"], stages["explained"]["summary"]),
                         ("warn", "495 explained · 4 withheld · 2 fallbacks"))

    def test_field_labels_and_plain_values(self):
        claim = {"lines": [{"line_id": "L1"}, {"line_id": None}], "attachments": [{"attachment_id": "DOC-1"}]}
        pointers = ["/coverage/end_date", "/lines/0/service_date", "/lines/1/net_amount", "/total_amount",
                    "/lines", "/attachments/0/text", "/coverage/beneficiary_patient_id", ""]
        self.assertEqual(node("input.pointers.map((p) => Core.fieldLabel(p, input.claim))", {"pointers": pointers, "claim": claim}),
                         ["Coverage › End date", "Line L1 › Service date", "Line 2 › Net amount", "Total amount",
                          "Service lines", "Document DOC-1 › Text", "Coverage › Beneficiary patient ID", "Claim"])
        values = [None, "", "active", 1510, 0.5, True, [], ["a", "b"],
                  [{"line_id": "L1", "modifier": None, "quantity": 2}], {"status": "approved", "max_quantity": 10}]
        self.assertEqual(node("input.map(Core.plain)", values),
                         ["—", "—", "active", "1,510", "0.5", "Yes", "None", "a, b",
                          "L1 · Modifier: — · Quantity: 2", "Status: approved\nMax quantity: 10"])

    def test_explanation_labels_are_honest(self):
        labels = node("Object.fromEntries(Object.entries(Core.SOURCE).map(([k, v]) => [k, v.label]))", None)
        self.assertEqual(labels["mock"], "Rule's explanation")
        self.assertEqual(labels["provider"], "AI explanation")
        self.assertTrue(labels["fallback"].startswith("Rule's explanation"))

    def test_one_date_format(self):
        self.assertEqual(node("[Core.date('2026-04-24'), Core.date(null), Core.money(1520, 'SAR'), Core.money(NaN)]", None),
                         ["24 Apr 2026", "—", "1,520.00 SAR", "—"])


if __name__ == "__main__":
    unittest.main()
