"""The review interface: one self-contained HTML page built from a run's files.

    python -m claimguard.ui --results outputs/dev_predictions.jsonl \\
        --claims data/development/claims.jsonl

bundle.py gathers the data; static/ holds the page's HTML, CSS, JavaScript
and icons, which page.py inlines with the data into one file that opens
offline, with no server.
"""
from .bundle import BUNDLE_VERSION, build, embed
from .page import render

__all__ = ["BUNDLE_VERSION", "build", "embed", "render"]
