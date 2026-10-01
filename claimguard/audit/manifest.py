"""U4.3 | The run manifest: what is needed to reproduce and audit one run.

Written beside the results, never inside them: evaluate.py rejects any result
key beyond schemas/result.schema.json. Input hashing (U1.5) and provenance
(U1.7) come from claimguard.ingest: the file's SHA-256 is in input, and every
accepted claim's own record SHA-256 and source line are in claims.
"""
import hashlib
import platform
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

import claimguard
from claimguard.engine.registry import REGISTRY

MANIFEST_VERSION = "1.0.0"


def _file_sha256(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build_manifest(*, engine, run_id: str, ingested, accepted: Sequence[Any],
                   results: Sequence[Mapping[str, Any]], injection_flags: List[Dict[str, Any]],
                   ai: Optional[Dict[str, Any]], duration_ms: int,
                   results_path, explanations_path=None) -> Dict[str, Any]:
    """The audit chain records this manifest's hash, so hashing the output
    files here ties them to the chain too."""
    summary = ai["summary"] if ai else {}
    return {
        "manifest_version": MANIFEST_VERSION,
        "run_id": run_id,
        "engine": {"name": "claimguard", "version": claimguard.__version__, "strict": engine.strict},
        "python": platform.python_version(),
        "input": ingested.summary(),
        "pack": {"sha256sums": _file_sha256(engine.root / "SHA256SUMS.json")},
        "rules": {r["rule_id"]: {"version": r["version"], "implemented": r["rule_id"] in REGISTRY}
                  for r in engine.cfg["rules"]},
        "policies": {policy_id: p["version"] for policy_id, p in engine.cfg["policies"].items()},
        "model": summary.get("model"),
        "prompt_version": summary.get("prompt_version"),
        "results": len(results),
        "outputs": {"results_sha256": _file_sha256(results_path),
                    "explanations_sha256": _file_sha256(explanations_path) if explanations_path else None},
        "statuses": dict(sorted(Counter(r["status"] for r in results).items())),
        "claims": [{"claim_id": item.claim["claim_id"], **item.provenance.as_dict()} for item in accepted],
        "ingestion_errors": list(ingested.errors),
        "rule_errors": [e._asdict() for e in engine.errors],
        "injection_flags": list(injection_flags),
        "ai": ai,
        "duration_ms": duration_ms,
    }
