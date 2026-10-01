"""Role 5 — bounded AI: the explanation provider, output validation and the
watchdog that falls back to the deterministic explanation.

    records, events, summary = explain_run(results, claims, rules)

The model sees one minimized finding and its rule (minimize.py), never the
claim. Every answer passes the watchdog (watchdog.py) or is replaced by the
rule engine's own explanation. Explanations are written beside the scored
results, never into them.
"""
from .explainer import EXPLAINED, explain_run
from .minimize import build_messages, load_prompt, minimize
from .provider import DEFAULT_TIMEOUT_S, MockProvider, select_provider, timeout_from
from .watchdog import deterministic, explain_safely

__all__ = [
    "DEFAULT_TIMEOUT_S", "EXPLAINED", "MockProvider", "build_messages", "deterministic",
    "explain_run", "explain_safely", "load_prompt", "minimize", "select_provider", "timeout_from",
]
