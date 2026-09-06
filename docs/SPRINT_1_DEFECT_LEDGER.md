# FRONTIER — Sprint 1 Defect Ledger (`zoocode/sprint-1-intelligence`)

Mandated by `ZOOCODE_SPRINT1.md` (DEBT POLICY section). Every deferred item carries a
concrete symptom, affected files, blast radius, and recommended repair.

Sprint classification key (per sprint contract):

- **P0** — data / security / PIT / epistemic corruption
- **P1** — major broken capability or non-replayable behavior
- **P2** — material UX / performance / maintainability issue
- **POLISH** — recorded and continued
- **ACCEPTED_DEBT** — deliberately deferred with a repair plan

---

## P0 — none

No P0 defect was found or remains open at sprint end.

## P1 — none remaining open (all repaired during this sprint)

### P1-1 (FIXED) — PEF preregistration validator out of sync with preregistration digest

- **Symptom:** `scripts/preflight/validate_pef_v0_preregistration.py` failed because the
  validator no longer matched the latest preregistration configuration/digest in
  `experiments/advanced_intelligence/pef_v0/preregistration.json`.
- **Files:** `scripts/preflight/validate_pef_v0_preregistration.py`, preregistration JSON.
- **Blast radius:** PEF_V0 preregistration gate (preflight verification).
- **Repair:** synchronized validator with the latest preregistration digest —
  commit `eb32122` (`fix(experiment): synchronize PEF preregistration validator with
  latest preregistration digest`). Fixed immediately as the sprint's first action, per
  sprint FIRST ACTIONS #4. Verified by preflight `pef-v0-preregistration: PASS`.

### P1-2 (FIXED) — Control identity never matched: PEF V0 ranking always failed

- **Symptom:** `_require_control_identity` compared the receipt `output_digest`
  (string with `"sha256:"` prefix, e.g. `"sha256:<hex>"`) against the bare-hex snapshot
  id; the comparison was always unequal, so `run_pef_v0_ranking()` always raised.
- **Files:** `src/frontier/application/advanced_intelligence.py`.
- **Blast radius:** application-layer PEF V0 runs (all shadow experiment execution that
  depends on control identity).
- **Repair:** normalize with `removeprefix("sha256:")` before comparing — commit
  `1b97fe1` (slice B). Covered by unit tests in `tests/unit/test_shadow_experiment.py`.

### P1-3 (FIXED, environment infra, off-record) — venv could not import fastapi/pydantic

- **Symptom:** the pre-existing `.venv` used CPython `3.14.0rc2`; `import fastapi`
  crashed with pydantic typing drift during `scripts/generate_public_contracts.py
  --check`, blocking the contract gate of `scripts/verify.py`.
- **Files:** none in the repo (environment-only repair).
- **Blast radius:** local verification environment only; CI untouched.
- **Repair:** rebuilt the local venv off-record:
  `uv venv --clear --python /usr/bin/python3.14 && uv sync --extra dev`
  (CPython 3.14.0rc2 → 3.14.4). Infra-only; no repo files changed. Recorded here per
  sprint policy because it affected the verification gate.

## P2 / POLISH — all repaired during this sprint

| ID | Slice | Symptom | Files | Blast radius | Repair status |
|----|-------|---------|-------|--------------|---------------|
| P2-1 | C | Circular-import risk between domain/application modules when candidate-freeze types were introduced | `src/frontier/domain/candidate_freeze.py`, application layer | Import graph of the intelligence vertical | Fixed in `e2bc824` (structure avoids the import cycle); `scripts/check_architecture_boundaries.py: PASS` |
| P2-2 | G | `_SectionFailure` sentinel plus NO_DATA/UNKNOWN conflation in the experimental read plane could mask empty sections as data | `src/frontier/application/experimental_read.py`, `src/frontier/domain/experimental_read.py` | Slice G read-plane responses | Fixed in `3a48916` (sentinel handling + explicit NO_DATA vs UNKNOWN semantics); covered by `tests/unit/test_experimental_read.py` |
| P2-3 | H | Pre-existing tsc debt: `TS2493` unused destructured binding in `api.test.ts` | `web/terminal/src/api.test.ts` | Terminal test build | Fixed in `6db6938`; `npx tsc --noEmit` clean (exit 0) |
| P2-4 | H | `EXPERIMENTAL_LENS` fixture literal not narrowed to a stable union type | `web/terminal/src/model.ts`, terminal fixture validator | Terminal model typing | Fixed in `6db6938`; tsc clean |
| POL-1 | A | Test-only defect: incorrect `artifact_id` derivation assertion in unit tests (repaired pre-commit) | `tests/unit/test_pef_v0.py` | Tests only | Fixed before commit `a643422`; suite green |
| POL-2 | F | Drafting defects repaired pre-commit: missing imports, incorrect `Protocol` usage, missing `Digest` import, pyright invariance complaint | `src/frontier/domain/experimental_analysis.py`, `src/frontier/application/experimental_analysis.py` | Slice F modules | Fixed before commit `3b9f851`; pyright 0 errors |
| POL-3 | H | `EXPERIMENTAL_LENS` literal narrowing refinement | `web/terminal/src/model.ts` | Slice H module | Fixed in `6db6938`; tsc clean |

