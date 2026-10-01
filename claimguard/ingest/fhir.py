"""FHIR R4 bundles to ClaimGuard envelopes (U1.4), degrading gracefully (U6.5).

Doc 11: the bundles are educational projections of the normalized envelope,
and "FHIR files alone are insufficient to reproduce all 15 checks". Each
bundle is mapped to an envelope; the three parts FHIR does not carry come
from the normalized claim with the same ID (doc 12: "The normalized envelope
is the authoritative sidecar"):

    schema_version, notes        not in the projection
    authorizations               only their IDs are (Claim.insurance.preAuthRef);
                                 the records come from the sidecar, and their
                                 IDs must equal preAuthRef

Everything else is read from FHIR (mapping below, verified on all 600 public
bundles). The FHIR-built envelope must then equal the sidecar claim field for
field, with the same JSON types. A difference is an ingestion error naming
the field, never repaired: one of the two files is wrong, and choosing would
be guessing (doc 04: "Do not silently trim or repair source data"). So an
accepted envelope's evidence values match the normalized file the scorer reads.

    claim_id            Claim.id
    invoice_number      Claim.identifier[system=.../ids/invoice].value, else null
    patient_id          Claim.patient -> Patient.id
    member_id           Patient.identifier[system=.../ids/member].value, else null
    provider_id         Claim.provider -> Organization.id
    payer_id            Claim.insurer -> Organization.id
    policy_id           Coverage.class[type=plan].value
    diagnosis_code      Claim.diagnosis[0].diagnosisCodeableConcept.coding[0].code, else null
    submission_date     Claim.created
    currency            Claim.total.currency
    total_amount        Claim.total.value
    coverage            Claim.insurance[0].coverage -> Coverage: id, status,
                        beneficiary -> Patient.id, subscriberId (else null),
                        period.start / period.end (else null)
    lines[i]            Claim.item[i]: "L" + sequence, productOrService code,
                        servicedDate, modifier code, quantity.value,
                        unitPrice.value, net.value (each null when absent),
                        line-authorization-id extension (else null)
    attachments[i]      Claim.supportingInfo[i] -> DocumentReference: id,
                        type code, subject -> Patient.id, service code from
                        description ("Synthetic <code>"), context.period.start,
                        docStatus (final -> final, preliminary -> draft),
                        base64 text/plain content decoded as UTF-8

The service code of a document is only in its description: a convention of
this projection, not FHIR. Any bundle outside this shape is an ingestion error
with stage "fhir" and a reason that names the element, never its value.
"""
import base64
import binascii
from pathlib import Path

from .contract import ContractError, check_claim
from .jsonl import (
    _SAFE_ID, IngestResult, Ingested, Provenance, _error, _parse, _sha256, read_jsonl,
)

ADAPTER = "fhir"
ADAPTER_VERSION = "1.0.0"

_BASE = "https://claimguard.example/"
_INVOICE = _BASE + "ids/invoice"
_MEMBER = _BASE + "ids/member"
_LINE_AUTH = _BASE + "StructureDefinition/line-authorization-id"
_DOC_STATUS = {"final": "final", "preliminary": "draft"}
_FROM_SIDECAR = ("schema_version", "notes", "authorizations")


def _fail(reason):
    raise ContractError("fhir", reason)


def _obj(v, what):
    if not isinstance(v, dict):
        _fail(f"{what} must be an object")
    return v


def _list(v, what, nonempty=False):
    if not isinstance(v, list) or (nonempty and not v):
        _fail(f"{what} must be a {'nonempty ' if nonempty else ''}list")
    return v


def _get(obj, key, what):
    if key not in _obj(obj, what):
        _fail(f"{what}.{key} is missing")
    return obj[key]


def _code(concept, what):
    coding = _list(_get(concept, "coding", what), f"{what}.coding", nonempty=True)
    return _get(coding[0], "code", f"{what}.coding[0]")


def _resolve(index, ref, rtype, what):
    url = _get(ref, "reference", what)
    if url not in index:
        _fail(f"{what} does not resolve in the bundle")
    resource = index[url]
    if resource.get("resourceType") != rtype:
        _fail(f"{what} does not point to a {rtype}")
    return resource


