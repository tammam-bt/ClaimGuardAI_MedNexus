"""Tests for the local review server (claimguard.ui.serve and
claimguard.ui.signin, Track C): every check in docs/THREAT_MODEL.md refuses
what it should, nothing refused reaches the audit log, and a decision saved
through the server gives the same gate result as the command line."""
import contextlib
import hashlib
import http.client
import io
import json
import re
import shutil
import socket
import tempfile
import threading
import unittest
from collections import Counter
from pathlib import Path
from unittest import mock

from claimguard._pack import load_jsonl
from claimguard.audit import chain
from claimguard.review.correction import original
from claimguard.review.gate import judge
from claimguard.run import main as run_main
from claimguard.ui import build, render
from claimguard.ui.decisions import main as decisions_main
from claimguard.ui.serve import MAX_BODY, App, Run, main as serve_main, make_server
from claimguard.ui.signin import SignIn, hash_password, load_users, main as signin_main, set_password

ROOT = Path(__file__).resolve().parents[1]
DEV = ROOT / "data" / "development"
CLAIM = "CG-785C09BD9CC8"      # R003 and R004 FAIL
TO_CORRECT = "CG-B39790AC3604"  # R008 FAIL until its authorization is added
FIX = [{"op": "replace", "path": "/lines/0/authorization_id", "value": "AUTH-CG-B39790AC3604-1"}]
DIRECTORY = {"Reviewer 01": "reviewer", "Reviewer 02": "reviewer", "Admin 01": "admin"}
PASSWORD = "correct horse battery"


def page_data(html):
    return json.loads(re.search(r'<script type="application/json" id="claimguard-data">(.*?)</script>', html, re.S).group(1))


def policy(html):
    return re.search(r'<meta http-equiv="Content-Security-Policy" content="([^"]+)">', html).group(1)


class ServerCase(unittest.TestCase):
    """A real run once; a fresh copy of its audit log and a server per test."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls._tmp.cleanup)
        cls.base = Path(cls._tmp.name)
        cls.results = cls.base / "pred.jsonl"
        cls.run_log = cls.base / "audit.jsonl"
        with contextlib.redirect_stdout(io.StringIO()):
            run_main(["--input", str(DEV / "claims.jsonl"), "--output", str(cls.results), "--audit-log", str(cls.run_log)])
        claims = {c["claim_id"]: c for c in load_jsonl(DEV / "claims.jsonl")}
        cls.hash = original(claims[CLAIM]).input_hash
        cls.fix_parent = original(claims[TO_CORRECT]).input_hash

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(dir=self.base))
        self.log = self.copy_log("audit")
        self.corrections = self.dir / "corrections"

    def copy_log(self, name):
        log = self.dir / f"{name}.jsonl"
        shutil.copy(self.run_log, log)
        shutil.copy(chain.default_anchor(self.run_log), chain.default_anchor(log))
        return log

    def start(self, *, corrections=True, signin=None, expect=None, log=None):
        log = log or self.log
        self.app = App(Run(str(self.results), str(DEV / "claims.jsonl"), str(log), chain.default_anchor(log), DIRECTORY,
                           str(self.corrections) if corrections else None, None, expect), signin=signin, quiet=True)
        self.server = make_server(self.app, 0)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.host = f"127.0.0.1:{self.app.port}"
        self.session = None
        return self.app

    def request(self, method, path, body=None, *, token=True, origin=True, headers=None):
        """(status, headers, body bytes). By default, as the server's own page sends it."""
        h = {}
        if token:
            h["X-ClaimGuard-Token"] = self.app.token if token is True else token
        if origin and method == "POST":
            h["Origin"] = f"http://{self.host}" if origin is True else origin
        if body is not None and not isinstance(body, bytes):
            body = json.dumps(body).encode()
            h["Content-Type"] = "application/json"
        if self.session:
            h["Cookie"] = f"{self.app.cookie('session')}={self.session}"
        h.update(headers or {})
        conn = http.client.HTTPConnection("127.0.0.1", self.app.port, timeout=30)
        try:
            conn.request(method, path, body=body, headers=h)
            res = conn.getresponse()
            return res.status, res.headers, res.read()
        finally:
            conn.close()

    def api(self, method, path, body=None, **kw):
        code, _, raw = self.request(method, path, body, **kw)
        return code, json.loads(raw)

    def page(self, **headers):
        return self.request("GET", "/", token=False, headers={"Cookie": f"{self.app.cookie('launch')}={self.app.token}", **headers})

    def decisions(self, actor="Reviewer 01", **changes):
        return [{"event": "review_decision", "claim_id": CLAIM, "rule_id": rule, "action": "dismiss_with_reason",
                 "actor": actor, "reason": "Checked at the source.", "created_at": "2026-10-28T10:00:00Z",
                 "original_status": "FAIL", "input_hash": self.hash, **changes} for rule in ("R003", "R004")]

    def correction(self, **changes):
        return {"claim_id": TO_CORRECT, "parent_hash": self.fix_parent, "changes": FIX, "actor": "Reviewer 01",
                "reason": "Authorization added from the source record.", **changes}

    def log_bytes(self):
        return self.log.read_bytes()


