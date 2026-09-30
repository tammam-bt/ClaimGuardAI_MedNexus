"""Split a claims file into accepted claims and ingestion errors.

    python -m claimguard.ingest --input data/stress/claims.jsonl \\
        --accepted outputs/accepted.jsonl --errors outputs/ingestion_errors.jsonl

The accepted file holds each accepted line's original bytes, unchanged, so the
pack's run_baseline.py and evaluate.py can read it and every evidence value
still matches. The errors file holds one ingestion-error record per rejected
line. Exits 0 even when lines are rejected: a malformed claim is reported, not
fatal.
"""
import argparse
import json
from pathlib import Path

from .jsonl import read_jsonl


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--input", required=True)
    p.add_argument("--accepted", default="outputs/accepted.jsonl")
    p.add_argument("--errors", default="outputs/ingestion_errors.jsonl")
    a = p.parse_args(argv)

    result = read_jsonl(a.input)
    for path in (a.accepted, a.errors):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(a.accepted).write_bytes(b"".join(item.raw + b"\n" for item in result.accepted))
    Path(a.errors).write_text("".join(json.dumps(e) + "\n" for e in result.errors), encoding="utf-8")
    print(json.dumps(result.summary(), indent=2))


if __name__ == "__main__":
    main()