def _ref_id(index, ref, rtype, what):
    """The ID a reference names. Doc 11: some records deliberately reference
    a patient outside the bundle, a business inconsistency for the rules to
    find, not a malformed bundle. So a reference that resolves must point to
    the right type; one that does not is read from its URL, .../<rtype>/<id>."""
    url = _get(ref, "reference", what)
    if url in index:
        return _get(_resolve(index, ref, rtype, what), "id", rtype)
    if not isinstance(url, str) or url.rsplit("/", 2)[-2:-1] != [rtype] or not url.rsplit("/", 1)[-1]:
        _fail(f"{what} is not a reference to a {rtype}")
    return url.rsplit("/", 1)[-1]


def _identifier(resource, system):
    values = [i.get("value") for i in _list(resource.get("identifier", []), "identifier")
              if isinstance(i, dict) and i.get("system") == system]
    if len(values) > 1:
        _fail(f"more than one identifier of system {system}")
    return values[0] if values else None


def _value(item, key, what):
    return _obj(item[key], f"{what}.{key}").get("value") if key in item else None


def _index(bundle):
    _obj(bundle, "bundle")
    if bundle.get("resourceType") != "Bundle" or bundle.get("type") != "collection":
        _fail("not a Bundle of type collection")
    index, claims = {}, []
    for n, entry in enumerate(_list(_get(bundle, "entry", "Bundle"), "Bundle.entry", nonempty=True)):
        url = _get(entry, "fullUrl", f"entry[{n}]")
        resource = _obj(_get(entry, "resource", f"entry[{n}]"), f"entry[{n}].resource")
        if not isinstance(url, str) or url in index:
            _fail(f"entry[{n}].fullUrl is not a unique string")
        index[url] = resource
        if resource.get("resourceType") == "Claim":
            claims.append(resource)
    if len(claims) != 1:
        _fail("bundle must hold exactly one Claim")
    return index, claims[0]


def _coverage(index, claim):
    insurance = _list(_get(claim, "insurance", "Claim"), "Claim.insurance", nonempty=True)
    cov = _resolve(index, _get(insurance[0], "coverage", "Claim.insurance[0]"), "Coverage",
                   "Claim.insurance[0].coverage")
    plans = [c.get("value") for c in _list(_get(cov, "class", "Coverage"), "Coverage.class")
             if isinstance(c, dict) and isinstance(c.get("type"), dict)
             and _code(c["type"], "Coverage.class.type") == "plan"]
    if len(plans) != 1:
        _fail("Coverage must have exactly one plan class")
    period = _obj(cov.get("period", {}), "Coverage.period")
    record = {
        "coverage_id": _get(cov, "id", "Coverage"),
        "status": cov.get("status"),
        "beneficiary_patient_id": _ref_id(index, _get(cov, "beneficiary", "Coverage"), "Patient",
                                          "Coverage.beneficiary"),
        "member_id": cov.get("subscriberId"),
        "start_date": period.get("start"),
        "end_date": period.get("end"),
    }
    pre = _list(insurance[0].get("preAuthRef", []), "Claim.insurance[0].preAuthRef")
    return record, plans[0], pre


def _lines(claim):
    lines, seen = [], set()
    for n, item in enumerate(_list(_get(claim, "item", "Claim"), "Claim.item", nonempty=True)):
        what = f"Claim.item[{n}]"
        seq = _get(item, "sequence", what)
        if isinstance(seq, bool) or not isinstance(seq, int) or seq < 1 or seq in seen:
            _fail(f"{what}.sequence must be a unique positive integer")
        seen.add(seq)
        auth = [e.get("valueString") for e in _list(item.get("extension", []), f"{what}.extension")
                if isinstance(e, dict) and e.get("url") == _LINE_AUTH]
        if len(auth) > 1:
            _fail(f"{what} has more than one authorization extension")
        modifier = _list(item["modifier"], f"{what}.modifier", nonempty=True) if "modifier" in item else None
        lines.append({
            "line_id": f"L{seq}",
            "service_code": _code(_get(item, "productOrService", what), f"{what}.productOrService"),
            "service_date": item.get("servicedDate"),
            "modifier": _code(modifier[0], f"{what}.modifier[0]") if modifier else None,
            "quantity": _value(item, "quantity", what),
            "unit_price": _value(item, "unitPrice", what),
            "net_amount": _value(item, "net", what),
            "authorization_id": auth[0] if auth else None,
        })
    return lines


