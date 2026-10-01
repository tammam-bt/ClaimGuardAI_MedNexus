"""Role 5 — security guards around untrusted claim text and the AI boundary.

A guard never changes a claim or a rule result. It reports; the caller decides
what the report keeps away from the model or shows to a reviewer.
"""
from .injection import SCANNER_VERSION, Hit, Screening, screen

__all__ = ["SCANNER_VERSION", "Hit", "Screening", "screen"]
