# Architecture decision log

Team MedNexus | CSTAM-VELODOC ClaimGuard AI

## ADR-001 | Our code lives beside the pack, not inside it

Date / authors / commit: 2026-09-26 / Tammam Bettayeb / branch `tb/spine-skeleton`

**Context and constraint:** The starter pack ships 15 rules of which 3 are implemented, all inside one function (`base_check`) in one file (`src/engine_core.py`). Doc 06 suggests implementing further rules there. Five people must write the remaining 12 rules within one week.

**Options considered:**
1. Extend `base_check` in place, as doc 06 suggests. Simplest, matches the setup instructions, and a mentor reading the repo finds rules where his own doc says they will be.
2. A separate `claimguard/` package that imports the pack's helpers and replaces only its dispatch.
3. A separate repository for our code. Rejected immediately: `validate_pack.py` resolves its root as `parents[1]` and `config()` reads `<root>/rules`, so splitting the tree breaks both.

**Decision and rationale:** Option 2. `base_check` is a single `if`-chain; twelve rules written by four people inside it is a merge conflict per day on a seven-day budget. The pack's `src/` stays byte-identical, so `validate_pack.py` keeps verifying data integrity and release checksums, and `git diff pack-v1.0.0..HEAD` remains exact evidence of our own work.

**Data and tool permissions:** `claimguard/_pack.py` is the only module that touches `src/`. It inserts `src/` on `sys.path` once and re-exports `make_result`, `pointer`, `money`, `valid_date`, `empty`, `load_jsonl`, `config`, `validate_transport` and `STATUSES`. No other module imports from the pack. No rule mutates the claim it is given.

**Failure behaviour:** If the pack moves or is replaced, exactly one file changes. `make_result` stays authoritative for result construction: it resolves every evidence pointer against the original claim, so an evidence value can never disagree with the source and `evaluate.py`'s "Evidence value mismatch" cannot fire.

**Consequences and known limitations:** We deviate from doc 06's suggestion to implement rules in `engine_core.py`. This is a suggestion, not a rule, and `validate_pack.py`'s own checksum message anticipates intentional edits. We accept one documented deviation (the root `README.md` swap) recorded in `PACK_DELTA.md`. Anyone reading the pack's docs must be told that rules live in `claimguard/rules/`.

**Verification evidence:**
```
uv pip install -e .
python -c "from claimguard._pack import make_result, money; print(money('1510.005'))"   -> 1510.01
python -c "import claimguard; print(claimguard.__version__)"  (from /tmp)              -> 0.1.0
```

## ADR-002 | Rules self-register; nothing central lists them

Date / authors / commit: 2026-09-26 / Tammam Bettayeb / branch `tb/spine-skeleton`

**Context and constraint:** Twelve rules, three authors, one week. Any file that every author must edit becomes a conflict point and a serialization point.

**Options considered:**
1. A dict literal mapping rule IDs to functions, maintained by hand.
2. An `__init__.py` importing each rule module explicitly.
3. `@rule("Rxxx")` decorators plus `pkgutil` auto-discovery at package import.

**Decision and rationale:** Option 3. An author adds `r013.py` and it registers itself; no shared file is touched, so two people adding two rules never conflict. Options 1 and 2 both reintroduce the single-file bottleneck we left `base_check` to escape.

**Data and tool permissions:** `claimguard/rules/__init__.py` imports every module in its own package and nothing else. The registry holds callables only; it reads no data and performs no I/O.

**Failure behaviour:** The known hazard of a decorator registry is silence — an unimported module registers nothing and its rule reports `NOT_IMPLEMENTED` with no error. Two guards: auto-discovery removes the "forgot to add the import" case, and `rule()` raises `RuntimeError` on a duplicate registration rather than overwriting. The runner iterates `config()['rules']`, so a genuinely absent implementation still emits exactly one `NOT_IMPLEMENTED` result and the claim-rule pair count stays at 15.

**Consequences and known limitations:** Modules whose names start with an underscore are skipped, which is how `rules/_template.py` ships without registering. Import order across rule modules is not guaranteed, so no rule may depend on another at import time. Cross-rule dependencies (R009 reads R008's per-line outcome) are handled at evaluation time through `RuleContext.prior`, not through imports.

**Verification evidence:**
```
python -c "import claimguard.rules; from claimguard.engine.registry import REGISTRY; print(sorted(REGISTRY))"  -> []
```
Empty is the expected result before any rule module exists, and proves discovery runs without finding anything.

## ADR-003 | One accumulator owns precedence, messages and evidence

Date / authors / commit: 2026-09-26 / Tammam Bettayeb / branch `tb/spine-skeleton`

**Context and constraint:** The three baseline rules each re-implement the same logic with three different accumulator styles: R003 keeps lists of failures and unknowns, R006 a boolean `missing` flag, R001 a path list with a default substituted on PASS. Twelve more rules by three authors would produce twelve more variations of the precedence law, and the scorer rejects results for missing evidence, blank explanations and foreign line IDs.

**Options considered:**
1. Each rule returns a complete result dict via `make_result`, as the baseline does.
2. A shared helper function for precedence only.
3. A `Findings` accumulator that owns precedence, message composition, evidence ordering and line-ID ordering, and asserts the scorer's remaining rejection conditions.

**Decision and rationale:** Option 3. Every rule follows the same five moves (seed evidence, accumulate, apply precedence, compose the message, build the result); only the second varies. Centralising the other four makes precedence impossible to get wrong per rule and turns four `evaluate.py` rejections into assertion failures inside our own tests, with a stack trace pointing at the rule responsible.

Two conventions are taken from the gold data rather than chosen: across 9,000 public expected results, `affected_line_ids` appear only on FAIL (never on UNABLE_TO_ASSESS, PASS or NOT_APPLICABLE), and multi-line IDs are always in claim line order (62 of 62). So `unknown()` accepts no line ID, and `verdict()` orders line IDs by claim position whatever the call order.

**Data and tool permissions:** `Findings` reads the `RuleContext` it was given and nothing else. It performs no I/O.

**Failure behaviour:** `verdict()` raises `AssertionError` for an invalid status, a blank message, empty evidence or a line ID not in the claim. A rule that cannot produce a valid result fails loudly in tests instead of producing a run that `evaluate.py` rejects wholesale.

**Consequences and known limitations:** Rules whose baseline messages are fixed strings (R001, R006) pass `message=` to override composition. Byte-identical reproduction of the baseline output is the acceptance test for this design (Block D).

**Verification evidence:** `tests/test_engine.py` encodes the full `verdict()` contract as 15 tests marked `expectedFailure` until Block C1 implements it.
