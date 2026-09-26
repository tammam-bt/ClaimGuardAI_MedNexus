"""What a rule is given.

A rule receives one RuleContext and nothing else. It is read-only by contract:
never mutate claim, policy or services. The dataclass is frozen, but the
mappings inside it are ordinary dicts, so this is a rule of the codebase, not
something Python enforces. Corrections create a new claim version and a new
run; they never edit the claim a rule is looking at.
"""
from dataclasses import dataclass
from typing import Any, Iterator, Mapping, Optional, Tuple


@dataclass(frozen=True)
class RuleContext:
    claim: Mapping[str, Any]
    """The original normalized envelope. Every key always exists (transport
    validation guarantees it); a missing value is None, never an absent key."""

    rule: Mapping[str, Any]
    """This rule's entry from rules/rules.json: rule_id, title, severity,
    logic, corrective_action, version, source."""

    policy: Optional[Mapping[str, Any]]
    """The claim's policy from rules/policies.json, or None when policy_id is
    unrecognised (e.g. EDU-NO-POLICY). None means no policy was supplied. It is
    never proof of non-coverage: report UNABLE_TO_ASSESS, not FAIL."""

    services: Mapping[str, Any]
    """rules/services.json keyed by service code. Use it for R011's catalogue
    check only. Price and quantity ceilings come from policy, not from here."""

    prior: Mapping[str, dict]
    """Results of rules that already ran on this claim, keyed by rule_id.
    Rules run in rules.json order, R001 to R015, so R009 can read prior['R008']."""

    @property
    def rule_id(self) -> str:
        return self.rule["rule_id"]

    def lines(self) -> Iterator[Tuple[int, Mapping[str, Any]]]:
        """(index, line) pairs in claim order. The index is what JSON pointers use."""
        return enumerate(self.claim["lines"])

    @staticmethod
    def path(*parts: Any) -> str:
        """Build a JSON pointer into the claim.

        path("member_id")                  -> "/member_id"
        path("lines", 0, "service_date")   -> "/lines/0/service_date"
        path("coverage", "end_date")       -> "/coverage/end_date"

        Cite the field itself even when its value is None. Never cite a path
        that does not exist in the claim: make_result resolves every one.
        """
        return "/" + "/".join(str(p).replace("~", "~0").replace("/", "~1") for p in parts)
