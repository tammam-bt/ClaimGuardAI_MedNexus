"""The single seam to the unmodified starter pack in src/.

src/ is a flat directory of modules, not a package, so it only imports when it
is on sys.path. Rather than repeat that path insertion everywhere (as
tests/test_baseline.py does), it happens once, here. No other module in this
package imports from src directly.

Keep the pack's helpers authoritative:
  make_result  builds a schema-valid result and resolves every evidence pointer
               against the claim, so evidence values can never be fabricated.
  money        Decimal(str(v)) quantized to 2dp, ROUND_HALF_UP.
  valid_date   ISO string -> date, or None. Never raises.
  empty        None or whitespace-only string. Note empty(0) is False.
"""
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from engine_core import (  # noqa: E402
    STATUSES,
    config,
    empty,
    load_jsonl,
    make_result,
    money,
    pointer,
    valid_date,
    validate_transport,
)

__all__ = [
    "STATUSES", "config", "empty", "load_jsonl", "make_result",
    "money", "pointer", "valid_date", "validate_transport",
]
