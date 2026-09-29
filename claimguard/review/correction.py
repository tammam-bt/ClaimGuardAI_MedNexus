"""U5.6 | Correction -> new version -> recheck (DEC-011).

    v1 = original(claim)                                    # immutable, hashed
    run = recheck(v1, [{"op": "replace", "path": "/total_amount", "value": 2350}],
                  actor="reviewer-1", reason="Total re-read from the source bill.",
                  engine=rule_engine())
    run.version          # v2, linked to v1 by parent_hash
    run.status_changes   # [{"rule_id": "R012", "before": "FAIL", "after": "PASS"}]

The original is never edited and results are never patched: a correction
creates a new version, and all 15 rules re-run on it. The version lives beside
the claim, not in it, because validate_transport() rejects any extra key.

Stand-ins until Role 1 ships its units (DEC-011):
  rule_engine()  runs the registered rules until the runner (U2.6) exists;
  input_hash     hashes canonical JSON, not the original file bytes (U1.5);
  record()       is returned for the audit trail, not written to it: the pack's
                 audit.append() accepts only the four review actions (U4.4).
"""
import copy
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

import claimguard.rules  # noqa: F401  registers every rule module
from claimguard._pack import config, make_result, validate_transport
from claimguard.engine.context import RuleContext
from claimguard.engine.policy import PolicyBook
from claimguard.engine.registry import REGISTRY

Engine = Callable[[Mapping[str, Any]], List[Dict[str, Any]]]

_INDEX = re.compile(r"^(0|[1-9][0-9]*)$")
_IDENTIFIERS = re.compile(r"^/(claim_id|schema_version|lines/(0|[1-9][0-9]*)/line_id)$")


def _canonical(claim: Mapping[str, Any]) -> str:
    return json.dumps(claim, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


@dataclass(frozen=True)
class ClaimVersion:
    """One immutable version of a claim. The claim is stored as canonical JSON,
    so nothing handed out can change it: .claim returns a fresh copy."""

    claim_id: str
    version: int
    input_hash: str
    parent_hash: Optional[str]
    actor: Optional[str]
    reason: Optional[str]
    _changes: str
    _claim: str

    @property
    def claim(self) -> Dict[str, Any]:
        return json.loads(self._claim)

    @property
    def changes(self) -> Tuple[Dict[str, Any], ...]:
        return tuple(json.loads(self._changes))

    def record(self) -> Dict[str, Any]:
        """The lineage entry for this version (U4.5), without the claim itself."""
        return {"claim_id": self.claim_id, "version": self.version, "input_hash": self.input_hash,
                "parent_hash": self.parent_hash, "actor": self.actor, "reason": self.reason,
                "changes": list(self.changes)}


def _version(claim: Mapping[str, Any], number: int, parent: Optional[ClaimVersion],
             actor: Optional[str], reason: Optional[str], changes: Sequence[Mapping[str, Any]]) -> ClaimVersion:
    text = _canonical(claim)
    return ClaimVersion(claim["claim_id"], number, hashlib.sha256(text.encode()).hexdigest(),
                        parent.input_hash if parent else None, actor, reason, json.dumps(list(changes)), text)


def original(claim: Mapping[str, Any]) -> ClaimVersion:
    """Version 1: the claim as received. Raises ValueError if its envelope is invalid."""
    validate_transport(claim)
    return _version(claim, 1, None, None, None, ())


def _locate(doc: Any, path: str) -> Tuple[Any, str]:
    """(container, last token) for a strict RFC 6901 pointer. Raises ValueError."""
    if not isinstance(path, str) or not path.startswith("/"):
        raise ValueError(f"{path!r} is not a JSON pointer into the claim")
    *parents, last = [p.replace("~1", "/").replace("~0", "~") for p in path[1:].split("/")]
    for token in parents:
        if isinstance(doc, list) and _INDEX.match(token) and int(token) < len(doc):
            doc = doc[int(token)]
        elif isinstance(doc, dict) and token in doc:
            doc = doc[token]
        else:
            raise ValueError(f"{path}: no such location")
    return doc, last


def _apply(claim: Dict[str, Any], op: Mapping[str, Any]) -> None:
    """Apply one operation in place: replace a value, add into an array, remove from an array."""
    kind, path = op.get("op"), op.get("path")
    if kind not in ("replace", "add", "remove"):
        raise ValueError(f"unsupported operation {kind!r}; use replace, add or remove")
    if isinstance(path, str) and _IDENTIFIERS.match(path):
        raise ValueError(f"{path} cannot be corrected: a different claim or line is a new submission")
    if kind != "remove" and "value" not in op:
        raise ValueError(f"{kind} {path} needs a value")
    parent, last = _locate(claim, path)

    if isinstance(parent, list):
        if kind == "add" and last == "-":
            parent.append(copy.deepcopy(op["value"]))
            return
        if not _INDEX.match(last) or int(last) > len(parent) or (kind != "add" and int(last) == len(parent)):
            raise ValueError(f"{path}: no such array position")
        i = int(last)
        if kind == "add":
            parent.insert(i, copy.deepcopy(op["value"]))
        elif kind == "remove":
            del parent[i]
        else:
            _replace(parent, i, op["value"], path)
        return
    if not isinstance(parent, dict) or last not in parent:
        raise ValueError(f"{path}: no such field")
    if kind != "replace":
        # validate_transport requires every key; a missing value is null, not an absent key.
        raise ValueError(f"{path}: fields can only be replaced (use null for a missing value)")
    _replace(parent, last, op["value"], path)


def _replace(parent: Any, key: Any, value: Any, path: str) -> None:
    """A correction changes values, never shapes, so every change is itemised in the lineage."""
    old = parent[key]
    if isinstance(old, list):
        raise ValueError(f"{path}: replace array items one by one, or add / remove them")
    if isinstance(old, dict):
        if not isinstance(value, dict) or set(value) != set(old):
            raise ValueError(f"{path}: a replaced object must keep its keys")
        if "line_id" in old and value["line_id"] != old["line_id"]:
            raise ValueError(f"{path}/line_id cannot be corrected: a different line is a new line")
    parent[key] = copy.deepcopy(value)


def correct(parent: ClaimVersion, changes: Sequence[Mapping[str, Any]], *, actor: str, reason: str) -> ClaimVersion:
    """The next version: parent's claim with changes applied, all or nothing.

    Raises ValueError, creating no version, for a blank actor or reason
    (docs/10), a correction that changes nothing (a decision alone cannot
    change a result), an invalid operation, or a result that fails the
    transport contract (an ingestion error, never a version).
    """
    for name, value in (("actor", actor), ("reason", reason)):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"a correction needs a non-blank {name}")
    claim = parent.claim
    for op in changes:
        if not isinstance(op, Mapping):
            raise ValueError(f"not an operation: {op!r}")
        _apply(claim, op)
    if _canonical(claim) == parent._claim:
        raise ValueError("this correction changes nothing; only corrected data can change a result")
    try:
        validate_transport(claim)
    except ValueError as e:
        raise ValueError(f"corrected claim is invalid: {e}") from None
    return _version(claim, parent.version + 1, parent, actor, reason, changes)


