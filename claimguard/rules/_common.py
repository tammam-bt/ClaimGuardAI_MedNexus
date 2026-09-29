"""Helpers and gold wordings shared by the rule modules (R007, R008, R009, R010, R012, R013, R014).

The leading underscore keeps this module out of rule discovery.
"""
import math
from decimal import Context, Decimal
from typing import Any, Mapping

EXACT = Context(prec=1000)
"""Decimal context for money and quantity arithmetic (DEC-012): use as
`with localcontext(EXACT):`. The default keeps 28 digits, so a sum silently
rounds and money() raises on a 309-digit amount. 1,000 digits hold any product
or sum of JSON doubles exactly (at most about 620 digits)."""

TOLERANCE = Decimal("0.01")
PASS_MESSAGE = "The supplied evidence satisfies this fictional rule."
NO_POLICY_MESSAGE = "No policy is supplied for this policy_id."
NOT_APPLICABLE_MESSAGE = "Rule does not apply to the supplied claim."


def dec(v: Any) -> Decimal:
    """Exact Decimal of a JSON number (via str, so 0.1 stays 0.1)."""
    return Decimal(str(v))


def is_number(v: Any) -> bool:
    """int or float, but not bool: bool is a subclass of int in Python (DEC-002)."""
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def unknown_service(policy: Mapping[str, Any], code: Any) -> bool:
    """A service code the policy's service tables do not list, or null (DEC-007).

    The same tables R013 reads; never ctx.services, which context.py reserves
    for R011. Exact and case-sensitive: "svc-image" is not "SVC-IMAGE".
    """
    return code is None or code not in policy["max_unit_price"]


def missing(v: Any) -> bool:
    """None, or a float that is no usable amount: NaN or +/-Infinity (DEC-003).

    json.loads accepts NaN and Infinity and validate_transport lets any float
    through, so treat them as unknown input rather than crash or guess.
    """
    return v is None or (isinstance(v, float) and not math.isfinite(v))
