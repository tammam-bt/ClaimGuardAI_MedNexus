"""claimguard._pack is the only door to the starter pack (ADR-001)."""
import pathlib
import re
import unittest

from claimguard import _pack

PACK_MODULES = ("engine_core", "evaluate", "llm_adapter", "audit", "schema_subset", "csv_to_jsonl")


class PackSeamTests(unittest.TestCase):
    def test_scorer_and_ai_seam_are_reexported(self):
        for name in ("index", "score", "ExplanationProvider", "MockExplanationProvider", "validate_explanation"):
            self.assertIn(name, _pack.__all__)
            self.assertTrue(hasattr(_pack, name), name)

    def test_scorer_comes_from_the_pack_file(self):
        self.assertTrue(pathlib.Path(_pack.score.__code__.co_filename).match("*/src/evaluate.py"))

    def test_confusion_uses_the_seam(self):
        from claimguard.evaluation import confusion
        self.assertIs(confusion.score, _pack.score)

    def test_no_module_outside_the_seam_imports_from_src(self):
        root = pathlib.Path(_pack.__file__).parent
        pattern = re.compile(rf"^\s*(from|import)\s+({'|'.join(PACK_MODULES)})\b", re.M)
        offenders = [str(p.relative_to(root)) for p in root.rglob("*.py")
                     if p.name != "_pack.py" and pattern.search(p.read_text(encoding="utf-8"))]
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
