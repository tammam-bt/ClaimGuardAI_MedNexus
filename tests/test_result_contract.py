"""The result contract, beyond what the official scorer checks.

src/evaluate.py accepts a result whose severity, corrective_action, method or
review_status disagrees with the rulebook; a requires_human_review that is any
truthy value such as "no"; evidence equal only because 1 == True in Python;
and pointers such as /lines/-1/... that are not RFC 6901. It also rejects a
correct NaN citation, because NaN != NaN (DEC-003).

contract_errors() closes those holes. It is tested against the 9,000 public
gold results (so it is never stricter than the gold), then applied to every
registered rule on all 600 public claims, so a new rule, or a runner that
builds results by hand, cannot slip through.
"""
import copy
import json
import math
import re
import unittest
from pathlib import Path

from claimguard._pack import config, load_jsonl, make_result
from claimguard.engine.context import RuleContext
from claimguard.engine.policy import PolicyBook
from claimguard.engine.registry import REGISTRY
import claimguard.rules  # noqa: F401  registers every rule module
from evaluate import index  # tests may read the pack; importing claimguard._pack put src/ on sys.path

ROOT = Path(__file__).resolve().parents[1]
SPLITS = ("development", "validation", "stress")
LIST_INDEX = re.compile(r"^(0|[1-9][0-9]*)$")


def resolve(claim, path):
    """Strict RFC 6901: list indexes are canonical non-negative integers. Raises ValueError."""
    if not path.startswith("/"):
        raise ValueError(f"pointer {path!r} does not start with /")
    obj = claim
    for raw in path[1:].split("/"):
        part = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(obj, list):
            if not LIST_INDEX.match(part) or int(part) >= len(obj):
                raise ValueError(f"pointer {path!r}: {raw!r} is not a valid index")
            obj = obj[int(part)]
        elif isinstance(obj, dict) and part in obj:
            obj = obj[part]
        else:
            raise ValueError(f"pointer {path!r}: no member {raw!r}")
    return obj


def same(a, b):
    """Equal with identical JSON types (so True is not 1), and NaN equal to NaN."""
    if type(a) is not type(b):
        return False
    if isinstance(a, float):
        return a == b or (math.isnan(a) and math.isnan(b))
    if isinstance(a, list):
        return len(a) == len(b) and all(map(same, a, b))
    if isinstance(a, dict):
        return a.keys() == b.keys() and all(same(a[k], b[k]) for k in a)
    return a == b


def contract_errors(result, claim, rule):
    """Every way result breaks the contract. Empty means valid."""
    errors = []
    flagged = result["status"] in ("FAIL", "UNABLE_TO_ASSESS")
    expected = {
        "rule_version": rule["version"], "rule_source": rule["source"], "severity": rule["severity"],
        "corrective_action": rule["corrective_action"] if flagged else "",
        "requires_human_review": flagged, "confidence": None, "confidence_kind": "not_probabilistic",
        "method": "deterministic", "review_status": "unreviewed",
    }
    for key, value in expected.items():
        if not same(result[key], value):
            errors.append(f"{key} is {result[key]!r}, expected {value!r}")

    ids, order = result["affected_line_ids"], [line["line_id"] for line in claim["lines"]]
    if ids and result["status"] != "FAIL":
        errors.append(f"affected_line_ids on {result['status']}")
    if not set(ids) <= set(order) or ids != sorted(set(ids), key=order.index):
        errors.append(f"affected_line_ids {ids} are foreign, repeated or out of claim order")

    for e in result["evidence"]:
        try:
            if not same(resolve(claim, e["path"]), e["value"]):
                errors.append(f"evidence {e['path']} value {e['value']!r} differs from the claim")
        except ValueError as err:
            errors.append(str(err))
    return errors


class ResultContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cfg = config(ROOT)
        cls.rules = {r["rule_id"]: r for r in cfg["rules"]}
        cls.book, cls.services = PolicyBook(cfg["policies"]), cfg["services"]
        cls.claims = {s: {c["claim_id"]: c for c in load_jsonl(ROOT / "data" / s / "claims.jsonl")} for s in SPLITS}
        cls.gold = {s: load_jsonl(ROOT / "data" / s / "expected_results.jsonl") for s in SPLITS}

    def run_rule(self, rule_id, claim):
        rule = self.rules[rule_id]
        v = REGISTRY[rule_id](RuleContext(claim, rule, self.book.resolve(claim["policy_id"]), self.services, {}))
        return make_result(claim, rule, v.status, v.paths, v.message, list(v.line_ids))

    def test_contract_is_never_stricter_than_the_gold(self):
        broken = [(r["claim_id"], r["rule_id"], err) for s in SPLITS for r in self.gold[s]
                  for err in contract_errors(r, self.claims[s][r["claim_id"]], self.rules[r["rule_id"]])]
        self.assertEqual(broken[:10], [])

    def test_every_registered_rule_meets_the_contract(self):
        self.assertTrue(REGISTRY, "no rule registered: this test would pass vacuously")
        broken = []
        for s in SPLITS:
            for claim in self.claims[s].values():
                for rule_id in sorted(REGISTRY):
                    for err in contract_errors(self.run_rule(rule_id, claim), claim, self.rules[rule_id]):
                        broken.append((claim["claim_id"], rule_id, err))
        self.assertEqual(broken[:10], [], f"{len(broken)} contract errors")

    def test_catches_what_the_official_scorer_accepts(self):
        claims = self.claims["development"]
        base = next(r for r in self.gold["development"] if r["status"] == "FAIL" and len(claims[r["claim_id"]]["lines"]) == 1
                    and any(e["path"] == "/lines/0/quantity" and e["value"] == 1 for e in r["evidence"]))
        claim, rule = claims[base["claim_id"]], self.rules[base["rule_id"]]
        q = next(i for i, e in enumerate(base["evidence"]) if e["path"] == "/lines/0/quantity")

        def with_evidence(**kw):
            r = copy.deepcopy(base)
            r["evidence"][q].update(kw)
            return r

        holes = {
            "severity": {**base, "severity": "low" if rule["severity"] != "low" else "high"},
            "method": {**base, "method": "magic"},
            "review_status": {**base, "review_status": "approved"},
            "requires_human_review": {**base, "requires_human_review": "no"},
            "corrective_action": {**base, "corrective_action": "Just approve it."},
            "differs from the claim": with_evidence(value=True),
            "is not a valid index": with_evidence(path="/lines/-1/quantity"),
        }
        for expected_error, result in holes.items():
            with self.subTest(hole=expected_error):
                index([result], claims)  # the official scorer accepts it...
                errors = contract_errors(result, claim, rule)  # ...the contract does not
                self.assertTrue(any(expected_error in e for e in errors), errors)

    def test_nan_citation_is_valid_but_the_official_scorer_rejects_it(self):
        """Pins the scorer limitation recorded in DEC-003. If this starts failing, update DEC-003."""
        claim = copy.deepcopy(next(iter(self.claims["development"].values())))
        claim["lines"][0]["unit_price"] = float("nan")
        claim = json.loads(json.dumps(claim))  # as the loader would read it
        result = json.loads(json.dumps(self.run_rule("R007", claim)))  # as a results file would hold it
        self.assertEqual(result["status"], "UNABLE_TO_ASSESS")
        self.assertIn("/lines/0/unit_price", [e["path"] for e in result["evidence"]])
        self.assertEqual(contract_errors(result, claim, self.rules["R007"]), [])
        with self.assertRaisesRegex(ValueError, "Evidence value mismatch"):
            index([result], {claim["claim_id"]: claim})


if __name__ == "__main__":
    unittest.main()