def _attachments(index, claim):
    out = []
    for n, info in enumerate(_list(claim.get("supportingInfo", []), "Claim.supportingInfo")):
        what = f"Claim.supportingInfo[{n}]"
        doc = _resolve(index, _get(info, "valueReference", what), "DocumentReference", f"{what}.valueReference")
        description = _get(doc, "description", "DocumentReference")
        if not isinstance(description, str) or not description.startswith("Synthetic "):
            _fail("DocumentReference.description does not carry a service code")
        status = _get(doc, "docStatus", "DocumentReference")
        if status not in _DOC_STATUS:
            _fail("DocumentReference.docStatus is not final or preliminary")
        content = _list(_get(doc, "content", "DocumentReference"), "DocumentReference.content", nonempty=True)
        attachment = _get(content[0], "attachment", "DocumentReference.content[0]")
        if _get(attachment, "contentType", "attachment") != "text/plain":
            _fail("DocumentReference attachment is not text/plain")
        try:
            text = base64.b64decode(_get(attachment, "data", "attachment"), validate=True).decode("utf-8")
        except (binascii.Error, ValueError, TypeError):
            _fail("DocumentReference attachment data is not base64 UTF-8 text")
        period = _obj(_get(_obj(_get(doc, "context", "DocumentReference"), "DocumentReference.context"),
                           "period", "DocumentReference.context"), "DocumentReference.context.period")
        out.append({
            "attachment_id": _get(doc, "id", "DocumentReference"),
            "type": _code(_get(doc, "type", "DocumentReference"), "DocumentReference.type"),
            "patient_id": _ref_id(index, _get(doc, "subject", "DocumentReference"), "Patient",
                                  "DocumentReference.subject"),
            "service_code": description[len("Synthetic "):],
            "service_date": period.get("start"),
            "document_status": _DOC_STATUS[status],
            "text": text,
        })
    return out


def map_bundle(bundle):
    """(envelope fields read from FHIR, authorization IDs from preAuthRef).
    Raises ContractError(stage 'fhir') for any bundle outside the projection."""
    index, claim = _index(bundle)
    if not isinstance(_get(claim, "id", "Claim"), str) or not claim["id"]:
        _fail("Claim.id must be a nonempty string")
    patient = _resolve(index, _get(claim, "patient", "Claim"), "Patient", "Claim.patient")
    coverage, policy_id, pre_auth = _coverage(index, claim)
    total = _obj(_get(claim, "total", "Claim"), "Claim.total")
    diagnosis = _list(claim.get("diagnosis", []), "Claim.diagnosis")
    return {
        "claim_id": _get(claim, "id", "Claim"),
        "invoice_number": _identifier(claim, _INVOICE),
        "patient_id": _get(patient, "id", "Patient"),
        "member_id": _identifier(patient, _MEMBER),
        "provider_id": _ref_id(index, _get(claim, "provider", "Claim"), "Organization", "Claim.provider"),
        "payer_id": _ref_id(index, _get(claim, "insurer", "Claim"), "Organization", "Claim.insurer"),
        "policy_id": policy_id,
        "diagnosis_code": _code(_get(diagnosis[0], "diagnosisCodeableConcept", "Claim.diagnosis[0]"),
                                "Claim.diagnosis[0].diagnosisCodeableConcept") if diagnosis else None,
        "submission_date": _get(claim, "created", "Claim"),
        "currency": _get(total, "currency", "Claim.total"),
        "total_amount": total.get("value"),
        "coverage": coverage,
        "lines": _lines(claim),
        "attachments": _attachments(index, claim),
    }, pre_auth


