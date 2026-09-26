"""Policy resolution (U2.4).

A claim names its policy by policy_id. The lookup is exact and
case-sensitive, and there is no fallback: an unrecognised policy_id (the
data contains EDU-NO-POLICY) resolves to None. The rulebook is explicit that
this means "no matching policy was supplied, not proof of non-coverage", so
rules report UNABLE_TO_ASSESS for whatever they cannot check without it.

Policies are frozen on load. The same two policy objects are shared by every
claim in a run, so a rule that mutated one would silently change the answer
for every claim after it. Frozen, that mistake raises instead.
"""
from types import MappingProxyType
from typing import Any, Mapping, Optional


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({k: _freeze(v) for k, v in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(v) for v in value)
    return value


class PolicyBook:
    """Read-only policies keyed by policy_id, built once per run."""

    def __init__(self, policies: Mapping[str, Mapping[str, Any]]):
        for key, policy in policies.items():
            if policy.get("policy_id") != key:
                raise ValueError(f"policies.json key {key!r} holds policy_id {policy.get('policy_id')!r}")
        self._policies = {key: _freeze(policy) for key, policy in policies.items()}

    def resolve(self, policy_id: str) -> Optional[Mapping[str, Any]]:
        """The policy for this exact policy_id, or None. Never trims or folds case."""
        return self._policies.get(policy_id)

    def __contains__(self, policy_id: object) -> bool:
        return policy_id in self._policies
