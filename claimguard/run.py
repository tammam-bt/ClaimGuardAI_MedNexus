"""One command, the whole pipeline:

    python -m claimguard.run --input data/development/claims.jsonl --output outputs/dev_predictions.jsonl

  ingest   claimguard.ingest: a JSONL file, a CSV folder, or FHIR bundles with
           --sidecar. A bad line, row or bundle is an ingestion error: recorded
           with its line and stage, skipped, never fatal.
  rules    all 15 rules on every accepted claim. --output is the file
           src/evaluate.py scores; the interface matches src/run_baseline.py.
  screen   the injection pre-filter on every accepted claim (flags only).
  explain  with --explain, the AI explainer on FAIL and UNABLE_TO_ASSESS
           results, watchdog-guarded, written to <output>.explanations.jsonl,
           never into the scored results.
  record   the run manifest, <output>.manifest.json.

Exit code 0: every record ingested and every rule ran. 2: something was
rejected or a rule failed; the manifest lists each one.
"""
import argparse
import hashlib
import json
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

import claimguard
from claimguard.ai import explain_run
from claimguard.audit import chain
from claimguard.audit.manifest import build_manifest
from claimguard.engine.runner import Engine
from claimguard.guards import screen
from claimguard.ingest import read_csv_folder, read_fhir, read_jsonl


def ingest(input_path, sidecar=None):
    """The adapter the input calls for: FHIR with a sidecar, CSV for a folder, else JSONL."""
    if sidecar:
        return read_fhir(input_path, sidecar)
    if Path(input_path).is_dir():
        return read_csv_folder(input_path)
    return read_jsonl(input_path)


def _write_jsonl(path, rows: Iterable[Dict[str, Any]]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Ingest, check, screen and optionally explain claims.")
    p.add_argument("--input", default="data/development/claims.jsonl",
                   help="JSONL file, CSV folder, or FHIR bundles (with --sidecar)")
    p.add_argument("--sidecar", help="normalized claims file; makes --input FHIR bundles")
    p.add_argument("--output", default="outputs/predictions.jsonl")
    p.add_argument("--manifest", help="run manifest path (default: <output>.manifest.json)")
    p.add_argument("--explain", action="store_true", help="write AI explanations to <output>.explanations.jsonl")
    p.add_argument("--limit", type=int, help="evaluate only the first N accepted claims")
    p.add_argument("--strict", action="store_true", help="re-raise rule exceptions (tests and CI)")
    p.add_argument("--audit-log", help="append this run's events to a hash chain")
    p.add_argument("--anchor", help="chain-head anchor (default: <audit-log>.head.json)")
    a = p.parse_args(argv)
    anchor = (a.anchor or chain.default_anchor(a.audit_log)) if a.audit_log else None

    run_id = uuid.uuid4().hex
    started = time.perf_counter()
    engine = Engine(strict=a.strict)
    ingested = ingest(a.input, a.sidecar)
    events: List[Dict[str, Any]] = [{
        "event": "run_started", "input_sha256": ingested.source_sha256,
        "engine_version": claimguard.__version__,
        "rule_versions": {r["rule_id"]: r["version"] for r in engine.cfg["rules"]},
        "policy_versions": {k: v["version"] for k, v in engine.cfg["policies"].items()},
    }, *ingested.errors]
    accepted = ingested.accepted if a.limit is None else ingested.accepted[: a.limit]
    claims = [item.claim for item in accepted]

    results: List[Dict[str, Any]] = [r for claim in claims for r in engine.evaluate_claim(claim)]
    _write_jsonl(a.output, results)
    injection_flags = [s.as_event() for s in map(screen, claims) if s.flagged]
    events += injection_flags

    ai, explanations_path = None, None
    if a.explain:
        records, failures, summary = explain_run(results, {c["claim_id"]: c for c in claims},
                                                 {r["rule_id"]: r for r in engine.cfg["rules"]})
        explanations_path = f"{a.output}.explanations.jsonl"
        _write_jsonl(explanations_path, records)
        ai = {"summary": summary, "model_failures": failures}
        events += failures

    manifest = build_manifest(engine=engine, run_id=run_id, ingested=ingested, accepted=accepted,
                              results=results, injection_flags=injection_flags, ai=ai,
                              duration_ms=round((time.perf_counter() - started) * 1000),
                              results_path=a.output, explanations_path=explanations_path)
    manifest_path = Path(a.manifest) if a.manifest else Path(f"{a.output}.manifest.json")
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if a.audit_log:
        summary_in = ingested.summary()
        events.append({
            "event": "run_finished", "records": summary_in["records"], "accepted": summary_in["accepted"],
            "rejected": summary_in["rejected"], "results": len(results), "statuses": manifest["statuses"],
            "rule_errors": len(engine.errors), "injection_flags": len(injection_flags),
            "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        })
        chain.append(a.audit_log, [{**e, "run_id": run_id} for e in events], anchor)

    print(f"{len(claims)} claims checked, {len(ingested.errors)} rejected at ingestion, "
          f"{len(injection_flags)} flagged for injection, {len(engine.errors)} rule errors. "
          f"Results: {a.output}  Manifest: {manifest_path}")
    return 2 if ingested.errors or engine.errors else 0

if __name__ == "__main__":
    raise SystemExit(main())
