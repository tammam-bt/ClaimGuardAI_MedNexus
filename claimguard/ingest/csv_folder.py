"""Relational CSV export to ClaimGuard envelopes, one claim at a time.

A split's csv/ folder holds claims.csv (one row per claim), coverage.csv (one
per claim), lines.csv, authorizations.csv and attachments.csv, joined by
claim_id (doc 03). The pack's src/csv_to_jsonl.py rebuilds the JSONL from
them, but one bad row stops it for every claim: a child row whose claim_id is
not in claims.csv raises KeyError, a quantity of "abc" raises ValueError.
Here each claim is assembled and checked on its own, as the JSONL and FHIR
adapters do, and a bad row rejects only the claim it belongs to.

An accepted claim equals its normalized JSONL envelope exactly: values, JSON
types and key order at every level, verified on all 600 public claims. An
empty cell is null, as in the pack's converter. A numeric cell must be a
number in JSON syntax with ASCII digits and is read by the JSON parser, so
"280" is an int and "280.0" a float, as written and as in the JSONL. The
converter differs on both points: it turns every whole number into an int (8
public totals and net amounts are written 280.0), and it takes anything
float() accepts, so " 12", "1_000", "inf", "nan" and non-Latin digits such as
"١٢" would be read differently from what a reviewer sees. Here they are
rejected.

The expected columns and the numeric ones come from schemas/claim.schema.json,
as the contract check does. A file whose header differs is a file-level error
(ValueError): no row of it can be read. Everything else is an ingestion-error
record:

    csv                 a row of the claim cannot be read (wrong field count,
                        not a number, not UTF-8, more than one coverage row)
    duplicate_claim_id  the claim_id is on more than one claims.csv row; all
                        of them are rejected, since their child rows cannot
                        be told apart
    orphan_row          a child row whose claim_id is not in claims.csv
    transport/contract  the assembled claim fails the ingestion contract

Provenance: source is the folder, source_sha256 a digest of the five files'
SHA-256, line_number the claim's line in claims.csv, record_sha256 the
SHA-256 of the assembled claim as canonical JSON (no single original line
holds it), and parts the lines used in each file.
"""
import csv
import hashlib
import io
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from .contract import _SCHEMA, ContractError, check_claim
from .jsonl import _SAFE_ID, IngestResult, Ingested, Provenance, _error, _sha256

ADAPTER = "csv"
ADAPTER_VERSION = "1.0.0"

_NESTED = ("coverage", "lines", "authorizations", "attachments")
FILES = ("claims",) + _NESTED
_NUMBER = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?")


def _types(node):
    t = node.get("type", [])
    return [t] if isinstance(t, str) else t


def _layout():
    props = _SCHEMA["properties"]
    columns = {"claims": [k for k in _SCHEMA["required"] if k not in _NESTED]}
    numeric = {"claims": {k for k in columns["claims"] if "number" in _types(props[k])}}
    for name in _NESTED:
        record = props[name].get("items", props[name])
        columns[name] = ["claim_id"] + list(record["properties"])
        numeric[name] = {k for k, v in record["properties"].items() if "number" in _types(v)}
    return columns, numeric


COLUMNS, NUMERIC = _layout()


class _RowError(Exception):
    pass


def _read(folder, name):
    """(SHA-256 of the file, [(line number, cells or None)])."""
    data = (Path(folder) / f"{name}.csv").read_bytes()
    # surrogateescape keeps invalid bytes visible per row instead of failing
    # the whole file.
    text = data.decode("utf-8", "surrogateescape").removeprefix("﻿")
    reader = csv.reader(io.StringIO(text, newline=""))
    try:
        header = next(reader)
    except StopIteration:
        raise ValueError(f"{name}.csv is empty") from None
    if header != COLUMNS[name]:
        raise ValueError(f"{name}.csv header does not match schemas/claim.schema.json")
    rows = []
    while True:
        try:
            cells = next(reader)
        except StopIteration:
            break
        except csv.Error:
            rows.append((reader.line_num, None))
            continue
        if cells:  # the converter (csv.DictReader) skips blank lines too
            rows.append((reader.line_num, cells))
    return _sha256(data), rows


