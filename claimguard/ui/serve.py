"""Serve the review page on this machine, and save decisions from it (Track C).

    python -m claimguard.ui.serve --results outputs/dev_predictions.jsonl \\
        --claims data/development/claims.jsonl --log outputs/audit.jsonl \\
        --directory actors.json [--corrections outputs/corrections] \\
        [--gold data/development/expected_results.jsonl] [--users users.json] [--port 8765]

It prints one address, http://127.0.0.1:<port>/?token=..., to open in a
browser on this machine. A reviewer then saves drafts to the audit log and
rechecks corrections from the page, with no download and no command. The
page written by python -m claimguard.ui is unchanged and still works offline:
it never looks for a server.

    GET  /                 the page, rebuilt from the run's files when they change
    GET  /api/status       the audit log's verified count and head
    POST /api/decisions    {"decisions": [review_decision, ...]}: the checks and
                           append of python -m claimguard.ui.decisions
    POST /api/corrections  {"claim_id", "parent_hash", "changes", "actor", "reason"}:
                           python -m claimguard.review.correct with --log
    POST /api/signin       {"name", "password"}, and POST /api/signout: only
                           with --users (claimguard.ui.signin)

Checks, each against a threat in docs/THREAT_MODEL.md:

  - bound to 127.0.0.1 only, and Host must be 127.0.0.1:<port> or
    localhost:<port> (DNS rebinding);
  - a random token per launch: in the printed address once, then moved by a
    redirect into an HttpOnly, SameSite=Strict cookie; the page needs it, and
    every API call sends it in X-ClaimGuard-Token;
  - every POST: Origin must be this server, Sec-Fetch-Site same-origin when
    sent, Content-Type application/json, Content-Length at most 1 MiB; no
    CORS header is ever sent;
  - one write at a time, inside M4's writer lock: a second writer, here or
    on the command line, is refused, never interleaved.

append_performed names claimguard.ui.serve, the OS user running it, and the
SHA-256 of the request body. Without --users, names are self-declared, as on
the static page; with it, every save needs a signed-in person.

Exit code 2: not started (a file cannot be read, the chain does not match
--expect-count and --expect-head, or the port is taken).
"""
import argparse
import hashlib
import hmac
import json
import secrets
import socket
import sys
import threading
import traceback
from dataclasses import dataclass
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from urllib.parse import parse_qs, urlsplit

from claimguard.audit import chain
from claimguard.guards.rbac import load_directory
from claimguard.ingest.jsonl import claims_by_id
from claimguard.review.correct import correct_claim, latest_version
from claimguard.review.gate import GateError, judge, verdict
from claimguard.ui.bundle import build
from claimguard.ui.decisions import DecisionsRefused, append_events
from claimguard.ui.page import render
from claimguard.ui.signin import SignIn, SignInRefused, load_users

COMMAND = "claimguard.ui.serve"
HOST = "127.0.0.1"
MAX_BODY = 1 << 20
TOKEN_HEADER = "X-ClaimGuard-Token"


@dataclass(frozen=True)
class Run:
    """The run's files, as the command-line tools take them."""
    results: str
    claims: str
    log: str
    anchor: str
    directory: Dict[str, str]
    corrections: Optional[str] = None
    gold: Optional[str] = None
    expect: Optional[Tuple[int, str]] = None