## ACCEPTED_DEBT (KNOWN DEBT) — deferred with repair plans

### DEBT-1 — Postgres integration tests skip locally (10 suites); migrations 0004–0009 never applied to a live DB here

- **Symptom:** `pytest` reports 24 skips (Sprint-1 suites plus pre-existing integration
  suites) with `FRONTIER_TEST_DATABASE_URL not set`. Migrations `0004_pef_artifacts`,
  `0005_shadow_experiment_runs`, `0006_candidate_freeze_receipts`,
  `0007_evaluation_receipts`, `0008_feature_vectors`,
  `0009_experimental_analysis` have never run against a live Postgres in this
  environment.
- **Files:** `tests/integration/test_pef_artifacts_postgres.py`,
  `test_shadow_experiments_postgres.py`, `test_candidate_freeze_postgres.py`,
  `test_evaluation_receipts_postgres.py`, `test_feature_vectors_postgres.py`,
  `test_experimental_analysis_postgres.py`, `test_experimental_read_postgres.py`
  (plus pre-existing suites); `migrations/versions/0004..0009`.
- **Blast radius:** persistence adapters are unit-covered but not live-DB-verified in
  this environment; schema drift on migrations 0004–0009 would go undetected locally.
- **Repair:** run integration suites with a test database (`FRONTIER_TEST_DATABASE_URL`)
  locally or in CI; apply migrations 0004–0009 to that DB.

### DEBT-2 — Slice G summary read plane exposes only latest items; per-episode candidate ranks / feature values not exposed

- **Symptom:** the experimental read plane returns only latest-per-entity summaries;
  per-episode candidate ranks and per-candidate feature values are not exposed, so the
  terminal EXPERIMENTAL lens renders rank deltas and feature values as `UNKNOWN` when
  candidate ranks are not available for a baseline-ranked entity.
- **Files:** `src/frontier/application/experimental_read.py`,
  `src/frontier/adapters/postgres/experimental_read.py`,
  `src/frontier/adapters/api/experimental_read.py`,
  `contracts/public/openapi_v0.json`,
  `clients/typescript/src/generated/public_read_v0.ts`,
  `web/terminal/src/TerminalApp.tsx`, `web/terminal/src/model.ts`.
- **Blast radius:** terminal comparison UX (honest UNKNOWN, no data corruption); read
  API completeness.
- **Repair:** future read-plane contract extension — list/per-episode endpoints
  exposing candidate ranks and feature vectors; regenerate contracts/TS client;
  rewire terminal model to consume them (terminal already renders honest UNKNOWN).

### DEBT-3 — Local verification environment rebuilt off-record

- **Symptom / repair:** see P1-3 above. Recorded as debt because the environment fix
  is not captured in any committed configuration (no repo change was warranted).
- **Files:** none (environment only).
- **Blast radius:** local dev environment reproducibility only.
- **Repair (recommended):** ensure CI pins a Python minor (≥ 3.14 stable) compatible
  with the uv.lock extras so the contract-generation check cannot hit the same
  pydantic/fastapi import drift.

### DEBT-4 — `ZOOCODE_SPRINT1.md` untracked

- **Symptom:** the sprint input document sits in the repo root but is intentionally
  not committed (input document, not sprint output).
