"""Tests for the RBAC sketch (U6.6) and secrets hygiene (U6.7)."""
import copy
import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

from claimguard.guards.rbac import (
    PERMISSIONS, REVIEW_ACTIONS, PermissionDenied, allowed, authorize, authorize_event,
)

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = {"Reviewer 01": "reviewer", "Admin 01": "admin"}
EVENT = {"claim_id": "CG-785C09BD9CC8", "rule_id": "R003", "action": "confirm_issue",
         "actor": "Reviewer 01", "reason": "Coverage ended the day before the service.",
         "created_at": "2026-10-01T10:00:00Z", "original_status": "FAIL"}


class RbacTests(unittest.TestCase):
    def test_review_actions_match_the_schema(self):
        schema = json.loads((ROOT / "schemas" / "review_event.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(REVIEW_ACTIONS, set(schema["properties"]["action"]["enum"]))

    def test_both_roles_may_review(self):
        for role in ("reviewer", "admin"):
            for action in REVIEW_ACTIONS:
                self.assertTrue(allowed(role, action), (role, action))

    def test_admin_only_actions(self):
        for action in ("run_pipeline", "append_audit", "verify_audit", "view_run_events", "change_ai_settings"):
            self.assertFalse(allowed("reviewer", action), action)
            self.assertTrue(allowed("admin", action), action)
            with self.assertRaises(PermissionDenied):
                authorize(DIRECTORY, "Reviewer 01", action)
        self.assertEqual(authorize(DIRECTORY, "Admin 01", "verify_audit"), "admin")

    def test_unknown_role_action_or_actor_is_denied(self):
        self.assertFalse(allowed("superuser", "view_claim"))
        self.assertFalse(allowed("admin", "delete_audit"))
        for actor in ("Stranger", "", "   ", None):
            with self.assertRaises(PermissionDenied, msg=repr(actor)):
                authorize(DIRECTORY, actor, "view_claim")

    def test_a_valid_event_passes_unchanged(self):
        event = copy.deepcopy(EVENT)
        self.assertEqual(authorize_event(DIRECTORY, event), "reviewer")
        self.assertEqual(event, EVENT)

    def test_bad_events_are_denied(self):
        for change in ({"reason": "  "}, {"actor": "Stranger"}, {"action": "approve_claim"},
                       {"role": "admin"}):  # a role smuggled into the event is refused, not trusted
            with self.assertRaises(PermissionDenied, msg=change):
                authorize_event(DIRECTORY, {**EVENT, **change})

    def test_denial_never_quotes_the_input(self):
        with self.assertRaises(PermissionDenied) as ctx:
            authorize_event(DIRECTORY, {**EVENT, "actor": "MARKER-7F3A"})
        self.assertNotIn("MARKER-7F3A", str(ctx.exception))

    def test_roles_are_closed(self):
        self.assertEqual(set(PERMISSIONS), {"reviewer", "admin"})
        self.assertTrue(PERMISSIONS["reviewer"] < PERMISSIONS["admin"])


@unittest.skipUnless(shutil.which("git") and (ROOT / ".git").exists(), "needs a git checkout")
class SecretsTests(unittest.TestCase):
    def git(self, *args):
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)

    def test_env_is_ignored_but_the_example_is_not(self):
        # .gitignore is a pack file under SHA256SUMS.json, so it cannot be
        # widened without failing validate_pack.py. It ignores exactly .env,
        # which is why .env.example says to use that name only.
        for path in (".env", "outputs/run.jsonl"):
            self.assertEqual(self.git("check-ignore", "-q", path).returncode, 0, path)
        self.assertEqual(self.git("check-ignore", "-q", ".env.example").returncode, 1)

    def test_example_holds_no_value_for_the_key(self):
        text = (ROOT / ".env.example").read_text(encoding="utf-8")
        self.assertRegex(text, r"(?m)^ANTHROPIC_API_KEY=$")

    def test_no_secret_in_any_file_that_would_be_committed(self):
        # Tracked files plus untracked ones that are not ignored: what
        # `git add -A` would take. data/ is the pack's synthetic data.
        files = self.git("ls-files", "--cached", "--others", "--exclude-standard").stdout.splitlines()
        secret = re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----"
                            r"|ghp_[A-Za-z0-9]{30,}")
        hits = []
        for name in files:
            path = ROOT / name
            if name.startswith("data/") or not path.is_file() or path.stat().st_size > 2_000_000:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            if secret.search(text):
                hits.append(name)
        self.assertEqual(hits, [])


if __name__ == "__main__":
    unittest.main()