class App:
    """What the server does, apart from HTTP: tested on its own."""

    def __init__(self, run: Run, *, signin: Optional[SignIn] = None, token: Optional[str] = None, quiet=False):
        self.run, self.signin, self.quiet = run, signin, quiet
        self.token = token or secrets.token_urlsafe(32)
        self.port = 0
        self._write = threading.Lock()  # one write at a time, and no page built during one
        self._page: Tuple[Any, bytes] = (None, b"")

    # ------------------------------------------------------------ identity
    @property
    def url(self):
        return f"http://{HOST}:{self.port}/?token={self.token}"

    def hosts(self):
        return {f"{HOST}:{self.port}", f"localhost:{self.port}"}

    def cookie(self, kind):
        """Cookies are shared by every port of a host: the name holds the port."""
        return f"claimguard_{kind}_{self.port}"

    def token_ok(self, given):
        return isinstance(given, str) and hmac.compare_digest(given.encode(), self.token.encode())

    # ---------------------------------------------------------------- page
    def _files(self):
        """What the page is built from, as (path, mtime, size): a change rebuilds it."""
        r = self.run
        paths = [r.results, r.claims, r.log, r.anchor, r.gold]
        if r.corrections and Path(r.corrections).is_dir():
            paths += sorted(str(p) for p in Path(r.corrections).glob("*.json"))
        key = []
        for p in paths:
            try:
                st = Path(p).stat() if p else None
                key.append((p, st.st_mtime_ns, st.st_size) if st else (p,))
            except OSError:
                key.append((p, None))
        return tuple(key)

    def page(self) -> bytes:
        """The page, served: the run's data, this launch's token, and a policy
        that lets it call this server and nothing else. Raises ValueError or
        OSError if the run's files cannot be read."""
        with self._write:
            key = self._files()
            if self._page[0] != key:
                r = self.run
                data = build(r.results, r.claims, audit_log=r.log, gold_path=r.gold, corrections=r.corrections,
                             anchor=r.anchor)
                data["server"] = {"token": self.token}
                self._page = (key, render(data, served=True).encode("utf-8"))
            return self._page[1]

    # ----------------------------------------------------------------- api
    def status(self, user=None):
        r = self.run
        try:
            head, count = chain.verify(r.log, r.anchor, r.expect)
            audit = {"valid": True, "count": count, "head": head}
        except chain.AuditError as e:
            audit = {"valid": False, "error": str(e)}
        return {"server": COMMAND, "audit": audit, "corrections": bool(r.corrections),
                "signin": {"user": user, "role": self.signin.role(user) if user else None} if self.signin else None}

    def _verdict(self):
        r = self.run
        try:
            return verdict(judge(r.results, r.claims, r.log, r.directory, anchor=r.anchor, corrections=r.corrections,
                                 expect=r.expect))
        except (GateError, ValueError) as e:
            return f"The gate cannot judge: {e}"

    def save_decisions(self, body, body_sha256, user=None):
        """(HTTP status, answer). The same checks and append as the command line."""
        events = body.get("decisions")
        if not isinstance(events, list) or not events:
            return 400, {"error": "decisions must be a non-empty list"}
        if self.signin:
            if not user:
                return 401, {"error": "Sign in to save decisions."}
            others = [f"decision {n}: its actor is not {user}, who is signed in"
                      for n, e in enumerate(events, start=1) if not isinstance(e, dict) or e.get("actor") != user]
            if others:
                return 403, {"error": "No decision was saved.", "problems": others}
        r = self.run
        with self._write:
            try:
                if r.expect:
                    chain.verify(r.log, r.anchor, r.expect)
                summary = append_events(events, r.log, claims_path=r.claims, results_path=r.results,
                                        directory=r.directory, input_sha256=body_sha256, anchor=r.anchor,
                                        corrections=r.corrections, command=COMMAND)
            except DecisionsRefused as e:
                return 422, {"error": "No decision was saved.", "problems": e.problems}
            except (ValueError, OSError) as e:  # AuditError is a ValueError
                return 409, {"error": f"No decision was saved: {e}"}
            return 200, {**summary, "verdict": self._verdict()}

    def save_correction(self, body, body_sha256, user=None):
        """(HTTP status, answer). python -m claimguard.review.correct, after
        checking the correction builds on the latest version."""
        r = self.run
        if not r.corrections:
            return 404, {"error": "This server was started without a corrections folder."}
        if self.signin and not user:
            return 401, {"error": "Sign in to correct a claim."}
        claim_id, parent, changes = body.get("claim_id"), body.get("parent_hash"), body.get("changes")
        actor, reason = (user if self.signin else body.get("actor")), body.get("reason")
        if not all(isinstance(v, str) for v in (claim_id, parent, actor, reason)) or not isinstance(changes, list):
            return 400, {"error": "a correction needs claim_id, parent_hash, actor and reason as text, and changes as a list"}
        with self._write:
            try:
                if r.expect:
                    chain.verify(r.log, r.anchor, r.expect)
                claims = claims_by_id(r.claims)
                if claim_id not in claims:
                    return 422, {"error": f"Correction refused: claim {claim_id} is not in this run."}
                latest = latest_version(claims[claim_id], r.corrections)
                if latest.input_hash != parent:
                    return 409, {"error": f"Correction refused: {claim_id} changed since this page was loaded "
                                          f"(it is now v{latest.version}). Reload the page and correct the latest version."}
                _, record = correct_claim(r.claims, claim_id, changes, actor=actor, reason=reason,
                                          directory=r.directory, output=r.corrections, log=r.log, anchor=r.anchor,
                                          changes_sha256=body_sha256, command=COMMAND)
            except (ValueError, OSError) as e:
                return 422, {"error": f"Correction refused: {e}"}
            except (TypeError, KeyError, AttributeError):
                return 422, {"error": "Correction refused: the changes are not JSON Patch operations"}
            return 200, {"claim_id": claim_id, "version": record["version"], "input_hash": record["input_hash"],
                         "status_changes": record["status_changes"], "rule_errors": record["rule_errors"],
                         "verdict": self._verdict()}


