"""Tests for escalation routing and the approval gate (claimguard.review.routing, DEC-004)."""
import unittest
from collections import Counter
from pathlib import Path

from claimguard._pack import config, load_jsonl
from claimguard.review.routing import (
    CLEAR, ESCALATE, REVIEW, ROUTING_POLICY_VERSION, outstanding, route_claim, route_run,
)

ROOT = Path(__file__).resolve().parents[1]
CLAIM = "CG-27BFD8541DEB"


class ResultsBuilder(unittest.TestCase):
    """Shared helpers; holds no tests of its own."""

    @classmethod
    def setUpClass(cls):
        cls.severity = {r["rule_id"]: r["severity"] for r in config(ROOT)["rules"]}

    def results(self, claim_id=CLAIM, **statuses):
        """15 PASS results for one claim, with statuses overridden by rule, e.g. R007="FAIL"."""
        return [
            {"claim_id": claim_id, "rule_id": rid, "status": statuses.get(rid, "PASS"), "severity": sev}
            for rid, sev in self.severity.items()
        ]


class RoutingTests(ResultsBuilder):
    def route(self, **statuses):
        return route_claim(self.results(**statuses))["route"]

    def test_severities_are_the_rulebooks(self):
        self.assertEqual(self.severity["R007"], "high")
        self.assertEqual(self.severity["R013"], "medium")

    def test_all_pass_or_not_applicable_is_clear(self):
        row = route_claim(self.results(R008="NOT_APPLICABLE", R009="NOT_APPLICABLE"))
        self.assertEqual(row, {"claim_id": CLAIM, "route": CLEAR, "reasons": [],
                               "routing_policy_version": ROUTING_POLICY_VERSION})

    def test_medium_severity_findings_are_review(self):
        self.assertEqual(self.route(R013="FAIL"), REVIEW)
        self.assertEqual(self.route(R010="UNABLE_TO_ASSESS"), REVIEW)

    def test_high_severity_findings_escalate(self):
        self.assertEqual(self.route(R007="FAIL"), ESCALATE)
        self.assertEqual(self.route(R003="UNABLE_TO_ASSESS"), ESCALATE)  # low confidence on a high rule

    def test_not_implemented_escalates_whatever_the_severity(self):
        self.assertEqual(self.route(R014="NOT_IMPLEMENTED"), ESCALATE)

    def test_reasons_list_every_flagged_finding_in_rule_order(self):
        results = self.results(R013="FAIL", R003="UNABLE_TO_ASSESS")
        row = route_claim(list(reversed(results)))
        self.assertEqual(row["route"], ESCALATE)
        self.assertEqual(row["reasons"], [
            {"rule_id": "R003", "status": "UNABLE_TO_ASSESS", "severity": "high"},
            {"rule_id": "R013", "status": "FAIL", "severity": "medium"},
        ])

    def test_incomplete_or_mixed_results_are_rejected_not_cleared(self):
        results = self.results()
        with self.assertRaises(ValueError):
            route_claim(results[:-1])
        with self.assertRaises(ValueError):
            route_claim(results[:-1] + [results[0]])
        with self.assertRaises(ValueError):
            route_claim(results[:-1] + [{**results[-1], "claim_id": "CG-OTHER"}])
        with self.assertRaises(ValueError):
            route_claim(results[:-1] + [{**results[-1], "status": "APPROVED"}])

    def test_route_run_groups_by_claim_in_order(self):
        rows = route_run(self.results("CG-B", R007="FAIL") + self.results("CG-A"))
        self.assertEqual([(r["claim_id"], r["route"]) for r in rows], [("CG-B", ESCALATE), ("CG-A", CLEAR)])

    def test_public_gold_route_counts(self):
        """Pins the numbers quoted in DEC-004; a change here is a policy change."""
        expected = {
            "development": {ESCALATE: 201, REVIEW: 63, CLEAR: 136},
            "validation": {ESCALATE: 75, REVIEW: 22, CLEAR: 53},
            "stress": {ESCALATE: 25, REVIEW: 13, CLEAR: 12},
        }
        for split, counts in expected.items():
            with self.subTest(split=split):
                rows = route_run(load_jsonl(ROOT / "data" / split / "expected_results.jsonl"))
                self.assertEqual(Counter(r["route"] for r in rows), counts)

    def test_baseline_with_unimplemented_rules_never_clears(self):
        rows = route_run(load_jsonl(ROOT / "examples" / "baseline_predictions.jsonl"))
        self.assertEqual({r["route"] for r in rows}, {ESCALATE})


class ApprovalGateTests(ResultsBuilder):
    def event(self, rule_id, action="dismiss_with_reason", original_status="FAIL", **kw):
        """A review event shaped like schemas/review_event.schema.json."""
        return {"claim_id": CLAIM, "rule_id": rule_id, "action": action, "actor": "reviewer-1",
                "reason": "Verified against the source bill.", "created_at": "2026-09-28T10:00:00Z",
                "original_status": original_status, **kw}

    def pending(self, events, **statuses):
        return outstanding(route_claim(self.results(**statuses)), events)

    def test_clear_needs_nothing(self):
        self.assertEqual(self.pending([]), [])

    def test_flagged_without_decision_is_outstanding(self):
        self.assertEqual(self.pending([], R007="FAIL"), [
            {"rule_id": "R007", "status": "FAIL", "severity": "high", "why": "no review decision recorded"},
        ])

    def test_named_dismissal_with_reason_approves(self):
        self.assertEqual(self.pending([self.event("R007")], R007="FAIL"), [])

    def test_every_flagged_finding_needs_its_own_approval(self):
        pending = self.pending([self.event("R007")], R007="FAIL", R013="FAIL")
        self.assertEqual([p["rule_id"] for p in pending], ["R013"])

    def test_only_dismissal_approves(self):
        for action in ("confirm_issue", "request_information", "mark_corrected_for_recheck"):
            with self.subTest(action=action):
                pending = self.pending([self.event("R007", action)], R007="FAIL")
                self.assertEqual(pending[0]["why"], f"latest decision is {action}")

    def test_latest_decision_wins(self):
        dismiss, ask = self.event("R007"), self.event("R007", "request_information")
        self.assertEqual(len(self.pending([dismiss, ask], R007="FAIL")), 1)
        self.assertEqual(self.pending([ask, dismiss], R007="FAIL"), [])

    def test_stale_decision_on_another_status_does_not_count(self):
        pending = self.pending([self.event("R003", original_status="FAIL")], R003="UNABLE_TO_ASSESS")
        self.assertEqual(pending[0]["why"], "no review decision recorded")

    def test_anonymous_or_unexplained_decision_does_not_count(self):
        for kw in ({"actor": ""}, {"actor": "  "}, {"reason": ""}, {"reason": None}):
            with self.subTest(**kw):
                self.assertEqual(len(self.pending([self.event("R007", **kw)], R007="FAIL")), 1)

    def test_decision_for_another_claim_does_not_count(self):
        self.assertEqual(len(self.pending([self.event("R007", claim_id="CG-OTHER")], R007="FAIL")), 1)

    def test_not_implemented_cannot_be_dismissed(self):
        pending = self.pending([self.event("R014", original_status="NOT_IMPLEMENTED")], R014="NOT_IMPLEMENTED")
        self.assertEqual(pending[0]["why"], "check not implemented; cannot be dismissed")

    def test_approval_never_changes_the_findings(self):
        results = self.results(R007="FAIL")
        before = [dict(r) for r in results]
        outstanding(route_claim(results), [self.event("R007")])
        self.assertEqual(results, before)


if __name__ == "__main__":
    unittest.main()
