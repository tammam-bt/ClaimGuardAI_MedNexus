"""Rule registry.

A rule module registers itself with the @rule decorator; claimguard.rules
imports every module in its package on import, so nothing central lists them.

    @rule("R002")
    def check(ctx):
        ...
        return f.verdict("All service dates are on or before submission.")
"""
import re
from typing import Callable, Dict

_RULE_ID = re.compile(r"^R\d{3}$")

REGISTRY: Dict[str, Callable] = {}


def rule(rule_id: str):
    """Register a rule implementation under its rule ID (e.g. "R002")."""
    if not _RULE_ID.match(rule_id):
        raise ValueError(f"rule ID must look like R002, got {rule_id!r}")

    def register(fn: Callable) -> Callable:
        if rule_id in REGISTRY:
            raise RuntimeError(f"{rule_id} is already registered by {REGISTRY[rule_id]!r}")
        REGISTRY[rule_id] = fn
        return fn
    return register