class Handler(BaseHTTPRequestHandler):
    server_version = "ClaimGuard"
    timeout = 15

    def version_string(self):
        return self.server_version

    @property
    def app(self) -> App:
        return self.server.app

    # ------------------------------------------------------------ logging
    # The request line holds the token on the first visit: never logged.
    def log_request(self, code="-", size="-"):
        if not self.app.quiet:
            sys.stderr.write(f"{self.command} {urlsplit(self.path).path} {code}\n")

    def log_message(self, format, *args):
        if not self.app.quiet:
            sys.stderr.write((format % args) + "\n")

    # ---------------------------------------------------------- responses
    def _send(self, code, body: bytes, content_type, headers=()):
        self.send_response(code)
        for k, v in [("Content-Type", content_type), ("Content-Length", str(len(body))), ("Cache-Control", "no-store"),
                     ("X-Content-Type-Options", "nosniff"), ("Referrer-Policy", "no-referrer"),
                     ("X-Frame-Options", "DENY"), ("Cross-Origin-Resource-Policy", "same-origin"), *headers]:
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, code, answer, headers=()):
        self._send(code, json.dumps(answer).encode("utf-8"), "application/json", headers)

    def _refuse(self, code, message):
        if urlsplit(self.path).path.startswith("/api/"):
            self._json(code, {"error": message})
        else:
            self._send(code, (message + "\n").encode("utf-8"), "text/plain; charset=utf-8")

    def _cookie(self, name):
        try:
            jar = SimpleCookie(self.headers.get("Cookie", ""))
        except CookieError:
            return None
        return jar[name].value if name in jar else None

    def _set_cookie(self, name, value, *, clear=False):
        return ("Set-Cookie", f"{name}={value}; HttpOnly; SameSite=Strict; Path=/" + ("; Max-Age=0" if clear else ""))

    def _user(self):
        return self.app.signin.user(self._cookie(self.app.cookie("session"))) if self.app.signin else None

    # ------------------------------------------------------------- checks
    def _host_ok(self):
        if self.headers.get("Host") not in self.app.hosts():
            self._refuse(403, "This server answers only to 127.0.0.1 or localhost on its own port.")
            return False
        return True

    def _api_token_ok(self):
        if not self.app.token_ok(self.headers.get(TOKEN_HEADER)):
            self._refuse(403, "Missing or wrong launch token.")
            return False
        return True

    def _origin_ok(self):
        origin, site = self.headers.get("Origin"), self.headers.get("Sec-Fetch-Site")
        if origin != f"http://{self.headers.get('Host')}" or site not in (None, "same-origin"):
            self._refuse(403, "Only this server's own page may write.")
            return False
        return True

    def _body(self):
        """(parsed JSON object, SHA-256 of the bytes), or None once refused."""
        if self.headers.get("Transfer-Encoding"):
            self._refuse(411, "Send a Content-Length, not a chunked body.")
            return None
        if (self.headers.get("Content-Type") or "").split(";")[0].strip().lower() != "application/json":
            self._refuse(415, "The body must be application/json.")
            return None
        try:
            length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            self._refuse(411, "A Content-Length is required.")
            return None
        if length < 0 or length > MAX_BODY:
            self.close_connection = True
            self._refuse(413, f"The body is larger than {MAX_BODY} bytes.")
            return None
        raw = self.rfile.read(length)
        try:
            body = json.loads(raw.decode("utf-8"))
        except (ValueError, RecursionError):  # RecursionError: nesting too deep to parse
            self._refuse(400, "The body is not JSON.")
            return None
        if not isinstance(body, dict):
            self._refuse(400, "The body must be a JSON object.")
            return None
        return body, hashlib.sha256(raw).hexdigest()

    # ------------------------------------------------------------- routes
    def do_GET(self):
        if not self._host_ok():
            return
        url = urlsplit(self.path)
        if url.path == "/":
            given = parse_qs(url.query).get("token", [None])[0]
            if given is not None:
                if not self.app.token_ok(given):
                    return self._refuse(403, "Wrong launch token: open the address the server printed.")
                # The token leaves the address bar (and history) for a cookie.
                return self._send(303, b"", "text/plain", [("Location", "/"),
                                                            self._set_cookie(self.app.cookie("launch"), given)])
            if not self.app.token_ok(self._cookie(self.app.cookie("launch"))):
                return self._refuse(403, "Open the address the server printed: it holds this launch's token.")
            try:
                page = self.app.page()
            except (ValueError, OSError) as e:
                return self._refuse(500, f"The page cannot be built from the run's files: {e}")
            return self._send(200, page, "text/html; charset=utf-8", [("Content-Security-Policy", "frame-ancestors 'none'")])
        if url.path == "/api/status":
            if self._api_token_ok():
                self._json(200, self.app.status(self._user()))
            return
        self._refuse(404, "Not found.")

    def do_POST(self):
        if not (self._host_ok() and self._origin_ok() and self._api_token_ok()):
            return
        try:
            self._post()
        except Exception:  # an answer, never a dropped connection; the details go to the server's log only
            self.log_error("%s", traceback.format_exc())
            self._json(500, {"error": "The server could not handle this request. Nothing was saved."})

    def _post(self):
        got = self._body()
        if got is None:
            return
        body, sha = got
        path = urlsplit(self.path).path
        if path == "/api/decisions":
            return self._json(*self.app.save_decisions(body, sha, self._user()))
        if path == "/api/corrections":
            return self._json(*self.app.save_correction(body, sha, self._user()))
        if path in ("/api/signin", "/api/signout") and self.app.signin:
            name = self.app.cookie("session")
            if path == "/api/signout":
                self.app.signin.sign_out(self._cookie(name))
                return self._json(200, {"user": None}, [self._set_cookie(name, "", clear=True)])
            try:
                sid = self.app.signin.sign_in(body.get("name"), body.get("password"))
            except SignInRefused as e:
                return self._json(401, {"error": f"Not signed in: {e}."})
            user = body["name"]
            return self._json(200, {"user": user, "role": self.app.signin.role(user)}, [self._set_cookie(name, sid)])
        self._refuse(404, "Not found.")


