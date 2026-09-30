"""The ingestion contract: what a claim must satisfy before any rule sees it.

Two checks, in order:

  1. The pack's validate_transport(), unchanged. It is the contract the pack's
     own runner enforces, so anything it rejects is rejected here too.
  2. schemas/claim.schema.json, read from the file so it cannot drift from it.
     validate_transport() checks only the top level and the line keys. It lets
     through NaN and Infinity (DEC-003), dates such as 20260525 that only
     Python 3.11+ accepts (DEC-010), and non-object or incomplete coverage,
     authorization and attachment records (DEC-012). The schema forbids all
     three.

Rejecting on the schema cannot cost a legitimate claim: QA_REPORT.md states
that all 800 claims, the mentor's 200 held-out ones included, were checked
against it. Only an input outside the documented contract fails here, and
docs/03 makes that an ingestion error: "quarantine it and report it
separately, never silently drop it".

A reason never quotes the input. It names a JSON pointer built from schema
keys and array indices only, so untrusted text cannot reach a log or a UI
through an error message.
"""
import json
import math
import re
from pathlib import Path

from claimguard._pack import valid_date, validate_transport

SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schemas" / "claim.schema.json"

# The keywords claim.schema.json uses. Any other keyword fails at load rather
# than being silently ignored.
_KEYWORDS = {"$schema", "title", "type", "properties", "required",
             "additionalProperties", "items", "minItems", "const", "format"}

# [0-9], not \d: \d also matches non-ASCII digits such as fullwidth ones.
_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


class ContractError(ValueError):
    """A claim outside the ingestion contract. stage is 'transport' or
    'contract'; reason never quotes the input."""

    def __init__(self, stage, reason):
        super().__init__(reason)
        self.stage = stage
        self.reason = reason


def _finite(v):
    # A JSON number must be a finite double. math.isfinite raises
    # OverflowError on an int too large for a double (10**400), which Python
    # 3.10 parses but 3.11+ may refuse, so both versions reject it here.
    try:
        return math.isfinite(v)
    except OverflowError:
        return False


_TYPES = {
    "null": lambda v: v is None,
    "string": lambda v: isinstance(v, str),
    # bool is a subclass of int: True is not a quantity.
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool) and _finite(v),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
}


def load_schema(path=SCHEMA_PATH):
    schema = json.loads(Path(path).read_text(encoding="utf-8"))

    def walk(node):
        unknown = set(node) - _KEYWORDS
        if unknown:
            raise RuntimeError(f"{Path(path).name} uses keywords the ingestion check does not implement: {sorted(unknown)}")
        for child in node.get("properties", {}).values():
            walk(child)
        if "items" in node:
            walk(node["items"])

    walk(schema)
    return schema


def _fail(path, what):
    raise ContractError("contract", f"{path or '/'}: {what}")


def _check(value, node, path):
    if "const" in node and (type(value) is not type(node["const"]) or value != node["const"]):
        _fail(path, "unexpected value")
    types = node.get("type")
    types = [types] if isinstance(types, str) else types
    if types and not any(_TYPES[t](value) for t in types):
        _fail(path, "expected " + " or ".join(types))
    if isinstance(value, dict):
        props = node.get("properties", {})
        missing = [k for k in node.get("required", []) if k not in value]
        if missing:
            _fail(path, "missing required key " + ", ".join(missing))
        if node.get("additionalProperties") is False and not set(value) <= set(props):
            _fail(path, "unexpected key")
        for k, child in props.items():
            if k in value:
                _check(value[k], child, f"{path}/{k}")
    elif isinstance(value, list):
        if len(value) < node.get("minItems", 0):
            _fail(path, "too few items")
        if "items" in node:
            for i, item in enumerate(value):
                _check(item, node["items"], f"{path}/{i}")
    elif isinstance(value, str) and node.get("format") == "date":
        if not _DATE.fullmatch(value) or valid_date(value) is None:
            _fail(path, "not a YYYY-MM-DD calendar date")


_SCHEMA = load_schema()


def check_claim(claim):
    """Raise ContractError if claim is outside the ingestion contract.

    Never modifies claim: rules and evidence must see the original values.
    """
    try:
        validate_transport(claim)
    except ValueError as e:
        # The pack's messages are fixed strings plus a schema key name.
        raise ContractError("transport", str(e)) from None
    except (TypeError, KeyError, AttributeError, IndexError) as e:
        raise ContractError("transport", f"malformed structure ({type(e).__name__})") from None
    _check(claim, _SCHEMA, "")
