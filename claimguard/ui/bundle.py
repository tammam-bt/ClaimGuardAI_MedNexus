"""Everything the review interface shows, gathered from one run's files.

The interface is a static page, so it cannot read files or run Python. This
module collects what a run produced, computes what the run does not write
down, and returns one JSON-ready dict that the page embeds:

    run          the run manifest, as written by python -m claimguard.run
    rules        rules/rules.json, with each rule's implemented flag from the
                 manifest
    policies     rules/policies.json (limits shown beside R013, R014, R015)
    claims       per accepted claim: the claim as received, its input hash
                 (the hash review decisions and versions refer to), its
                 provenance, its 15 results, its route, its AI explanations
                 and its injection flag
    rejected     the ingestion errors: claims that never reached the rules
    audit        the hash-chained audit log, if one was given: its events and
                 whether it verifies against its anchor
    evaluation   per-rule metrics, confusion matrices and mismatches against
                 the expected results, if a gold file was given
    corrections  if a corrections folder was given (python -m
                 claimguard.review.correct --output): each claim's newer
                 versions, with their results, status changes and route
    rbac         the permission matrix of claimguard.guards.rbac
    routing      the routing policy version

Routes are computed here from the results (claimguard.review.routing), never
read from an older routing file, which could belong to another run. Nothing
is invented: a section whose source was not given is null, and the page
shows that it is missing.
"""
import json
from pathlib import Path

import claimguard
from claimguard._pack import config, load_jsonl
from claimguard.audit import chain
from claimguard.evaluation.confusion import confusion_by_rule
from claimguard.guards.rbac import PERMISSIONS
from claimguard.review.correction import original
from claimguard.review.routing import ROUTING_POLICY_VERSION, route_claim, route_run

ROOT = Path(__file__).resolve().parents[2]
BUNDLE_VERSION = "1.0.0"


def _read_jsonl(path):
    path = Path(path)
    return load_jsonl(path) if path.exists() else None


def _audit(log, anchor):
    if not log or not Path(log).exists():
        return None
    anchor = anchor or chain.default_anchor(log)
    rows = load_jsonl(log)
    try:
        head, count = chain.verify(log, anchor)
        verdict = {"valid": True, "head": head, "count": count, "error": None}
    except chain.AuditError as e:
        verdict = {"valid": False, "head": None, "count": len(rows), "error": str(e)}
    return {"log": str(log), "anchored": Path(anchor).exists(), **verdict, "events": rows}


def _corrections(folder, claims):
    """Attach each version written by claimguard.review.correct to its claim,
    following the chain: version 2's parent is this run's version of the
    claim, version 3's parent is version 2, and so on. A version whose parent
    is in neither belongs to another run: it is listed as skipped, not shown."""
    skipped = []
    if not folder:
        return skipped
    by_hash = {c["input_hash"]: c for c in claims}
    loaded = [(path, json.loads(path.read_text(encoding="utf-8"))) for path in sorted(Path(folder).glob("*.json"))]
    number = lambda r: r.get("version") if isinstance(r.get("version"), int) else 0
    for path, record in sorted(loaded, key=lambda item: number(item[1])):  # parents before children
        entry = by_hash.get(record.get("parent_hash"))
        if entry is None or entry["claim"]["claim_id"] != record.get("claim_id"):
            skipped.append({"file": path.name, "why": "its parent is not this run's version of the claim"})
            continue
        entry["versions"].append({**record, "route": route_claim(record["results"])})
        by_hash[record["input_hash"]] = entry
    for c in claims:
        c["versions"].sort(key=lambda v: v["version"])
    return skipped


def build(results_path, claims_path, *, manifest_path=None, explanations_path=None,
          audit_log=None, anchor=None, gold_path=None, corrections=None):
    """The interface's data for one run. results_path is the run's --output."""
    results = load_jsonl(results_path)
    manifest_path = Path(manifest_path or f"{results_path}.manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else None
    explanations = _read_jsonl(explanations_path or f"{results_path}.explanations.jsonl")

    claims_in = {c["claim_id"]: c for c in load_jsonl(claims_path)}
    by_claim = {}
    for r in results:
        by_claim.setdefault(r["claim_id"], []).append(r)
    unknown = sorted(set(by_claim) - set(claims_in))
    if unknown:
        raise ValueError(f"{len(unknown)} result claim(s) are not in the claims file, e.g. {unknown[0]}")

    routes = {r["claim_id"]: r for r in route_run(results)}
    provenance = {c["claim_id"]: c for c in (manifest or {}).get("claims", [])}
    flags = {f["claim_id"]: f for f in (manifest or {}).get("injection_flags", [])}
    expl_by_claim = {}
    for e in explanations or []:
        expl_by_claim.setdefault(e["claim_id"], []).append(e)

    claims = []
    for cid, rows in by_claim.items():
        claim = claims_in[cid]
        claims.append({
            "claim": claim,
            "input_hash": original(claim).input_hash,
            "provenance": provenance.get(cid),
            "results": rows,
            "route": routes[cid],
            "explanations": expl_by_claim.get(cid, []) if explanations is not None else None,
            "flag": flags.get(cid),
            "versions": [],
        })
    corrections_skipped = _corrections(corrections, claims)

    cfg = config(ROOT)
    implemented = (manifest or {}).get("rules", {})
    rules = [{**r, "implemented": implemented.get(r["rule_id"], {}).get("implemented")} for r in cfg["rules"]]

    evaluation = None
    if gold_path:
        evaluation = confusion_by_rule(load_jsonl(gold_path), results, claims_in)

    return {
        "bundle_version": BUNDLE_VERSION,
        "engine_version": claimguard.__version__,
        "sources": {"results": str(results_path), "claims": str(claims_path),
                    "manifest": str(manifest_path) if manifest else None,
                    "explanations": str(explanations_path or f"{results_path}.explanations.jsonl")
                    if explanations is not None else None,
                    "audit_log": str(audit_log) if audit_log else None,
                    "gold": str(gold_path) if gold_path else None,
                    "corrections": str(corrections) if corrections else None},
        "run": manifest,
        "rules": rules,
        "policies": cfg["policies"],
        "claims": claims,
        "rejected": (manifest or {}).get("ingestion_errors", []),
        "corrections_skipped": corrections_skipped,
        "audit": _audit(audit_log, anchor),
        "evaluation": evaluation,
        "rbac": {role: sorted(actions) for role, actions in PERMISSIONS.items()},
        "routing": {"policy_version": ROUTING_POLICY_VERSION},
    }


def embed(data):
    """JSON safe to place inside <script type="application/json">: no
    character of the data can close the script element or open a comment,
    whatever text a claim carries."""
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return (text.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
            .replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))