- **Files:** `ZOOCODE_SPRINT1.md`.
- **Blast radius:** none (documentation provenance only).
- **Repair:** leave untracked (accepted), or move to a dedicated planning area if the
  orchestrator wants it versioned.

### DEBT-5 — `evaluate_shadow_experiment()` PairedSnapshot plumbing to stored snapshot loaders left to integration follow-up

- **Symptom:** the evaluation machinery (slice D) is digest-bound and model-independent,
  but application-layer wiring of `evaluate_shadow_experiment()` to stored snapshot
  loaders (the PairedSnapshot plumbing that feeds evaluation directly from persisted
  shadow runs) was left as an integration follow-up.
- **Files:** `src/frontier/application/evaluation.py`,
  `src/frontier/application/advanced_intelligence.py` (call-site wiring),
  `src/frontier/adapters/postgres/advanced_intelligence.py`.
- **Blast radius:** end-to-end evaluation runs need a thin adapter layer; evaluation
  logic itself is complete and unit-covered (40 tests).
- **Repair:** wire `evaluate_shadow_experiment()` against `PostgresShadowRunRepository`
  stored snapshots and artifact loaders in the next sprint, then add a live-DB
  integration test (depends on DEBT-1).

---

# Sprint 1 Final Report (companion section)

## PLAN

Final integration pass only, per subtask scope:
1. Write the sprint-mandated defect ledger (`docs/SPRINT_1_DEFECT_LEDGER.md`).
2. Run final full verification (`scripts/verify.py`, terminal vitest + tsc).
3. Capture final git state.
4. Produce the FINAL OUTPUT in the mandated format (this section).
5. Commit the ledger as `docs(sprint): record Sprint-1 defect ledger and sprint report`.
No new features were added in this pass.

## CHANGESET (all files by slice)

- `eb32122` fix(experiment): `scripts/preflight/validate_pef_v0_preregistration.py`
  synchronized with the latest preregistration digest.
- `a643422` slice A — PEF_V0 foundation: `src/frontier/domain/advanced_intelligence.py`,
  `src/frontier/application/advanced_intelligence.py`,
  `src/frontier/adapters/postgres/advanced_intelligence.py` (`PostgresPefArtifactRepository`),
  `migrations/versions/0004_pef_artifacts.py`, `tests/unit/test_pef_v0.py` (11 tests),
  `tests/integration/test_pef_artifacts_postgres.py`.
- `1b97fe1` slice B — shadow experiment engine: `ShadowExperimentRun`,
  `build_shadow_experiment_run()`, `run_shadow_experiment()`,
  `migrations/versions/0005_shadow_experiment_runs.py`, `PostgresShadowRunRepository`,
  `tests/unit/test_shadow_experiment.py` (12 tests). P1-2 fixed here.
- `e2bc824` slice C — candidate freeze: `src/frontier/domain/candidate_freeze.py`
  (`CandidateFreezeReceipt`, `verify_candidate_freeze()` fail-closed drift detection),
  `src/frontier/application/candidate_freeze.py` (`freeze_candidate()`,
  `verify_freeze()`), `migrations/versions/0006_candidate_freeze_receipts.py`,
  `PostgresCandidateFreezeRepository`, freeze binding into `run_shadow_experiment()`,
  `tests/unit/test_candidate_freeze.py` (21 tests). P2-1 fixed here.
- `597117f` slice D — evaluation machinery: `src/frontier/domain/evaluation.py`
  (digest-bound `EVALUATION_CONFIGURATION`, model-independent labels, opportunity
  anchors, top-K paired precision, Newcombe hybrid margin −0.10 in stdlib `Decimal`,
  lead-time medians, sample adequacy ≥ 2 domains, `EvaluationReceipt` statuses
  `COMPLETE`/`INSUFFICIENT_SAMPLE`/`FAILED`/`INVALID_DRIFT`),
  `src/frontier/application/evaluation.py` (`evaluate_shadow_experiment()`),
  `migrations/versions/0007_evaluation_receipts.py`, `PostgresEvaluationRepository`,
  `tests/unit/test_evaluation.py` (40 tests).
- `dabbcf0` slice E — transparent feature vectors: `src/frontier/domain/features.py`
  (10 deterministic interpretable features — persistence/novelty/recency/acceleration/
  breadth/propagation/recurrence/decay/primary_emission_timing/discovery_lag — with
  UNKNOWN semantics), `src/frontier/application/advanced_features.py`
  (`compute_advanced_features()`), `migrations/versions/0008_feature_vectors.py`,
  `PostgresFeatureVectorRepository`, `tests/unit/test_advanced_features.py` (23 tests).