class AccessTests(ServerCase):
    """T1 to T5 and T10: who can reach the server and with what."""

    def setUp(self):
        super().setUp()
        self.start()

    def test_bound_to_this_machine_only(self):
        self.assertEqual(self.server.server_address[0], "127.0.0.1")
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            serve_main(["--host", "0.0.0.0"])  # there is no such option

    def test_page_needs_the_token(self):
        code, _, body = self.request("GET", "/", token=False)
        self.assertEqual(code, 403)
        self.assertNotIn(CLAIM.encode(), body)
        code, _, _ = self.request("GET", "/?token=wrong", token=False)
        self.assertEqual(code, 403)
        code, _, _ = self.request("GET", "/", token=False, headers={"Cookie": f"{self.app.cookie('launch')}=wrong"})
        self.assertEqual(code, 403)

    def test_token_moves_to_a_cookie(self):
        code, headers, _ = self.request("GET", f"/?token={self.app.token}", token=False)
        self.assertEqual(code, 303)
        self.assertEqual(headers["Location"], "/")
        cookie = headers["Set-Cookie"]
        self.assertTrue(cookie.startswith(f"{self.app.cookie('launch')}={self.app.token};"))
        for flag in ("HttpOnly", "SameSite=Strict", "Path=/"):
            self.assertIn(flag, cookie)
        code, headers, body = self.page()
        self.assertEqual(code, 200)
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(headers["Referrer-Policy"], "no-referrer")
        self.assertEqual(headers["X-Frame-Options"], "DENY")
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
        self.assertIsNone(headers["Access-Control-Allow-Origin"])

    def test_cookie_names_hold_the_port(self):
        # Cookies are shared by every port of 127.0.0.1: two servers must not overwrite each other's.
        self.assertIn(str(self.app.port), self.app.cookie("launch"))

    def test_served_page_policy(self):
        html = self.page()[2].decode()
        served = policy(html)
        self.assertIn("default-src 'none'", served)
        self.assertIn("connect-src 'self'", served)
        self.assertEqual(page_data(html)["server"], {"token": self.app.token})
        # The file python -m claimguard.ui writes is unchanged: no server, no connection.
        offline = render(build(self.results, DEV / "claims.jsonl", audit_log=self.log))
        self.assertNotIn("connect-src", policy(offline))
        self.assertNotIn("server", page_data(offline))
        self.assertEqual(served.replace("connect-src 'self'; ", ""), policy(offline))

    def test_wrong_host_is_refused(self):
        cookie = {"Cookie": f"{self.app.cookie('launch')}={self.app.token}"}
        for host in ("evil.example", f"evil.example:{self.app.port}", f"127.0.0.1:{self.app.port + 1}", "127.0.0.1"):
            code, _, _ = self.request("GET", "/", token=False, headers={"Host": host, **cookie})
            self.assertEqual(code, 403, host)
            code, _ = self.api("GET", "/api/status", headers={"Host": host})
            self.assertEqual(code, 403, host)
        self.assertEqual(self.page(Host=f"localhost:{self.app.port}")[0], 200)

    def test_api_refuses_a_missing_or_wrong_token(self):
        for token in (False, "wrong", self.app.token[:-1]):
            self.assertEqual(self.api("GET", "/api/status", token=token)[0], 403)
            self.assertEqual(self.api("POST", "/api/decisions", {"decisions": self.decisions()}, token=token)[0], 403)
        # The launch cookie alone opens the page, never the API.
        code, _ = self.api("GET", "/api/status", token=False, headers={"Cookie": f"{self.app.cookie('launch')}={self.app.token}"})
        self.assertEqual(code, 403)
        self.assertEqual(self.log_bytes(), self.run_log.read_bytes())

    def test_api_refuses_another_origin(self):
        before = self.log_bytes()
        for origin in ("http://evil.example", f"http://localhost:{self.app.port}", "null", False):
            code, _ = self.api("POST", "/api/decisions", {"decisions": self.decisions()}, origin=origin)
            self.assertEqual(code, 403, origin)
        code, _ = self.api("POST", "/api/decisions", {"decisions": self.decisions()}, headers={"Sec-Fetch-Site": "cross-site"})
        self.assertEqual(code, 403)
        self.assertEqual(self.log_bytes(), before)

    def test_api_takes_json_only(self):
        # A form or text/plain post needs no preflight from another site: refused.
        for kind in ("text/plain", "application/x-www-form-urlencoded", "multipart/form-data"):
            code, _ = self.api("POST", "/api/decisions", json.dumps({"decisions": self.decisions()}).encode(),
                               headers={"Content-Type": kind})
            self.assertEqual(code, 415, kind)
        for raw in (b"not json", b"[1, 2]", b"\xff\xfe", b"[" * 200000):  # the last nests too deep to parse
            code, _ = self.api("POST", "/api/decisions", raw, headers={"Content-Type": "application/json"})
            self.assertEqual(code, 400, raw)
        self.assertEqual(self.log_bytes(), self.run_log.read_bytes())

    def raw_post(self, headers):
        """The status line of a POST whose headers are sent as given, with no
        body: the server must answer from the headers alone."""
        with socket.create_connection(("127.0.0.1", self.app.port), timeout=30) as s:
            s.sendall((f"POST /api/decisions HTTP/1.1\r\nHost: {self.host}\r\nOrigin: http://{self.host}\r\n"
                       f"X-ClaimGuard-Token: {self.app.token}\r\nContent-Type: application/json\r\n"
                       + "".join(f"{k}: {v}\r\n" for k, v in headers.items()) + "\r\n").encode())
            return s.recv(4096).split(b"\r\n")[0].decode()

    def test_oversized_body_is_refused(self):
        # Refused from the header, before a byte of the body is read.
        self.assertIn(" 413 ", self.raw_post({"Content-Length": MAX_BODY + 1}))
        self.assertIn(" 411 ", self.raw_post({}))
        self.assertIn(" 411 ", self.raw_post({"Content-Length": "lots"}))

    def test_a_chunked_body_is_refused(self):
        self.assertIn(" 411 ", self.raw_post({"Transfer-Encoding": "chunked"}))

    def test_unknown_paths_and_methods(self):
        self.assertEqual(self.api("GET", "/api/nothing")[0], 404)
        self.assertEqual(self.api("POST", "/api/signin", {"name": "x", "password": "y"})[0], 404)  # no --users
        self.assertEqual(self.request("PUT", "/api/decisions", b"{}")[0], 501)

    def test_status_reports_the_verified_head(self):
        code, status = self.api("GET", "/api/status")
        head, count = chain.verify(self.log, chain.default_anchor(self.log))
        self.assertEqual(code, 200)
        self.assertEqual(status["audit"], {"valid": True, "count": count, "head": head})
        self.assertEqual((status["signin"], status["corrections"]), (None, True))

    def test_status_reports_a_broken_chain(self):
        self.log.write_text(self.log.read_text(encoding="utf-8").replace('"accepted": ', '"accepted": 1', 1), encoding="utf-8")
        status = self.api("GET", "/api/status")[1]
        self.assertFalse(status["audit"]["valid"])
        self.assertIn("invalid", status["audit"]["error"])


