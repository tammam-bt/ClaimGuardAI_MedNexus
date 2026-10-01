"""U2.6 | The runner: every claim through all 15 rules, in rules.json order.

One runner for the whole package. Rules registered with @rule run; a rule not
registered yet reports NOT_IMPLEMENTED, never PASS.

A rule that raises is a bug, but one bug must not cost a whole held-out run.
By default that result becomes UNABLE_TO_ASSESS, flagged for human review,
and the error is recorded in Engine.errors (and from there in the run
manifest). Only the exception's type is recorded: its message can quote the
claim, and the manifest never does. strict=True re-raises instead, with the
full traceback; tests and CI use it so bugs stay loud.

Each rule sees a read-only deep copy of the results before it (prior), so no
rule can alter what an earlier rule reported.
"""
import copy
from pathlib import Path
from types import MappingProxyType
from typing import Any, Dict, List, Mapping, NamedTuple, Optional, Union

import claimguard.rules  # noqa: F401  importing the package registers every rule module
from claimguard._pack import config, make_result
from claimguard.engine.context import RuleContext
from claimguard.engine.policy import PolicyBook
from claimguard.engine.registry import REGISTRY

ROOT = Path(__file__).resolve().parents[2]
NOT_IMPLEMENTED_MESSAGE = "Student implementation required."
RULE_ERROR_MESSAGE = "This check failed to run because of an internal error. Review it manually."


class RuleError(NamedTuple):
    claim_id: str
    rule_id: str
    error: str


class Engine:
    def __init__(self, root: Optional[Union[str, Path]] = None, *, strict: bool = False):
        self.root = Path(root) if root is not None else ROOT
        self.cfg = config(self.root)
        self.policies = PolicyBook(self.cfg["policies"])
        self.strict = strict
        self.errors: List[RuleError] = []
        stray = sorted(set(REGISTRY) - {r["rule_id"] for r in self.cfg["rules"]})
        if stray:
            raise RuntimeError(f"rules registered but absent from rules/rules.json: {stray}")

    def evaluate_claim(self, claim: Mapping[str, Any]) -> List[Dict[str, Any]]:
        """All 15 results for one accepted claim, R001 to R015."""
        policy = self.policies.resolve(claim["policy_id"])
        prior: Dict[str, Dict[str, Any]] = {}
        for rule in self.cfg["rules"]:
            view = MappingProxyType(copy.deepcopy(prior))
            prior[rule["rule_id"]] = self._evaluate_rule(claim, rule, policy, view)
        return list(prior.values())

    def _evaluate_rule(self, claim, rule, policy, prior) -> Dict[str, Any]:
        fn = REGISTRY.get(rule["rule_id"])
        if fn is None:
            return make_result(claim, rule, "NOT_IMPLEMENTED", [], NOT_IMPLEMENTED_MESSAGE)
        try:
            v = fn(RuleContext(claim, rule, policy, self.cfg["services"], prior))
            return make_result(claim, rule, v.status, list(v.paths), v.message, list(v.line_ids))
        except Exception as e:
            if self.strict:
                raise
            self.errors.append(RuleError(claim["claim_id"], rule["rule_id"], type(e).__name__))
            return make_result(claim, rule, "UNABLE_TO_ASSESS", ["/claim_id"], RULE_ERROR_MESSAGE)