- `3b9f851` slice F — richer experimental analysis: `src/frontier/domain/experimental_analysis.py`
  (6 artifact kinds `GROUPING_HYPOTHESES`/`ENTITY_PROVENANCE`/`CORROBORATION`/
  `PROPAGATION_GRAPH`/`INDICATORS`/`TRAJECTORY` with `forbid_truth_keys` structural
  R7 guard), `src/frontier/application/experimental_analysis.py`,
  `migrations/versions/0009_experimental_analysis.py`,
  `PostgresExperimentalAnalysisRepository`, `tests/unit/test_experimental_analysis.py`
  (22 tests).
- `3a48916` slice G — EXPERIMENTAL_SHADOW read API: `src/frontier/domain/experimental_read.py`,
  `src/frontier/application/experimental_read.py`,
  `src/frontier/adapters/postgres/experimental_read.py` (read-only),
  `src/frontier/adapters/api/experimental_read.py` (`/v0/experimental/*` endpoints),
  regenerated `contracts/public/openapi_v0.json` +
  `clients/typescript/src/generated/public_read_v0.ts`,
  `tests/unit/test_experimental_read.py` + `tests/unit/test_experimental_api.py`
  (15 tests). P2-2 fixed here.
- `6db6938` slice H — terminal EXPERIMENTAL lens: `web/terminal/src/api.ts`,
  `web/terminal/src/model.ts`, `web/terminal/src/TerminalApp.tsx`,
  `web/terminal/src/styles.css`; `x` key toggle; rank deltas with UNKNOWN when
  candidate ranks are not exposed; feature explanations; history; explicit
  EMPTY/UNKNOWN/error states; fixture T021 `experimental-lens` + validator update;
  `docs/TERMINAL_V0.md` addendum; `web/terminal/src/*.test.ts(x)` (21 tests).
  P2-3/P2-4 fixed here.
- This commit: `docs/SPRINT_1_DEFECT_LEDGER.md` (ledger + sprint report).

## INTEGRATED CAPABILITIES

- Deterministic PEF_V0 candidate ranking (preregistration-bound, no learned coefficients).
- Shadow experiment engine executing control baseline vs experimental candidate on the
  identical episode universe / as_of / registry / health / evidence; baseline snapshots
  untouched (R6).
- Durable candidate-freeze receipts (preregistration identity, implementation tree,
  dependency lock, algorithm/config digest, registry version) with fail-closed drift
  detection.
- Digest-bound evaluation machinery: top-K paired precision, Newcombe hybrid margin
  −0.10, opportunity anchors, lead-time medians, sample adequacy, immutable
  `EvaluationReceipt` with explicit non-COMPLETE statuses (R8).
- 10 transparent interpretable feature vectors with honest UNKNOWN semantics (R4).
- 6 experimental analysis artifact kinds under a structural R7
  `forbid_truth_keys` guard (epistemic non-escalation).
- Read-only `/v0/experimental/*` API with regenerated OpenAPI contract + TS client.
- Terminal EXPERIMENTAL lens (`x` toggle) comparing BASELINE vs EXPERIMENTAL with
  keyboard-first behavior, snapshot identity visibility, and explicit
  EMPTY/UNKNOWN/error states.
- Migrations `0004`–`0009` for all new artifact/receipt/vector stores.

## TESTS

- Python full suite (`uv run python scripts/verify.py` → pytest): **209 passed,
  24 skipped** (all skips are `FRONTIER_TEST_DATABASE_URL` integration suites — see
  DEBT-1), verifier EXIT 0.
- Sprint-1 focused unit suites: `test_pef_v0` 11, `test_shadow_experiment` 12,
  `test_candidate_freeze` 21, `test_evaluation` 40, `test_advanced_features` 23,
  `test_experimental_analysis` 22, `test_experimental_read` + `test_experimental_api`
  15 — 144 python unit tests this sprint.
- Terminal: `npx vitest run` — **21 passed** (api 4, model 10, TerminalApp 7);
  `npx tsc --noEmit` — clean (exit 0).
