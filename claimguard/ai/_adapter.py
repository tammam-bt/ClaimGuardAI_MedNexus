"""The pack's AI seam, src/llm_adapter.py, reached from one place only.

ADR-001: claimguard/_pack.py is the only module that imports from src/. It
does not re-export llm_adapter yet, and it is shared code we may not edit
alone. Until those three names are added there, this is the only file in
claimguard that imports llm_adapter. When they are, the import below becomes
`from claimguard._pack import ...` and nothing else moves.
"""
import claimguard._pack  # noqa: F401  (puts src/ on sys.path)
from llm_adapter import (  # noqa: E402
    ExplanationProvider,
    MockExplanationProvider,
    validate_explanation,
)

__all__ = ["ExplanationProvider", "MockExplanationProvider", "validate_explanation"]
