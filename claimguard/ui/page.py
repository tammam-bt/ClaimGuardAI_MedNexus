"""Inline the page's static files and a run's data into one HTML file.

static/index.html holds four markers, each exactly once: the stylesheet,
the icon sprite, the data, and the script. Data goes in a
<script type="application/json"> element, read with JSON.parse, never run.

The script is the files of JS_FILES joined in this order, in one <script>:
core.js (pure logic, also tested in Node), ui.js (shared components, shell,
router), one file per page, then main.js, which starts the app. Pages only
assemble ui.js components, which is what keeps every page consistent.
"""
from pathlib import Path

from .bundle import embed

STATIC = Path(__file__).resolve().parent / "static"
JS_FILES = (
    "core.js",
    "ui.js",
    "page-dashboard.js",
    "page-queue.js",
    "page-claims.js",
    "page-audit.js",
    "page-rules.js",
    "page-evaluation.js",
    "page-settings.js",
    "page-components.js",
    "main.js",
)
_MARKERS = ("/*@CSS@*/", "<!--@ICONS@-->", "@DATA@", "/*@JS@*/")
# The page's policy sends nothing anywhere. Served by claimguard.ui.serve, it
# may talk to that server and nothing else: connect-src 'self' is the only
# difference, and the file written by python -m claimguard.ui never has it.
OFFLINE_POLICY = "img-src data:; base-uri 'none'"
SERVED_POLICY = "img-src data:; connect-src 'self'; base-uri 'none'"


def _static(name):
    return (STATIC / name).read_text(encoding="utf-8")


def script():
    return "\n;\n".join(f"// ---- {name}\n{_static(name)}" for name in JS_FILES)


def render(data, *, served=False):
    template = _static("index.html")
    for marker in _MARKERS + (OFFLINE_POLICY,):
        if template.count(marker) != 1:
            raise RuntimeError(f"static/index.html must contain {marker} exactly once")
    if served:
        template = template.replace(OFFLINE_POLICY, SERVED_POLICY)
    parts = {
        "/*@CSS@*/": _static("app.css"),
        "<!--@ICONS@-->": _static("icons.svg"),
        "@DATA@": embed(data),
        "/*@JS@*/": script(),
    }
    # Cut the template at its markers first, then join: inserted text is never
    # searched again, so a marker string inside a claim cannot be replaced.
    order = sorted(_MARKERS, key=template.index)
    out, rest = [], template
    for marker in order:
        head, rest = rest.split(marker, 1)
        out += [head, parts[marker]]
    return "".join(out + [rest])