- Preflights all PASS, including `pef-v0-preregistration: PASS`,
  `terminal-corpus: PASS 21 frozen hostile scenarios`,
  `advanced-intelligence-corpus: PASS 20 frozen hostile scenarios`,
  `public-contract-generation: PASS`; pyright 0 errors; ruff clean;
  `architecture-boundaries: PASS`.

## DEFECT LEDGER

See above: P0 none; P1 none remaining (P1-1, P1-2, P1-3 all fixed); P2/POLISH all
repaired (P2-1..P2-4, POL-1..POL-3); ACCEPTED_DEBT DEBT-1..DEBT-5 recorded with
symptom/files/blast radius/repair plan.

## KNOWN DEBT

DEBT-1 Postgres integration skips (10 suites; migrations 0004–0009 never applied to a
live DB here) · DEBT-2 read plane latest-only (per-episode ranks/features UNKNOWN;
contract extension needed) · DEBT-3 off-record venv rebuild · DEBT-4 ZOOCODE_SPRINT1.md
untracked (intentional) · DEBT-5 evaluate_shadow_experiment() PairedSnapshot wiring to
stored snapshot loaders pending. Full detail above.

## COMMITS

```
6db6938 (HEAD -> zoocode/sprint-1-intelligence) feat(terminal): EXPERIMENTAL comparison lens (slice H)
3a48916 feat(api): EXPERIMENTAL_SHADOW read endpoints + regenerated contracts (slice G)
3b9f851 feat(intelligence): richer experimental analysis artifacts (slice F)
dabbcf0 feat(intelligence): transparent advanced feature vectors (slice E)
597117f feat(intelligence): preregistered evaluation machinery (slice D)
e2bc824 feat(intelligence): candidate freeze identity and receipts (slice C)
1b97fe1 feat(intelligence): shadow experiment engine paired execution (slice B)
a643422 feat(intelligence): implement PEF_V0 deterministic foundation (slice A)
eb32122 fix(experiment): synchronize PEF preregistration validator with latest preregistration digest
<this commit> docs(sprint): record Sprint-1 defect ledger and sprint report
```

## CURRENT HEAD

`6db6938d60089551ce04c948d66c4db3808a22a8` on branch `zoocode/sprint-1-intelligence`
(at ledger-writing time; advanced by the ledger commit itself).

## VERDICT

**SUCCESS condition MET.** Every clause of the sprint SUCCESS condition is evidenced:

- PEF implemented — slices A (`a643422`) + preregistration gate PASS.
- Baseline preserved — baseline/comparator surfaces untouched; no silent reranking;
  R6 comparators intact.
- Shadow experiment execution works — slice B with P1-2 repaired and unit-covered.
- Deterministic artifacts/receipts work — PEF artifacts, shadow runs, evaluation
  receipts, experimental analysis artifacts all digest-bound.
- Candidate freeze works — slice C with fail-closed drift detection.
- Evaluation machinery works — slice D, 40 unit tests.
- Advanced transparent intelligence features exist — slice E, 10 features, 23 tests.
- Useful experimental read/API/terminal integration exists — slices G + H.
- Focused tests pass — all sprint suites green.
- Full verification passes — `scripts/verify.py` EXIT 0 (209 passed / 24 skipped);
  terminal vitest 21/21, tsc clean.
- No known P0/P1 defect remains — all P0/P1 entries above are marked FIXED.
- Remaining debt is written to this ledger — DEBT-1..DEBT-5.

## NEXT SPRINT RECOMMENDATION

1. Stand up a Postgres test database and run the 10 skipped integration suites with
   migrations 0004–0009 applied (closes DEBT-1).
2. Wire `evaluate_shadow_experiment()` to stored snapshot loaders end-to-end and add a
   live-DB evaluation integration test (closes DEBT-5).
3. Extend the read-plane contract with per-episode candidate ranks and feature values;
   regenerate contracts/TS client; upgrade the terminal UNKNOWN placeholders into real
   rank deltas and feature explanations (closes DEBT-2).
4. Promote the strongest experimental candidate toward confirmatory evaluation only
   after freeze-identity continuity is demonstrated across runs (R7 discipline).
5. Consider pinning CI Python to a stable 3.14.x to prevent recurrence of the pydantic
   import drift (DEBT-3).
