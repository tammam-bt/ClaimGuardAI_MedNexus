"""What leaves the engine (Phase 2: data minimization, prompt/data security).

An end-to-end run on the development claims, with an API key in the
environment, an audit log, explanations and the review page, then a scan of
every file the run wrote:

  - the key appears nowhere (doc 10: "Do not put API keys in prompts, code,
    screenshots or audit logs");
  - no claim's notes or document text appears in the manifest, the
    explanations, the audit log or its anchor: they record fixed text, field
    names and exception types only;
  - in the scored results, document text appears only inside R010's evidence,
    which cites the whole attachments array as the pack's result contract and
    gold require; notes appear nowhere, since no rule reads them;
  - the review page carries document text only as evidence and claim data,
    for the reviewer to inspect (escaping is tested in test_ui_bundle.py and
    test_ui_e2e.py).

The model's view is tested in test_ai.py (test_model_never_sees_the_claim_id_or_free_text).
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from claimguard._pack import load_jsonl

ROOT = Path(__file__).resolve().parents[1]
DEV = ROOT / "data" / "development"
# Built at runtime so the repository's own secret scan never matches this file.
FAKE_KEY = "sk-" + "ant-" + "privacytest" + "0" * 24
MIN_TEXT = 12  # shorter strings are codes and dates that legitimately repeat


def free_texts(claims):
    """(notes, document texts) of the claims: the untrusted free text."""
    notes = {c["notes"] for c in claims if isinstance(c.get("notes"), str) and len(c["notes"]) >= MIN_TEXT}
    docs = {a["text"] for c in claims for a in c["attachments"]
            if isinstance(a.get("text"), str) and len(a["text"]) >= MIN_TEXT}
    return notes, docs


class PrivacyRunTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        out = Path(cls._tmp.name)
        cls.results, cls.log = out / "pred.jsonl", out / "audit.jsonl"
        cls.page = out / "page.html"
        env = {**os.environ, "ANTHROPIC_API_KEY": FAKE_KEY}
        for args in (["claimguard.run", "--input", DEV / "claims.jsonl", "--output", cls.results, "--explain",
                      "--audit-log", cls.log],
                     ["claimguard.ui", "--results", cls.results, "--claims", DEV / "claims.jsonl",
                      "--audit-log", cls.log, "--output", cls.page]):
            done = subprocess.run([sys.executable, "-m", *map(str, args)], cwd=ROOT, env=env,
                                  capture_output=True, text=True, encoding="utf-8")
            assert done.returncode == 0, done.stderr
            cls.printed = getattr(cls, "printed", "") + done.stdout + done.stderr
        cls.files = {p.name: p.read_text(encoding="utf-8") for p in out.iterdir() if p.is_file()}
        cls.notes, cls.docs = free_texts(load_jsonl(DEV / "claims.jsonl"))

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_the_run_wrote_what_is_scanned(self):
        self.assertEqual(set(self.files), {"pred.jsonl", "pred.jsonl.manifest.json", "pred.jsonl.explanations.jsonl",
                                           "audit.jsonl", "audit.head.json", "page.html"})
        self.assertTrue(self.notes and self.docs)  # the scan has something to find

    def test_the_key_is_written_nowhere(self):
        for name, text in self.files.items():
            self.assertNotIn(FAKE_KEY, text, name)
        self.assertNotIn(FAKE_KEY, self.printed)

    def test_records_never_quote_free_text(self):
        for name in ("pred.jsonl.manifest.json", "pred.jsonl.explanations.jsonl", "audit.jsonl", "audit.head.json"):
            text = self.files[name]
            with self.subTest(file=name):
                self.assertEqual([t for t in self.notes | self.docs if t in text], [])

    def test_results_quote_document_text_only_as_r010_evidence(self):
        for r in load_jsonl(self.results):
            for e in r["evidence"]:
                value = json.dumps(e["value"], ensure_ascii=False)
                self.assertFalse(any(t in value for t in self.notes), (r["claim_id"], r["rule_id"], e["path"]))
                if any(t in value for t in self.docs):
                    self.assertEqual((r["rule_id"], e["path"]), ("R010", "/attachments"))

    def test_notes_never_reach_the_page_outside_the_claim(self):
        # The page shows each claim as received (notes included) for the
        # reviewer; what it must not do is copy notes into results or logs.
        page = self.files["page.html"]
        self.assertTrue(any(t in page for t in self.notes))  # the claim itself is shown
        for name in ("pred.jsonl", "audit.jsonl"):
            self.assertEqual([t for t in self.notes if t in self.files[name]], [], name)


class NoteCitesRealTestsTests(unittest.TestCase):
    """docs/PRIVACY_SECURITY.md proves each control by naming a test. A name
    that no longer exists would make the deliverable claim proof it lacks."""

    def test_every_cited_test_exists(self):
        note = (ROOT / "docs" / "PRIVACY_SECURITY.md").read_text(encoding="utf-8")
        sources = {p.stem: p.read_text(encoding="utf-8") for p in (ROOT / "tests").glob("test_*.py")}
        everything = "\n".join(sources.values())
        cited = re.findall(r"`(test_[a-z0-9_]+)(?:\.([A-Za-z_][A-Za-z0-9_]*))?`", note)
        self.assertGreater(len(cited), 30)
        missing = []
        for first, second in cited:
            if second:  # module.test_function or module.ClassName
                found = first in sources and re.search(rf"(def|class) {second}\b", sources[first])
            else:       # a module, or a test function named after its module elsewhere in the row
                found = first in sources or re.search(rf"def {first}\b", everything)
            if not found:
                missing.append(f"{first}.{second}" if second else first)
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