def rule_engine(root: Optional[str] = None) -> Engine:
    """All 15 results for a claim, in rules.json order, from the registered rules.

    Stand-in for Role 1's runner (U2.6): an unregistered rule reports
    NOT_IMPLEMENTED, never PASS. prior carries earlier results, as
    RuleContext documents.
    """
    cfg = config(root or Path(__file__).resolve().parents[2])
    book = PolicyBook(cfg["policies"])

    def run(claim: Mapping[str, Any]) -> List[Dict[str, Any]]:
        prior: Dict[str, Dict[str, Any]] = {}
        for rule in cfg["rules"]:
            fn = REGISTRY.get(rule["rule_id"])
            if fn is None:
                result = make_result(claim, rule, "NOT_IMPLEMENTED", [], "Student implementation required.")
            else:
                v = fn(RuleContext(claim, rule, book.resolve(claim["policy_id"]), cfg["services"], dict(prior)))
                result = make_result(claim, rule, v.status, v.paths, v.message, list(v.line_ids))
            prior[rule["rule_id"]] = result
        return list(prior.values())
    return run


@dataclass(frozen=True)
class Recheck:
    version: ClaimVersion
    results: List[Dict[str, Any]]
    previous_results: List[Dict[str, Any]]
    status_changes: List[Dict[str, str]]


def recheck(parent: ClaimVersion, changes: Sequence[Mapping[str, Any]], *, actor: str, reason: str,
            engine: Engine) -> Recheck:
    """Correct, then re-run every rule on the new version and report what moved."""
    version = correct(parent, changes, actor=actor, reason=reason)
    before, after = engine(parent.claim), engine(version.claim)
    was = {r["rule_id"]: r["status"] for r in before}
    moved = [{"rule_id": r["rule_id"], "before": was[r["rule_id"]], "after": r["status"]}
             for r in after if was.get(r["rule_id"]) != r["status"]]
    return Recheck(version, after, before, moved)
