"""Which ExplanationProvider a run uses (U2.7).

Any object with explain(finding, rule) and the attributes name and model is
a provider. explain() receives the minimized finding and rule (minimize.py)
and returns either the four-key dict or the model's raw JSON text; the
watchdog parses and validates both.

Only the mock exists today. The live model, its access and its client
library are a team decision still to be made, so a run with
ANTHROPIC_API_KEY set still uses the mock and says why. A clean checkout
needs no key, network or package. The key itself is never read here beyond
checking that it is present, and never logged.
"""
import os

from claimguard._pack import MockExplanationProvider

DEFAULT_TIMEOUT_S = 20.0


class MockProvider(MockExplanationProvider):
    """The pack's mock: returns the rule engine's own explanation."""
    name = "mock"
    model = None


def select_provider(env=None):
    """(provider, reason). reason says why this provider was chosen."""
    env = os.environ if env is None else env
    if env.get("ANTHROPIC_API_KEY"):
        return MockProvider(), "ANTHROPIC_API_KEY is set, but no live provider is wired yet; using the mock"
    return MockProvider(), "no ANTHROPIC_API_KEY; using the mock"


def timeout_from(env=None):
    """CLAIMGUARD_AI_TIMEOUT_S, or the default. A bad value is an error, not a
    silent default, so a run never uses a timeout nobody chose."""
    env = os.environ if env is None else env
    raw = env.get("CLAIMGUARD_AI_TIMEOUT_S")
    if raw is None:
        return DEFAULT_TIMEOUT_S
    value = float(raw)
    if not 0 < value <= 300:
        raise ValueError("CLAIMGUARD_AI_TIMEOUT_S must be between 0 and 300 seconds")
    return value
