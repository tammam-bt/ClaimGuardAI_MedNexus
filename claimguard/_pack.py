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
if not (_SRC / "engine_core.py").is_file():
    raise ImportError(
        f"starter pack not found at {_SRC}. claimguard must be installed "
        "editable from the repository root: uv pip install -e ."
    )
# Appended, not inserted first: src/ holds generic top-level names such as
# evaluate and audit, which would otherwise shadow installed packages of the
# same name (e.g. Hugging Face's evaluate) for the whole process.
if str(_SRC) not in sys.path:
    sys.path.append(str(_SRC))

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
