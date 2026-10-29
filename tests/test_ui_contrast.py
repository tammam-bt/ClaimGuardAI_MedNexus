"""Every text color of the interface meets WCAG AA (4.5:1) on its background,
in the light theme and in the dark one.

The pairs are the design tokens of claimguard/ui/static/app.css, read from
the file and resolved through the primitives, so changing a token re-runs the
check.
"""
import re
import unittest

from claimguard.ui.page import STATIC

# (text token, background token): every pair the components use for text.
SURFACES = ("--color-bg", "--color-surface", "--color-surface-raised", "--color-surface-muted", "--color-surface-strong")
PAIRS = [
    *[(t, b) for t in ("--color-text", "--color-text-muted", "--color-text-subtle") for b in SURFACES],
    *[("--color-link", b) for b in ("--color-surface", "--color-surface-raised", "--color-surface-muted")],
    ("--color-primary", "--color-surface-raised"), ("--color-primary", "--color-primary-subtle"),
    ("--color-on-primary", "--color-primary"), ("--color-on-primary", "--color-primary-hover"),
    ("--color-sidebar-text", "--color-sidebar"), ("--color-sidebar-text", "--color-sidebar-hover"),
    ("--color-sidebar-text-strong", "--color-sidebar"), ("--color-sidebar-text-strong", "--color-sidebar-hover"),
    *[(f"--color-{s}", f"--color-{s}-subtle") for s in ("success", "warning", "error", "info", "neutral")],
    *[(f"--color-{s}", "--color-surface-raised") for s in ("success", "warning", "error", "info")],
    ("--color-escalate", "--color-escalate-bg"), ("--color-review", "--color-review-bg"), ("--color-clear", "--color-clear-bg"),
    ("--color-severity-high", "--color-surface-raised"), ("--color-severity-medium", "--color-surface-raised"),
    # the selected finding in the workspace list, and claim fields a finding cites
    *[(t, "--color-primary-subtle") for t in ("--color-text", "--color-text-muted", "--color-success", "--color-info")],
]
# Non-text contrast (WCAG 1.4.11): 3:1 against what they sit on.
FOCUS_ON = ("--color-bg", "--color-surface", "--color-surface-raised", "--color-sidebar")
CHARTS = ("pass", "fail", "unknown", "neutral", "review", "clear")


def css():
    return (STATIC / "app.css").read_text(encoding="utf-8")


def block(text, opener):
    """The declarations of the first rule that starts with opener."""
    start = text.index(opener) + len(opener)
    return text[start:text.index("}", start)]


def declarations(body):
    return dict(re.findall(r"(--[a-z0-9-]+):\s*([^;]+);", body))


def dark_blocks(text):
    media = text[text.index("@media (prefers-color-scheme: dark)"):]
    return block(media, ':root:not([data-theme="light"]) {'), block(text, ':root[data-theme="dark"] {')


def theme(name):
    text = css()
    primitives = declarations(block(text, ":root {"))
    body = block(text, ':root,\n:root[data-theme="light"] {') if name == "light" else dark_blocks(text)[1]
    semantic = declarations(body)

    def resolve(value):
        m = re.fullmatch(r"var\((--[a-z0-9-]+)\)", value.strip())
        return resolve(primitives[m.group(1)]) if m else value.strip()
    return {k: resolve(v) for k, v in {**primitives, **semantic}.items()}


def luminance(hex_color):
    def channel(c):
        c = int(c, 16) / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (channel(hex_color[i:i + 2]) for i in (1, 3, 5))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


class ContrastTests(unittest.TestCase):
    def test_every_text_pair_meets_aa_in_both_themes(self):
        for name in ("light", "dark"):
            t = theme(name)
            for fg, bg in PAIRS:
                with self.subTest(theme=name, pair=(fg, bg)):
                    ratio = contrast(t[fg], t[bg])
                    self.assertGreaterEqual(ratio, 4.5, f"{name}: {fg} on {bg}: {ratio:.2f}:1")

    def test_focus_ring_is_visible_in_both_themes(self):
        for name in ("light", "dark"):
            t = theme(name)
            for bg in FOCUS_ON:
                with self.subTest(theme=name, bg=bg):
                    self.assertGreaterEqual(contrast(t["--color-focus-ring"], t[bg]), 3.0)

    def test_chart_fills_stand_out_from_their_track(self):
        for name in ("light", "dark"):
            t = theme(name)
            for chart in CHARTS:
                with self.subTest(theme=name, chart=chart):
                    self.assertGreaterEqual(contrast(t[f"--color-chart-{chart}"], t["--color-surface-strong"]), 3.0)

    def test_every_semantic_token_is_set_in_both_themes(self):
        text = css()
        light = set(declarations(block(text, ':root,\n:root[data-theme="light"] {')))
        for body in dark_blocks(text):
            self.assertEqual(set(declarations(body)), light)

    def test_the_two_dark_blocks_are_identical(self):
        # One for the system setting, one for the reviewer's choice: CSS
        # cannot share them, so this keeps them from drifting apart.
        media, chosen = (declarations(b) for b in dark_blocks(css()))
        self.assertEqual(media, chosen)


if __name__ == "__main__":
    unittest.main()