class Server(ThreadingHTTPServer):
    daemon_threads = True
    # On Windows, SO_REUSEADDR would let another program bind the same port;
    # exclusive use refuses it instead.
    allow_reuse_address = False

    def server_bind(self):
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()

    def handle_error(self, request, client_address):
        # A browser that leaves (a reload, a closed tab) is not an error.
        if not isinstance(sys.exc_info()[1], ConnectionError):
            super().handle_error(request, client_address)


def make_server(app: App, port=0) -> Server:
    """Bind to 127.0.0.1 only; port 0 picks a free one."""
    server = Server((HOST, port), Handler)
    server.app = app
    app.port = server.server_address[1]
    return server


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--results", required=True, help="the run's results")
    p.add_argument("--claims", required=True, help="the claims file the run read")
    p.add_argument("--log", required=True, help="the run's audit log")
    p.add_argument("--anchor", help="chain-head anchor (default: beside the log)")
    p.add_argument("--directory", required=True, help="JSON {actor: role}, e.g. actors.example.json")
    p.add_argument("--corrections", help="folder of corrected versions; enables corrections from the page")
    p.add_argument("--gold", help="expected results, for the evaluation page")
    p.add_argument("--users", help="password file from python -m claimguard.ui.signin; every save then needs sign-in")
    p.add_argument("--port", type=int, default=8765, help="port on 127.0.0.1 (0: any free port)")
    p.add_argument("--quiet", action="store_true", help="do not print each request")
    chain.add_expect_arguments(p)
    a = p.parse_args(argv)
    expect = chain.expected(p, a)
    anchor = a.anchor or chain.default_anchor(a.log)
    try:
        directory = load_directory(a.directory)
        signin = SignIn(load_users(a.users, directory), directory) if a.users else None
        if expect:
            chain.verify(a.log, anchor, expect)
        app = App(Run(a.results, a.claims, a.log, anchor, directory, a.corrections, a.gold, expect),
                  signin=signin, quiet=a.quiet)
        app.page()  # refuses to start on files it cannot read
        server = make_server(app, a.port)
    except (ValueError, OSError) as e:  # AuditError is a ValueError
        print(f"Not started: {e}")
        return 2
    print(f"ClaimGuard review server, for this machine only{' (sign-in required)' if signin else ''}. Open:\n"
          f"  {app.url}\n"
          "The address holds this launch's token: do not share it. Stop the server with Ctrl+C.")
    sys.stdout.flush()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    audit = app.status()["audit"]
    if audit["valid"] and audit["count"]:
        print(chain.record_hint(audit["count"], audit["head"]))
    elif not audit["valid"]:
        print(f"Audit chain INVALID: {audit['error']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