class DecisionTests(ServerCase):
    """B2: saving decisions from the page."""

    def setUp(self):
        super().setUp()
        self.start()

    def test_saved_like_the_command_line(self):
        body = {"decisions": self.decisions()}
        code, answer = self.api("POST", "/api/decisions", body)
        self.assertEqual(code, 200, answer)
        self.assertEqual((answer["appended"], answer["already_in_chain"]), (2, 0))
        head, count = chain.verify(self.log, chain.default_anchor(self.log))
        self.assertEqual((answer["head"], answer["events_in_chain"]), (head, count))
        # The gate's verdict as counts, which the page words in its own labels.
        rows = judge(self.results, DEV / "claims.jsonl", self.log, DIRECTORY)
        self.assertEqual(answer["gate"], {"claims": len(rows), "ready": sum(r["ready"] for r in rows),
                                          "blocked": dict(Counter(r["state"] for r in rows if not r["ready"]))})
        performed = load_jsonl(self.log)[-1]["event"]
        self.assertEqual(performed["command"], "claimguard.ui.serve")
        self.assertEqual(performed["events"], 2)
        self.assertEqual(performed["input_sha256"], hashlib.sha256(json.dumps(body).encode()).hexdigest())

        # The same decisions through the command line, on a copy of the log.
        cli_log = self.copy_log("cli")
        path = self.dir / "decisions.jsonl"
        path.write_text("".join(json.dumps(e) + "\n" for e in self.decisions()), encoding="utf-8")
        directory = self.dir / "actors.json"
        directory.write_text(json.dumps(DIRECTORY), encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(decisions_main(["--decisions", str(path), "--log", str(cli_log), "--directory", str(directory),
                                             "--results", str(self.results), "--claims", str(DEV / "claims.jsonl")]), 0)
        rows = [judge(self.results, DEV / "claims.jsonl", log, DIRECTORY) for log in (self.log, cli_log)]
        self.assertEqual(rows[0], rows[1])
        self.assertTrue(next(r for r in rows[0] if r["claim_id"] == CLAIM)["ready"])

    def test_the_page_is_rebuilt_after_a_save(self):
        before = page_data(self.page()[2].decode())["audit"]["events"]
        self.assertEqual(self.api("POST", "/api/decisions", {"decisions": self.decisions()})[0], 200)
        after = page_data(self.page()[2].decode())["audit"]["events"]
        self.assertEqual(len(after), len(before) + 3)  # two decisions and who appended them
        self.assertEqual([r["event"]["event"] for r in after[-3:]], ["review_decision", "review_decision", "append_performed"])

    def test_saving_twice_adds_nothing(self):
        self.api("POST", "/api/decisions", {"decisions": self.decisions()})
        before = self.log_bytes()
        code, answer = self.api("POST", "/api/decisions", {"decisions": self.decisions()})
        self.assertEqual((code, answer["appended"], answer["already_in_chain"]), (200, 0, 2))
        self.assertEqual(self.log_bytes(), before)

    def test_a_refusal_lists_every_problem_and_writes_nothing(self):
        events = self.decisions()
        events[0]["actor"] = "Nobody"
        events[1]["original_status"] = "UNABLE_TO_ASSESS"
        code, answer = self.api("POST", "/api/decisions", {"decisions": events})
        self.assertEqual(code, 422)
        self.assertEqual(len(answer["problems"]), 2)
        self.assertIn("decision 1", answer["problems"][0])
        self.assertIn("decision 2: taken on status UNABLE_TO_ASSESS", answer["problems"][1])
        self.assertEqual(self.log_bytes(), self.run_log.read_bytes())

    def test_a_stale_decision_is_refused(self):
        code, answer = self.api("POST", "/api/decisions", {"decisions": self.decisions(input_hash="0" * 64)})
        self.assertEqual(code, 422)
        self.assertTrue(all("another version" in p for p in answer["problems"]))

    def test_an_empty_or_malformed_list_is_refused(self):
        not_text = dict(self.decisions()[0], claim_id=[CLAIM], action=["dismiss_with_reason"])
        for body in ({}, {"decisions": []}, {"decisions": "x"}, {"decisions": [1]}, {"decisions": [not_text]}):
            code, _ = self.api("POST", "/api/decisions", body)
            self.assertIn(code, (400, 422), body)
        self.assertEqual(self.log_bytes(), self.run_log.read_bytes())

    def test_a_second_writer_is_refused(self):
        lock = chain.lock_path(self.log)
        lock.write_text("", encoding="utf-8")
        code, answer = self.api("POST", "/api/decisions", {"decisions": self.decisions()})
        self.assertEqual(code, 409)
        self.assertIn("another command is writing", answer["error"])
        self.assertEqual(self.log_bytes(), self.run_log.read_bytes())
        lock.unlink()
        self.assertEqual(self.api("POST", "/api/decisions", {"decisions": self.decisions()})[0], 200)

    def test_saves_from_two_tabs_at_once_are_serialised(self):
        answers = []
        threads = [threading.Thread(target=lambda: answers.append(self.api("POST", "/api/decisions",
                                                                          {"decisions": self.decisions()})))
                   for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(sorted(a[0] for a in answers), [200] * 4)
        self.assertEqual(sum(a[1]["appended"] for a in answers), 2)
        chain.verify(self.log, chain.default_anchor(self.log))

    def test_a_head_recorded_outside_must_still_match(self):
        self.server.shutdown()
        head, count = chain.verify(self.log, chain.default_anchor(self.log))
        self.start(expect=(count, "f" * 64))
        code, answer = self.api("POST", "/api/decisions", {"decisions": self.decisions()})
        self.assertEqual(code, 409)
        self.assertIn("rewritten", answer["error"])
        self.assertEqual(self.log_bytes(), self.run_log.read_bytes())

    def test_not_started_on_a_mismatched_head_or_bad_files(self):
        base = ["--results", str(self.results), "--claims", str(DEV / "claims.jsonl"), "--log", str(self.log), "--port", "0"]
        directory = self.dir / "actors.json"
        directory.write_text(json.dumps(DIRECTORY), encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(serve_main(base + ["--directory", str(directory), "--expect-count", "1",
                                                "--expect-head", "f" * 64]), 2)
            self.assertEqual(serve_main(base + ["--directory", str(self.dir / "missing.json")]), 2)
        self.assertIn("Not started", out.getvalue())


class CorrectionTests(ServerCase):
    """B3: a correction rechecked by the server."""

    def test_recheck_as_a_new_version(self):
        self.start()
        code, answer = self.api("POST", "/api/corrections", self.correction())
        self.assertEqual(code, 200, answer)
        self.assertEqual(answer["version"], 2)
        self.assertIn({"rule_id": "R008", "before": "FAIL", "after": "PASS"}, answer["status_changes"])
        self.assertTrue((self.corrections / f"{TO_CORRECT}.v2.json").exists())
        events = [r["event"] for r in load_jsonl(self.log)]
        self.assertEqual([e["event"] for e in events[-2:]], ["version_created", "append_performed"])
        self.assertEqual(events[-1]["command"], "claimguard.ui.serve")
        # The page now shows v2.
        entry = next(c for c in page_data(self.page()[2].decode())["claims"] if c["claim"]["claim_id"] == TO_CORRECT)
        self.assertEqual([v["version"] for v in entry["versions"]], [2])

    def test_a_correction_on_an_old_version_is_refused(self):
        self.start()
        self.assertEqual(self.api("POST", "/api/corrections", self.correction())[0], 200)
        before = self.log_bytes()
        code, answer = self.api("POST", "/api/corrections", self.correction(
            changes=[{"op": "replace", "path": "/total_amount", "value": 1}]))
        self.assertEqual(code, 409)
        self.assertIn("now v2", answer["error"])
        self.assertEqual(self.log_bytes(), before)

    def test_a_refused_correction_writes_nothing(self):
        self.start()
        for body, words in ((self.correction(actor="Nobody"), "not permitted"),
                            (self.correction(reason=" "), "reason"),
                            (self.correction(changes=[{"op": "replace", "path": "/claim_id", "value": "X"}]), "cannot be corrected"),
                            (self.correction(claim_id="CG-NOPE"), "not in this run")):
            code, answer = self.api("POST", "/api/corrections", body)
            self.assertEqual(code, 422, answer)
            self.assertIn(words, answer["error"].lower())
        self.assertEqual(self.api("POST", "/api/corrections", self.correction(changes="x"))[0], 400)
        self.assertEqual(self.log_bytes(), self.run_log.read_bytes())
        self.assertFalse(self.corrections.exists() and any(self.corrections.iterdir()))

    def test_no_corrections_folder_means_no_corrections(self):
        self.start(corrections=False)
        self.assertEqual(self.api("POST", "/api/corrections", self.correction())[0], 404)
        self.assertFalse(self.api("GET", "/api/status")[1]["corrections"])


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class SignInTests(ServerCase):
    """B4: optional sign-in."""

    def setUp(self):
        super().setUp()
        self.users = self.dir / "users.json"
        set_password(self.users, "Reviewer 01", PASSWORD, DIRECTORY)
        self.clock = FakeClock()
        self.signin = SignIn(load_users(self.users, DIRECTORY), DIRECTORY, clock=self.clock)

    def sign_in(self, name="Reviewer 01", password=PASSWORD):
        code, headers, raw = self.request("POST", "/api/signin", {"name": name, "password": password})
        if code == 200:
            cookie = headers["Set-Cookie"]
            self.assertIn("HttpOnly", cookie)
            self.assertIn("SameSite=Strict", cookie)
            self.session = cookie.split(";")[0].split("=", 1)[1]
        return code, json.loads(raw)

    def test_the_password_command_checks_before_it_asks(self):
        directory = self.dir / "actors.json"
        directory.write_text(json.dumps(DIRECTORY), encoding="utf-8")
        damaged = self.dir / "damaged.json"
        damaged.write_text("not json", encoding="utf-8")
        for users, name, words in ((self.users, "Ghost", "not in the actor directory"),
                                   (damaged, "Reviewer 02", "not a readable JSON file")):
            with mock.patch("claimguard.ui.signin.getpass.getpass") as asked, \
                    contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(signin_main(["--users", str(users), "--directory", str(directory), "--name", name]), 1)
            asked.assert_not_called()
            self.assertIn(words, out.getvalue())
        with mock.patch("claimguard.ui.signin.getpass.getpass", return_value=PASSWORD), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(signin_main(["--users", str(self.users), "--directory", str(directory),
                                          "--name", "Reviewer 02"]), 0)
        self.assertEqual(sorted(load_users(self.users, DIRECTORY)), ["Reviewer 01", "Reviewer 02"])

    def test_password_file_rules(self):
        with self.assertRaises(ValueError):
            set_password(self.users, "Reviewer 01", "short", DIRECTORY)
        with self.assertRaises(ValueError):
            set_password(self.users, "Someone Else", PASSWORD, DIRECTORY)
        record = json.loads(self.users.read_text(encoding="utf-8"))["Reviewer 01"]
        self.assertEqual(record["scheme"], "scrypt")
        self.assertNotIn(PASSWORD, self.users.read_text(encoding="utf-8"))
        weak = dict(record, n=2)
        self.users.write_text(json.dumps({"Reviewer 01": weak}), encoding="utf-8")
        with self.assertRaises(ValueError):
            load_users(self.users, DIRECTORY)
        self.users.write_text(json.dumps({"Ghost": hash_password(PASSWORD)}), encoding="utf-8")
        with self.assertRaises(ValueError):
            load_users(self.users, DIRECTORY)

    def test_saving_needs_a_signed_in_person(self):
        self.start(signin=self.signin)
        self.assertEqual(self.api("POST", "/api/decisions", {"decisions": self.decisions()})[0], 401)
        self.assertEqual(self.api("POST", "/api/corrections", self.correction())[0], 401)
        self.assertEqual(self.sign_in(password="wrong password")[0], 401)
        self.assertEqual(self.sign_in(name="Reviewer 02")[0], 401)  # in the directory, no password
        code, answer = self.sign_in()
        self.assertEqual((code, answer), (200, {"user": "Reviewer 01", "role": "reviewer"}))
        self.assertEqual(self.api("GET", "/api/status")[1]["signin"], {"user": "Reviewer 01", "role": "reviewer"})
        self.assertEqual(self.api("POST", "/api/decisions", {"decisions": self.decisions()})[0], 200)
        self.assertEqual(self.log_bytes()[:len(self.run_log.read_bytes())], self.run_log.read_bytes())

    def test_signed_in_actor_must_match(self):
        self.start(signin=self.signin)
        self.sign_in()
        code, answer = self.api("POST", "/api/decisions", {"decisions": self.decisions(actor="Reviewer 02")})
        self.assertEqual(code, 403)
        self.assertEqual(len(answer["problems"]), 2)
        self.assertEqual(self.log_bytes(), self.run_log.read_bytes())
        # A correction is recorded under the signed-in name, whatever the body says.
        code, _ = self.api("POST", "/api/corrections", self.correction(actor="Admin 01"))
        self.assertEqual(code, 200)
        self.assertEqual(load_jsonl(self.log)[-2]["event"]["actor"], "Reviewer 01")

    def test_sign_out_ends_the_session(self):
        self.start(signin=self.signin)
        self.sign_in()
        code, headers, _ = self.request("POST", "/api/signout", {})
        self.assertEqual(code, 200)
        self.assertIn("Max-Age=0", headers["Set-Cookie"])
        self.assertIsNone(self.api("GET", "/api/status")[1]["signin"]["user"])
        self.assertEqual(self.api("POST", "/api/decisions", {"decisions": self.decisions()})[0], 401)

    def test_a_forged_session_is_nobody(self):
        self.start(signin=self.signin)
        self.session = "forged"
        self.assertIsNone(self.api("GET", "/api/status")[1]["signin"]["user"])

    def test_failed_sign_ins_lock_the_name(self):
        for _ in range(5):
            with self.assertRaises(Exception):
                self.signin.sign_in("Reviewer 01", "wrong password")
        with self.assertRaisesRegex(Exception, "too many"):
            self.signin.sign_in("Reviewer 01", PASSWORD)
        self.clock.now += 61
        self.assertTrue(self.signin.sign_in("Reviewer 01", PASSWORD))

    def test_a_session_expires(self):
        sid = self.signin.sign_in("Reviewer 01", PASSWORD)
        self.assertEqual(self.signin.user(sid), "Reviewer 01")
        self.clock.now += 8 * 3600
        self.assertIsNone(self.signin.user(sid))


if __name__ == "__main__":
    unittest.main()