def _row(name, cells):
    if cells is None:
        raise _RowError(f"{name}.csv row is not valid CSV")
    if len(cells) != len(COLUMNS[name]):
        raise _RowError(f"{name}.csv row has {len(cells)} fields, expected {len(COLUMNS[name])}")
    if any("\udc80" <= ch <= "\udcff" for v in cells for ch in v):
        raise _RowError(f"{name}.csv row is not valid UTF-8")
    out = {}
    for key, value in zip(COLUMNS[name], cells):
        if value == "":
            out[key] = None
        elif key in NUMERIC[name]:
            if not _NUMBER.fullmatch(value):
                raise _RowError(f"{name}.csv column {key} is not a number")
            try:
                # The JSON parser, as for the JSONL: "280" is an int, "280.0"
                # a float, as written.
                out[key] = json.loads(value)
            except ValueError:  # an integer beyond Python's digit limit (3.11+)
                raise _RowError(f"{name}.csv column {key} is not a number") from None
        else:
            out[key] = value
    return out


def _safe(cid):
    return cid if isinstance(cid, str) and _SAFE_ID.fullmatch(cid) else None


def read_csv_folder(folder):
    """Ingest a CSV export folder. Never raises for a bad row; raises only if
    a file is missing, unreadable or has the wrong header."""
    files = {name: _read(folder, name) for name in FILES}
    digest = hashlib.sha256("".join(f"{n}.csv {d}\n" for n, (d, _) in files.items()).encode()).hexdigest()
    result = IngestResult(source=str(folder), source_sha256=digest, adapter=ADAPTER, adapter_version=ADAPTER_VERSION)

    def provenance(line, parts=None, record=None):
        return Provenance(ADAPTER, ADAPTER_VERSION, result.source, digest, line, record, None, parts)

    # One entry per claims.csv row, in file order.
    entries = []
    for line, cells in files["claims"][1]:
        cid = cells[1] if cells and len(cells) > 1 else None
        entry = {"line": line, "cid": cid, "errors": [], "claim": None,
                 "parts": defaultdict(list, {"claims.csv": [line]})}
        try:
            entry["claim"] = _row("claims", cells)
        except _RowError as e:
            entry["errors"].append(("csv", str(e)))
        entries.append(entry)
    counts = Counter(e["cid"] for e in entries)
    for e in entries:
        if counts[e["cid"]] > 1:
            e["errors"].append(("duplicate_claim_id", "claim_id is on more than one claims.csv row"))
    by_id = {e["cid"]: e for e in entries if counts[e["cid"]] == 1 and e["cid"] is not None}
    duplicated = {cid for cid, n in counts.items() if n > 1}

    for name in _NESTED:
        for line, cells in files[name][1]:
            cid = cells[0] if cells else None
            if cid in duplicated:
                continue
            entry = by_id.get(cid)
            if entry is None:
                result.records += 1
                result.errors.append(_error("orphan_row", f"{name}.csv row's claim_id is not in claims.csv",
                                            _safe(cid), provenance(line, {f"{name}.csv": [line]})))
                continue
            entry["parts"][f"{name}.csv"].append(line)
            try:
                row = _row(name, cells)
            except _RowError as e:
                entry["errors"].append(("csv", f"{e} (line {line})"))
                continue
            del row["claim_id"]
            if entry["claim"] is None:
                continue
            if name == "coverage":
                if "coverage" in entry["claim"]:
                    entry["errors"].append(("csv", f"more than one coverage.csv row (line {line})"))
                entry["claim"]["coverage"] = row
            else:
                entry["claim"].setdefault(name, []).append(row)

    for e in entries:
        result.records += 1
        parts = dict(e["parts"])
        if e["errors"]:
            stage, reason = e["errors"][0]
            more = len(e["errors"]) - 1
            result.errors.append(_error(stage, reason + (f"; {more} more problem(s)" if more else ""),
                                        _safe(e["cid"]), provenance(e["line"], parts)))
            continue
        # Key order of the normalized envelope: the schema's required order.
        # No coverage row leaves coverage null, which the contract rejects; no
        # child rows is an empty list, which is a known empty inventory.
        claim = {k: e["claim"].get(k, None if k == "coverage" else []) for k in _SCHEMA["required"]}
        canonical = json.dumps(claim, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        try:
            check_claim(claim)
        except ContractError as err:
            result.errors.append(_error(err.stage, err.reason, _safe(e["cid"]),
                                        provenance(e["line"], parts, _sha256(canonical))))
            continue
        result.accepted.append(Ingested(claim, provenance(e["line"], parts, _sha256(canonical)),
                                        json.dumps(claim, ensure_ascii=False).encode("utf-8")))
    return result