def _first_difference(a, b, path=""):
    """JSON pointer of the first place a and b differ, by value or JSON type
    (1 == 1.0 == True in Python, but not in a claim)."""
    if type(a) is not type(b):
        return path or "/"
    if isinstance(a, dict):
        for k in a.keys() | b.keys():
            if k not in a or k not in b:
                return f"{path}/{k}"
            d = _first_difference(a[k], b[k], f"{path}/{k}")
            if d:
                return d
        return None
    if isinstance(a, list):
        if len(a) != len(b):
            return path
        for i, (x, y) in enumerate(zip(a, b)):
            d = _first_difference(x, y, f"{path}/{i}")
            if d:
                return d
        return None
    return None if a == b else (path or "/")


def merge(fhir, pre_auth, sidecar):
    """The envelope: FHIR fields plus the sidecar's three, in the sidecar's
    key order. Raises ContractError(stage 'fhir_mismatch') on any difference."""
    if [a.get("authorization_id") if isinstance(a, dict) else None
            for a in sidecar["authorizations"]] != pre_auth:
        raise ContractError("fhir_mismatch", "authorization IDs differ from Claim.insurance.preAuthRef")
    envelope = {k: (sidecar[k] if k in _FROM_SIDECAR else fhir[k]) for k in sidecar}
    diff = _first_difference(envelope, sidecar)
    if diff:
        raise ContractError("fhir_mismatch", f"FHIR and sidecar differ at {diff}")
    return envelope


def _peek_claim_id(bundle):
    """The Claim's ID for an error record, if it can be read safely."""
    try:
        ids = [e["resource"]["id"] for e in bundle["entry"] if e["resource"]["resourceType"] == "Claim"]
    except (TypeError, KeyError, AttributeError):
        return None
    if len(ids) == 1 and isinstance(ids[0], str) and _SAFE_ID.fullmatch(ids[0]):
        return ids[0]
    return None


def read_fhir(bundles_path, sidecar_path):
    """Ingest FHIR bundles, completed from the normalized sidecar file. Never
    raises for a bad bundle; raises only if a file cannot be read."""
    sidecar = read_jsonl(sidecar_path)
    by_id = {item.claim["claim_id"]: item for item in sidecar.accepted}
    data = Path(bundles_path).read_bytes()
    result = IngestResult(source=str(bundles_path), source_sha256=_sha256(data),
                          adapter=ADAPTER, adapter_version=ADAPTER_VERSION)
    seen = set()
    for number, raw in enumerate(data.splitlines(), start=1):
        claim_id, side = None, None
        provenance = Provenance(ADAPTER, ADAPTER_VERSION, result.source, result.source_sha256,
                                number, _sha256(raw))
        try:
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                raise ContractError("decode", "not valid UTF-8") from None
            if not text.strip():
                continue
            bundle = _parse(text)
            claim_id = _peek_claim_id(bundle)
            try:
                fhir, pre_auth = map_bundle(bundle)
            except ContractError:
                raise
            except RecursionError:
                raise ContractError("fhir", "bundle nested too deeply") from None
            except (TypeError, AttributeError, KeyError, IndexError, ValueError) as e:
                # A shape the checks above did not foresee: still an error
                # record, never a crash of the whole run.
                raise ContractError("fhir", f"malformed bundle ({type(e).__name__})") from None
            cid = fhir["claim_id"]
            if cid in seen:
                raise ContractError("duplicate_claim_id", "claim_id already read on an earlier line")
            side = by_id.get(cid) if isinstance(cid, str) else None
            if side is None:
                raise ContractError("fhir_mismatch", "no accepted sidecar claim with this claim_id")
            provenance = Provenance(ADAPTER, ADAPTER_VERSION, result.source, result.source_sha256,
                                    number, _sha256(raw),
                                    {"source": sidecar.source, "source_sha256": sidecar.source_sha256,
                                     "line_number": side.provenance.line_number})
            envelope = merge(fhir, pre_auth, side.claim)
            check_claim(envelope)
            seen.add(cid)
        except ContractError as e:
            result.records += 1
            result.errors.append(_error(e.stage, e.reason, claim_id, provenance))
            continue
        result.records += 1
        result.accepted.append(Ingested(envelope, provenance, raw))
    return result
