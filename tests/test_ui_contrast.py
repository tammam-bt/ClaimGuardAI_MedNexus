"""Every text color of the interface meets WCAG AA (4.5:1) on its background.

The pairs are the design tokens of claimguard/ui/static/app.css, read from
the file, so changing a token re-runs the check.
"""
import re
import unittest

from claimguard.ui.page import STATIC

# (text token, background token): every pair the components use for text.
PAIRS = [
    *[(t, b) for t in ("--text", "--text-2", "--text-3") for b in ("--surface", "--bg", "--surface-2", "--surface-3")],
    ("--primary", "--surface"), ("--primary", "--primary-soft"), ("--text-inverse", "--primary"), ("--text-inverse", "--primary-hover"),
    ("--sidebar-text", "--sidebar"), ("--sidebar-text", "--sidebar-2"), ("--sidebar-text-strong", "--sidebar"),
    ("--pass", "--pass-bg"), ("--fail", "--fail-bg"), ("--unknown", "--unknown-bg"), ("--neutral", "--neutral-bg"),
    ("--info", "--info-bg"), ("--escalate", "--escalate-bg"), ("--review", "--review-bg"), ("--clear", "--clear-bg"),
]


def tokens():
    css = (STATIC / "app.css").read_text(encoding="utf-8")
    root = css[css.index(":root"):css.index("}", css.index(":root"))]
    return dict(re.findall(r"(--[a-z0-9-]+):\s*(#[0-9A-Fa-f]{6})\b", root))


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
    def test_every_text_pair_meets_aa(self):
        t = tokens()
        for fg, bg in PAIRS:
            ratio = contrast(t[fg], t[bg])
            self.assertGreaterEqual(ratio, 4.5, f"{fg} on {bg}: {ratio:.2f}:1")

    def test_focus_ring_is_visible(self):
        # Non-text contrast (WCAG 1.4.11): 3:1 against the surfaces it sits on.
        t = tokens()
        for bg in ("--surface", "--bg", "--sidebar"):
            self.assertGreaterEqual(contrast(t["--focus"], t[bg]), 3.0, bg)


if __name__ == "__main__":
    unittest.main()
