"""Role-based access sketch (U6.6): who may do what, checked before it happens.

The pack defines no roles. Doc 10: "The supplied static interface uses
self-declared reviewer names and does not authenticate users." This module is
authorization given an identity; authentication (proving who the actor is)
is out of scope and stated as such. A production design would take the actor
from a verified login, not from the event.

Two roles:

  reviewer  reads claims and findings, records the four review decisions
            (schemas/review_event.schema.json) and exports them;
  admin     everything a reviewer can, plus running the pipeline, the audit
            log, run events (ingestion errors, model failures) and AI settings.

The role never goes into a review event or a result row: both schemas forbid
extra keys, and evaluate.py rejects a result with one. It is looked up in a
separate directory, {actor: role}, kept beside the audit log
(actors.example.json shows the format). Every command that writes a human
action to the audit log requires it: no directory, no action.
"""
import json
from pathlib import Path

REVIEW_ACTIONS = frozenset({"confirm_issue", "dismiss_with_reason", "request_information",
                            "mark_corrected_for_recheck"})

PERMISSIONS = {
    "reviewer": frozenset({"view_claim", "view_findings", "export_decisions"}) | REVIEW_ACTIONS,
    "admin": frozenset({"view_claim", "view_findings", "export_decisions", "run_pipeline",
                        "append_audit", "verify_audit", "view_run_events", "change_ai_settings"})
             | REVIEW_ACTIONS,
}

_EVENT_KEYS = {"claim_id", "rule_id", "action", "actor", "reason", "created_at", "original_status"}


class PermissionDenied(Exception):
    """An action refused. The message names the role and action, never the
    reason text or other input."""


def load_directory(path):
    """The actor directory {actor: role} from a JSON file. Raises ValueError,
    naming the file but never quoting its content, unless it is one non-empty
    JSON object mapping non-blank names to known roles: a mistyped role must
    never grant a permission or silently drop one."""
    try:
        directory = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise ValueError(f"actor directory {path}: not a readable JSON file ({type(e).__name__})") from None
    if not isinstance(directory, dict) or not directory:
        raise ValueError(f"actor directory {path}: expected a non-empty JSON object of actor names to roles")
    for actor, role in directory.items():
        if not actor.strip():
            raise ValueError(f"actor directory {path}: an actor name is blank")
        if not isinstance(role, str) or role not in PERMISSIONS:
            raise ValueError(f"actor directory {path}: an actor has an unknown role; roles are {sorted(PERMISSIONS)}")
    return directory


def allowed(role, action):
    return action in PERMISSIONS.get(role, frozenset())


def authorize(directory, actor, action):
    """Return the actor's role, or raise PermissionDenied."""
    if not isinstance(actor, str) or not actor.strip():
        raise PermissionDenied("an actor is required")
    role = directory.get(actor)
    if role is None:
        raise PermissionDenied("actor is not in the directory")
    if not allowed(role, action):
        raise PermissionDenied(f"role {role!r} may not {action}")
    return role


def authorize_event(directory, event):
    """Check a review event before it is appended to the audit log. Returns
    the actor's role. Never modifies the event.

    Beyond the role: the event must have exactly the schema's keys, and every
    action needs a reason, as src/audit.py's append() requires (doc 10:
    "Require an actor, timestamp and reason").
    """
    if not isinstance(event, dict) or set(event) != _EVENT_KEYS:
        raise PermissionDenied("event keys must match schemas/review_event.schema.json")
    if event["action"] not in REVIEW_ACTIONS:
        raise PermissionDenied("unknown review action")
    role = authorize(directory, event["actor"], event["action"])
    if not isinstance(event["reason"], str) or not event["reason"].strip():
        raise PermissionDenied("a reason is required")
    return role
