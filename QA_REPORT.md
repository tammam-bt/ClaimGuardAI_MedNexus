# ClaimGuard AI starter pack | Release QA

Version 1.0.0 | 17 September 2026

## Completed checks

- 800 unique synthetic claims across public and mentor-held splits; no overlapping claim, patient or non-null invoice IDs.
- 12,000 complete claim-rule labels checked; 9,000 public and 3,000 mentor-held.
- Transport shapes and every keyword used by the supplied input/result schemas checked by the pack's limited schema validator.
- All four relational CSV exports rebuild exactly to the normalized JSON envelopes.
- Result evidence paths and values resolve to original claim data. Every claim has exactly 15 labeled rule outcomes.
- All 15 rules have positive issue examples in both development and validation.
- 11 student tests passed: missing information, coverage boundaries, uncertainty, duplicate/modifier handling, incomplete output visibility, scorer rejection, audit tampering and explanation citations.
- 30 independent hand-written reference tests passed across all 15 rules, including decimal tolerance and authorization aggregation. These tests do not use the dataset generator.
- Student CLI, scorer, report generator and mentor reference CLI executed successfully.
- Review-page JavaScript syntax and filter/decision/download flow checked in a minimal DOM simulation; exported event successfully imported and verified by the audit tool.
- 23-page handbook rendered and visually inspected; contents links, tables and chapter flow checked.
- Student content scanned for hidden claim IDs and mentor reference code; neither is included.

## Limits of these checks

No full HL7 validator, terminology server or national payer profile was run. FHIR files are teaching projections and do not contain all rule inputs. The custom schema validator implements only the keywords present in the supplied schemas.

The headless browser binary was unavailable, so the UI checks use JavaScript simulation, not a full browser compatibility run. The interface is a small static HTML demo; teams should test it in their own browser. No live model was called. Model grounding remains a student evaluation task.

The reference engine reproduces labels generated from it; this consistency check alone is not independent validation. The separate 30 manual cases provide independent spot checks, but this is not a formal proof or real payer validation.

## Baseline result on development

The three-rule baseline returns 1,200 implemented results and 4,800 NOT_IMPLEMENTED results. It detects 88 of 319 expected issue pairs, with zero false alarms on this synthetic set. Overall exact status accuracy is 20%. These are starter-code measurements, not a finished-system score or business-impact estimate.

## Release integrity

SHA256SUMS.json records included files. Intentional student edits change checksums; keep an untouched original for comparison. Output folders and Python caches are excluded from distribution.
