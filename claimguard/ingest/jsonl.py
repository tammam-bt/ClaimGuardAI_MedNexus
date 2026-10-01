"""Read a normalized JSONL claims file one line at a time (U1.6, U1.7).

The pack's runner calls validate_transport() on every claim with no guard, so
one malformed line aborts all of them. Here each line is parsed and checked
on its own: a bad line becomes an ingestion-error record and every other claim
is still read.

An accepted claim is the exact object json.loads() makes of its line, the same
object the pack's load_jsonl() and evaluate.py see, so every evidence value
still resolves. Provenance travels beside the claim in Ingested, never inside
it: validate_transport() rejects any key beyond the envelope's.

Lines are split the way the pack's text-mode reader splits them (\\n, \\r\\n
or \\r) and blank lines are skipped the same way, so line numbers and claims
line up with what evaluate.py reads.
"""
import codecs
import hashlib
import json
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .contract import ContractError, check_claim

ADAPTER = "jsonl"
ADAPTER_VERSION = "1.0.0"

# Public claim IDs look like CG-27BFD8541DEB. An ID outside this shape is still
# a valid claim ID, but it is left out of error records so that untrusted text
# never reaches a log through them.
_SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")


@dataclass(frozen=True)
class Provenance:
    """Where one record came from: which adapter produced it, from which file
    and line, and the SHA-256 of the file and of the line's original bytes.
    sidecar is set when part of the claim came from a second file (the FHIR
    adapter): that file, its SHA-256 and the line used. parts is set when one
    claim is assembled from rows of several files (the CSV adapter): each
    file's name and the lines used."""
    adapter: str
    adapter_version: str
    source: str
    source_sha256: str
    line_number: int
    record_sha256: str
    sidecar: object = None
    parts: object = None

    def as_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class Ingested:
    """An accepted claim, its provenance, and its line's original bytes."""
    claim: dict
    provenance: Provenance
    raw: bytes


@dataclass
class IngestResult:
    source: str
    source_sha256: str
    records: int = 0
    accepted: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    adapter: str = ADAPTER
    adapter_version: str = ADAPTER_VERSION

    def summary(self):
        return {
            "adapter": self.adapter,
            "adapter_version": self.adapter_version,
            "source": self.source,
            "source_sha256": self.source_sha256,
            "records": self.records,
            "accepted": len(self.accepted),
            "rejected": len(self.errors),
            "rejected_by_stage": dict(sorted(Counter(e["stage"] for e in self.errors).items())),
        }


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


def _unique_keys(pairs):
    # Duplicate keys are legal JSON, but json.loads keeps only the last, so a
    # reviewer reading the raw line and the engine could see different values.
    keys = [k for k, _ in pairs]
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate key in an object")
    return dict(pairs)


def _parse(text):
    try:
        return json.loads(text, object_pairs_hook=_unique_keys)
    except json.JSONDecodeError as e:
        raise ContractError("json", f"invalid JSON: {e.msg} at column {e.colno}") from None
    except RecursionError:
        raise ContractError("json", "invalid JSON: nesting too deep") from None
    except ValueError as e:
        # _unique_keys, or an integer beyond Python's digit limit (3.11+).
        raise ContractError("json", f"invalid JSON: {e}") from None


def _error(stage, reason, claim_id, provenance):
    return {
        "event": "ingestion_error",
        "stage": stage,
        "reason": reason,
        "claim_id": claim_id,
        "provenance": provenance.as_dict(),
    }


def read_jsonl(path):
    """Ingest a JSONL claims file. Never raises for a bad record; raises only
    if the file itself cannot be read."""
    data = Path(path).read_bytes()
    result = IngestResult(source=str(path), source_sha256=_sha256(data))
    if data.startswith(codecs.BOM_UTF8):
        data = data[len(codecs.BOM_UTF8):]
    seen = set()
    for number, raw in enumerate(data.splitlines(), start=1):
        provenance = Provenance(ADAPTER, ADAPTER_VERSION, result.source, result.source_sha256,
                                number, _sha256(raw))
        claim_id = None
        try:
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                raise ContractError("decode", "not valid UTF-8") from None
            if not text.strip():
                continue
            claim = _parse(text)
            if isinstance(claim, dict) and isinstance(claim.get("claim_id"), str) \
                    and _SAFE_ID.fullmatch(claim["claim_id"]):
                claim_id = claim["claim_id"]
            check_claim(claim)
            if claim["claim_id"] in seen:
                raise ContractError("duplicate_claim_id", "claim_id already read on an earlier line")
            seen.add(claim["claim_id"])
        except ContractError as e:
            result.records += 1
            result.errors.append(_error(e.stage, e.reason, claim_id, provenance))
            continue
        result.records += 1
        result.accepted.append(Ingested(claim, provenance, raw))
    return result
