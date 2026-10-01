"""Authorization predicates shared by R008 and R009 (DEC-007).

"If R008 already finds a missing ID, R009 is UNABLE_TO_ASSESS for that line."
Rather than R009 reading ctx.prior["R008"], which depends on run order (U2.6)
and is empty in unit tests, both rules classify each line with the same
functions below. The dependency is explicit in code, and R008 and R009 can
never disagree about which line needs an authorization or lacks a reference.

The leading underscore keeps this module out of rule discovery.
"""
from typing import Any, Mapping

from claimguard._pack import empty

from ._common import unknown_service

REQUIRED, NOT_REQUIRED, UNKNOWN = "required", "not_required", "unknown"

UNKNOWN_SERVICE_MESSAGE = "Unknown service prevents authorization requirement lookup"
"""Gold wording, identical in R008 and R009."""


def requirement(policy: Mapping[str, Any], line: Mapping[str, Any]) -> str:
    """Whether this line's service needs an authorization under this policy.

    UNKNOWN when the code is null or unlisted, as unknown_service() defines it
    for every rule (DEC-007). Exact and case-sensitive.
    """
    code = line["service_code"]
    if code in policy["auth_required_services"]:
        return REQUIRED
    if unknown_service(policy, code):
        return UNKNOWN
    return NOT_REQUIRED


def missing_reference(line: Mapping[str, Any]) -> bool:
    """R008's failure on a required line, and R009's cascade to UNABLE_TO_ASSESS.

    empty() is the pack's: None or a whitespace-only string, as R001 uses it.
    """
    return empty(line["authorization_id"])
