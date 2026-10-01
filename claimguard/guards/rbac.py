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
separate directory, {actor: role}, kept beside the audit log.
"""
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
