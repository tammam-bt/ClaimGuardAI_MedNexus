"""Scan a claims file for instruction-like text.

    python -m claimguard.guards --input data/stress/claims.jsonl \\
        --output outputs/injection_flags.jsonl

Writes one injection_flag event per flagged claim. Reads the file with the
pack's own loader, so it expects a file that has passed ingestion. Changes no
claim and no result: flagged claims are still checked by all 15 rules.
"""
import argparse
import json
from pathlib import Path

from claimguard._pack import load_jsonl

from .injection import SCANNER_VERSION, screen


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--input", required=True)
    p.add_argument("--output", default="outputs/injection_flags.jsonl")
    a = p.parse_args(argv)

    claims = load_jsonl(a.input)
    flagged = [s for s in map(screen, claims) if s.flagged]
    out = Path(a.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(json.dumps(s.as_event()) + "\n" for s in flagged), encoding="utf-8")
    print(json.dumps({"scanner_version": SCANNER_VERSION, "claims": len(claims),
                      "flagged": len(flagged), "output": str(out)}, indent=2))


if __name__ == "__main__":
    main()
