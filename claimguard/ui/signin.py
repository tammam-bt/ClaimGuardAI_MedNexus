"""Optional sign-in for the local review server (B4).

    python -m claimguard.ui.signin --users users.json --directory actors.json --name "Reviewer 01"

sets one person's password, asked twice and never taken from the command
line, in a JSON file of scrypt hashes. It is typed at the keyboard: on
Windows the prompt reads the console, so a password cannot be piped in. The
name and the file are checked before the prompt. Start claimguard.ui.serve with
--users users.json and every save then needs a signed-in person: a decision
is refused unless its actor is that person, and a correction is recorded
under their name. Roles still come from the actor directory only; a name
that is not in it cannot have a password.

What it proves, and what it does not: sign-in checks that whoever saves knows
that person's password. On a machine where reviewers have a shell under the
account that runs the server, they can edit the log, the directory or this
file directly, and sign-in proves nothing about that. It authenticates only
when the server and its files run under an account reviewers cannot use
(docs/THREAT_MODEL.md, T6 and T11).

Sessions live in the server's memory: an HttpOnly, SameSite=Strict cookie,
8 hours at most, ended by signing out or stopping the server. Five failed
sign-ins for a name lock it for 60 seconds.
"""
import argparse
import getpass
import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time
from pathlib import Path

from claimguard.guards.rbac import load_directory

SCRYPT = {"n": 2 ** 14, "r": 8, "p": 1}
MIN_LENGTH = 12
SESSION_SECONDS = 8 * 3600
MAX_FAILURES, LOCK_SECONDS = 5, 60
_HEX = re.compile(r"[0-9a-f]{32,128}")


class SignInRefused(Exception):
    """A sign-in refused. The message never says whether the name exists."""


def _derive(password, salt, n, r, p):
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p, maxmem=64 * 1024 * 1024, dklen=32)


def hash_password(password):
    salt = secrets.token_bytes(16)
    return {"scheme": "scrypt", **SCRYPT, "salt": salt.hex(), "hash": _derive(password, salt, **SCRYPT).hex()}


def load_users(path, directory):
    """{name: scrypt record} from the password file. Raises ValueError, naming
    the file but never quoting it, unless every name is in the actor
    directory and every record is a scrypt hash this module wrote."""
    try:
        users = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise ValueError(f"password file {path}: not a readable JSON file ({type(e).__name__})") from None
    if not isinstance(users, dict):
        raise ValueError(f"password file {path}: expected a JSON object of names to password hashes")
    for name, record in users.items():
        if name not in directory:
            raise ValueError(f"password file {path}: a name is not in the actor directory")
        ok = isinstance(record, dict) and record.get("scheme") == "scrypt" \
            and all(record.get(k) == v for k, v in SCRYPT.items()) \
            and all(isinstance(record.get(k), str) and _HEX.fullmatch(record[k]) for k in ("salt", "hash"))
        if not ok:
            raise ValueError(f"password file {path}: a record is not a scrypt hash written by claimguard.ui.signin")
    return users


def set_password(path, name, password, directory):
    """Add or replace one person's hash; the file is replaced in one step."""
    if name not in directory:
        raise ValueError("this name is not in the actor directory, so it has no role")
    if len(password) < MIN_LENGTH:
        raise ValueError(f"a password needs at least {MIN_LENGTH} characters")
    users = load_users(path, directory) if Path(path).exists() else {}
    users[name] = hash_password(password)
    tmp = Path(str(path) + ".tmp")
    tmp.write_text(json.dumps(users, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


class SignIn:
    """Password check, sessions and failure throttling for one server."""

    def __init__(self, users, directory, clock=time.monotonic):
        self.users, self.directory, self._clock = users, directory, clock
        self._sessions = {}   # session id -> (name, expires)
        self._failures = {}   # name -> (failures, locked until)
        self._lock = threading.Lock()
        # Checked against an unknown name too, so it takes as long as a known one.
        self._decoy = hash_password(secrets.token_urlsafe(16))

    def role(self, name):
        return self.directory.get(name)

    def sign_in(self, name, password):
        """A new session id, or SignInRefused."""
        if not isinstance(name, str) or not isinstance(password, str) or not name or len(name) > 200:
            raise SignInRefused("enter your name and password")
        now = self._clock()
        with self._lock:
            failures, until = self._failures.get(name, (0, 0.0))
            if until > now:
                raise SignInRefused("too many failed sign-ins for this name: try again in a minute")
        record = self.users.get(name, self._decoy)
        given = _derive(password, bytes.fromhex(record["salt"]), record["n"], record["r"], record["p"])
        if not (hmac.compare_digest(given.hex(), record["hash"]) and name in self.users):
            with self._lock:
                if len(self._failures) > 1000:
                    self._failures = {k: v for k, v in self._failures.items() if v[1] > now}
                failures += 1
                self._failures[name] = (0, now + LOCK_SECONDS) if failures >= MAX_FAILURES else (failures, 0.0)
            raise SignInRefused("the name or the password is wrong")
        sid = secrets.token_urlsafe(32)
        with self._lock:
            self._failures.pop(name, None)
            self._sessions[sid] = (name, now + SESSION_SECONDS)
        return sid

    def user(self, sid):
        """The signed-in name for a session id, or None."""
        if not sid:
            return None
        with self._lock:
            name, expires = self._sessions.get(sid, (None, 0.0))
            if name and expires <= self._clock():
                del self._sessions[sid]
                return None
            return name

    def sign_out(self, sid):
        with self._lock:
            self._sessions.pop(sid, None)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--users", required=True, help="the password file the server reads with --users")
    p.add_argument("--directory", required=True, help="JSON {actor: role}, e.g. actors.example.json")
    p.add_argument("--name", required=True, help="the person's name, exactly as in the directory")
    a = p.parse_args(argv)
    try:
        directory = load_directory(a.directory)
        if a.name not in directory:  # before the prompt, so a mistyped name costs no typing
            raise ValueError("this name is not in the actor directory, so it has no role")
        if Path(a.users).exists():
            load_users(a.users, directory)  # a damaged file is refused before the prompt too
        password = getpass.getpass(f"Password for {a.name} (at least {MIN_LENGTH} characters): ")
        if password != getpass.getpass("The same password again: "):
            raise ValueError("the two passwords differ")
        set_password(a.users, a.name, password, directory)
    except ValueError as e:
        print(f"Password not set: {e}")
        return 1
    print(f"Password set for {a.name} in {a.users}. Keep this file where reviewers cannot write it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
