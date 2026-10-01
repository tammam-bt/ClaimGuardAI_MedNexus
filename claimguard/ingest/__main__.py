"""Split a claims file into accepted claims and ingestion errors.

    python -m claimguard.ingest --input data/stress/claims.jsonl
    python -m claimguard.ingest --input data/stress/csv
    python -m claimguard.ingest --input data/stress/fhir_bundles.jsonl \\
        --sidecar data/stress/claims.jsonl

A file reads normalized JSONL; the accepted file holds each accepted line's
original bytes, unchanged, so the pack's run_baseline.py and evaluate.py can
read it and every evidence value still matches. A folder reads its CSV export
(claimguard/ingest/csv_folder.py). With --sidecar, the input is FHIR bundles
completed from the normalized file (claimguard/ingest/fhir.py). For CSV and
FHIR the accepted file holds the envelopes built. The errors file holds one
ingestion-error record per rejected claim or row. Exits 0 even when some are
rejected: a malformed claim is reported, not fatal.
"""
import argparse
import json
from pathlib import Path

from .csv_folder import read_csv_folder
from .fhir import read_fhir
from .jsonl import read_jsonl


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--input", required=True)
    p.add_argument("--sidecar", help="normalized claims file; makes --input FHIR bundles")
    p.add_argument("--accepted", default="outputs/accepted.jsonl")
    p.add_argument("--errors", default="outputs/ingestion_errors.jsonl")
    a = p.parse_args(argv)

    if a.sidecar or Path(a.input).is_dir():
        result = read_fhir(a.input, a.sidecar) if a.sidecar else read_csv_folder(a.input)
        accepted = "".join(json.dumps(i.claim, ensure_ascii=False) + "\n" for i in result.accepted).encode("utf-8")
    else:
        result = read_jsonl(a.input)
        accepted = b"".join(item.raw + b"\n" for item in result.accepted)
    for path in (a.accepted, a.errors):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(a.accepted).write_bytes(accepted)
    Path(a.errors).write_text("".join(json.dumps(e) + "\n" for e in result.errors), encoding="utf-8")
    print(json.dumps(result.summary(), indent=2))


if __name__ == "__main__":
    main()
