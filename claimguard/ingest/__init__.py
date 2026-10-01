"""Role 5 — ingestion adapters: JSONL, CSV, FHIR R4 bundles; input hashing,
provenance and graceful handling of malformed input.

    result = read_jsonl("data/development/claims.jsonl")
    for item in result.accepted:      # Ingested(claim, provenance, raw)
        ...                           # run the 15 rules on item.claim
    result.errors                     # ingestion-error records, reported separately
"""
from .contract import ContractError, check_claim
from .csv_folder import read_csv_folder
from .fhir import read_fhir
from .jsonl import ADAPTER, ADAPTER_VERSION, IngestResult, Ingested, Provenance, read_jsonl

__all__ = [
    "ADAPTER", "ADAPTER_VERSION", "ContractError", "IngestResult", "Ingested",
    "Provenance", "check_claim", "read_csv_folder", "read_fhir", "read_jsonl",
]
