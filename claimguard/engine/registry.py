"""Rule registry.

A rule module registers itself with the @rule decorator; claimguard.rules
imports every module in its package on import, so nothing central lists them.

    @rule("R002")
    def check(ctx):
        ...
        return f.verdict("All service dates are on or before submission.")
"""
from typing import Callable, Dict

REGISTRY: Dict[str, Callable] = {}


def rule(rule_id: str):
    """Register a rule implementation under its rule ID (e.g. "R002")."""
    def register(fn: Callable) -> Callable:
        if rule_id in REGISTRY:
            raise RuntimeError(f"{rule_id} is already registered by {REGISTRY[rule_id]!r}")
        REGISTRY[rule_id] = fn
        return fn
    return register
