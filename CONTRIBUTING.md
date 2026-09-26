# How we work: team MedNexus

Read this once, fully, before your first commit. These are rules, not suggestions. Every one of them exists because breaking it costs the team time or points.

---

## 1. Setup, once

```bash
git clone https://github.com/tammam-bt/ClaimGuardAI_MedNexus.git
cd ClaimGuardAI_MedNexus

git config user.name  "Your Full Name"
git config user.email "an-email-verified-on-your-github-account"

uv venv --python 3.12
source .venv/bin/activate
uv pip install -e .          # must be -e. A plain install cannot find the pack
```

Check it works:

```bash
python src/validate_pack.py          # ends with PASS
python -m unittest discover -s tests # ends with OK
```

Then add your section to `docs/SETUP_NOTES.md` in your first PR.

**Your name and email must be right before your first commit.** Git history is our contribution log for the jury. Fixing it afterwards means rewriting history, and we will not do that.

---

## 2. Branches

- **Never commit to `main`.** It's protected: pushes are rejected and only reviewed PRs get in.
- **One branch per unit of work.** One rule, one helper, one doc. Not "R007 and R012 and a refactor".
- **Name it** `<your initials>/<what>`, lowercase, with hyphens:
  - `ab/r007-line-arithmetic`
  - `ab/test-r007-boundaries`
  - `ab/fix-r007-tolerance`
- **Always start from a fresh `main`:**

```bash
git checkout main
git pull
git checkout -b ab/r007-line-arithmetic
```

---

## 3. Where things go

| You are writing | It goes in |
|---|---|
| A rule | `claimguard/rules/rNNN.py`, copied from `claimguard/rules/_template.py` |
| Its tests | `tests/test_rNNN.py` |
| Ingestion (JSONL, CSV, FHIR) | `claimguard/ingest/` |
| AI explanation, watchdog | `claimguard/ai/` |
| A rule clarification or disagreement with a label | `docs/DECISIONS.md` |

### Never touch these

| Path | Why |
|---|---|
| `src/`, `data/`, `rules/*.json`, `schemas/`, `examples/` | The starter pack. CI fails if any byte changes |
| `claimguard/engine/`, `claimguard/_pack.py` | Shared by everyone. Change it only after talking to Tammam, in its own PR |
| `.github/` | CI and review settings |
| `claimguard/rules/rNNN.py` of someone else's rule | Ask them. Don't fix it silently |

---

## 4. Writing a rule

**Write the tests first**, from `docs/04_Rulebook.md`. At minimum: one PASS, one FAIL, one UNABLE_TO_ASSESS, plus NOT_APPLICABLE if your rule can be not applicable. Include the exact boundary: the equal date and the exact 0.01 SAR difference.

Then the rule itself. The full contract is the `Findings.verdict()` docstring in `claimguard/engine/findings.py`. Read it. The rules:

1. **Never build a result dict yourself.** Return `f.verdict(...)`. The engine builds the result, which is what keeps evidence values honest.
2. **Build paths with `ctx.path(...)`**, never by hand: `ctx.path("lines", i, "unit_price")`.
3. **Cite what you inspected, even when its value is `None`.** Every envelope and line key always exists. A path that doesn't exist raises an error naming your rule.
4. **Missing data → `f.unknown(...)`. Proven violation → `f.fail(...)`.** A known absence your rule is *about* (like R001's required fields) is a FAIL, not an unknown. Read your rule's text.
5. **`line_id` comes from `line["line_id"]`.** Never build it, and never pass one to `unknown()` (it won't let you).
6. **No policy is an unknown, not a stop.** Record it and keep checking whatever doesn't need the policy. R013 can still FAIL a negative quantity with no policy.
7. **Price and quantity limits come from `ctx.policy`**, never from `ctx.services`. They're the same numbers, and they diverge exactly on the no-policy claims.
8. **Money uses `money()`** from `claimguard._pack` (Decimal, ROUND_HALF_UP). Never compare floats.
9. **Dates are inclusive. Never read today's date or the current time.** CI rejects `date.today`, `datetime.now` and `time.time()` in rules.
10. **Never open `expected_results.jsonl` from rule code**, or special-case a claim ID. The scorer can't see it. The mentor's 200 held-out claims will.
11. **Don't mutate `ctx.claim` or `ctx.policy`.** The policy is frozen and will raise if you try.
12. **Two rules firing on one claim is normal.** R008 + R009 and R007 + R012 check different things. Don't "fix" it.

---

## 5. Commits

- Small and often. Each commit should run.
- Message format: `type(area): what`, for example:
  - `feat(rules): R007 line arithmetic`
  - `test(rules): R007 tolerance boundaries`
  - `fix(rules): R007 treat 0.01 difference as a pass`
- **Never commit** `.env`, API keys, `outputs/`, `.venv/`, or any real patient data. `.gitignore` covers the common ones; you're responsible for the rest.

---

## 6. Pull requests

```bash
git push -u origin ab/r007-line-arithmetic
```

Then **Compare & pull request** on GitHub. The description template fills in automatically. Complete every section.

- **CI must be green** before review. Red PRs aren't reviewed.
- **Tammam is requested automatically** (CODEOWNERS). Don't ping for every push; reviews happen at the times posted in the team channel.
- **Review comments:** fix them on the **same branch** and push again. Don't open a new PR, and don't force-push once review has started, because that erases what was reviewed.
- **`main` moved on while you worked?** Click **Update branch** on the PR, or run `git merge origin/main`. Don't rebase a branch you've already pushed.
- **Only Tammam merges.** After the merge, delete your branch and start the next one from a fresh `main`.

---

## 7. AI tools

The CSTAM rules allow them, with conditions: **you must understand, validate and be able to explain every line**, because the jury asks in Q&A. So:

- Don't commit code you can't explain.
- Say it in the PR: the template asks whether AI was used, and for what.

That answer becomes our contribution log.

---

## 8. When something goes wrong

| Situation | Do this |
|---|---|
| Committed on `main` locally by mistake | `git branch ab/rescue && git reset --hard origin/main && git checkout ab/rescue`. Your work is now on a branch |
| Pushed a secret or real data | **Tell Tammam immediately.** Don't try to delete it yourself. Rotate the key |
| Your rule disagrees with an expected result | Build the smallest failing example, quote the rule's exact wording, write it in `docs/DECISIONS.md`, and raise it with the mentor. Never change the code to match the label |
| CI fails and you don't know why | Open the failed step's log on the PR. If still stuck, post the claim ID, rule ID, expected vs actual status, and the command you ran |
| Stuck on a rule for over an hour | Ask in the team channel with that same information. Screenshots and "it doesn't work" can't be answered |
