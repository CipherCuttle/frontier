# GIGASPRINT_01 PR Notes — Prospective Intelligence Operationalization

Source for the PR body of branch `agent/gigasprint-01-prospective-intelligence`.
Status: **IMPLEMENTED_ON_BRANCH**, pending independent review and merge authorization.

## Objective

Operationalize prospective intelligence experiments end-to-end on top of the merged
sprint-1 experimental substrate (PR #18): durable opportunity/outcome and attempt state,
paired prospective orchestration, persisted evaluation, scientific status semantics,
drift gating, an identity-transparent comparison read plane/terminal, live-Postgres
proof, and an operator freeze workflow — without granting confirmatory authority to any
experimental model.

## Base and frozen authority

- Base: `main@db9a56e4be66085def287682fa94bbe599bb58f5` (PR #18 merge).
- Authority unchanged and unmodified by this branch: `docs/CONSTITUTION.md`,
  ADR-0001..0012, P01–P08, `experiments/advanced_intelligence/pef_v0/preregistration.json`
  (digest-bound PEF_V0 preregistration), baseline ranking policy
  `naive-episode-activity-v0`, grouping authority `guarded-hybrid-v0`, frozen fixture
  corpora, `sources/registry/registry_v0.json`, and the digest-bound evaluation
  configuration (top-K paired precision, Newcombe hybrid margin −0.10).

## Architecture summary — five state-model ownership decisions

1. **Durability is owned by the canonical database.** `durable_freeze_at` is stamped by
   a `BEFORE INSERT` trigger with the committing transaction's `clock_timestamp()`;
   it is never collapsed with the local wall-clock `frozen_at` (migration 0010).
   `NULL` durability can never gate a confirmatory run.
2. **Run class is explicit and safe-by-default.** `shadow_experiment_runs.run_class`
   is `DEV`/`CONFIRMATORY`; existing and unstamped rows are `DEV` (migration 0010).
3. **The attempt lifecycle is the only new mutable operational state.** Explicit
   terminal states (`DONE`/`EXPIRED`/`FAILED`/`SKIPPED`) with a mutable `detail` column
   carrying human-readable reasons and `run_id` bindings — never extra state enums
   (migration 0011); RUNNING attempts with elapsed leases are adopted-or-expired.
4. **Opportunity membership is append-only evidence, never a flag.** Content-derived
   `membership_id` rows record present/absent at each paired-run boundary `as_of`;
   rows are never updated or deleted (migration 0012).
5. **Outcome labels are blinded adjudication, not projection.** A `RESOLVED` label
   requires explicit `BLINDED` adjudication with evidence digests; `UNKNOWN` stays
   `UNKNOWN`; anchors without a resolution row are `PENDING` by projection (migration 0010).

## Work packages (one-line outcomes)

| WP | Outcome | Commit |
|---|---|---|
| WP0 | Governance baseline: D007 main-protection status recorded | `0196a56` |
| WP1 | Opportunity/outcome + run-attempt state foundations (migration 0010) | `e7f7d7e` |
| WP2 | Paired prospective experiment orchestrator, adopt-or-expire attempts (0011) | `cb6582a` |
| WP3 | Durable prospective opportunity/outcome state + membership history (0012) | `e5db416` |
| WP4 | Persisted paired-snapshot evaluation loaders, fail-closed + boundary tests A–F | `48c319e` |
| WP5 | Coherent scientific evaluation status model (read plane semantics) | `6043305` |
| WP6 | Drift sentry validating frozen identity before confirmatory work | `9bfa0c6` |
| WP7 | Per-episode experimental read plane + API (closes sprint DEBT-2) | `0b91cb2` |
| WP8 | Terminal experiment war room (identity-transparent comparison views) | `3bc730b` |
| WP9 | Worker heartbeat, advisory-lock lease, graceful shutdown, `frontier ops status` | `e8b1c05` |
| WP10 | Backup/restore proof extended to experimental scientific tables | `e7238db` |
| WP11 | G10 hostile-mutation replay gauntlet: frozen-candidate determinism | `0c5932e` |
| WP12b | Full experiment lifecycle proof on live PostgreSQL + `e2e-postgres.yml` CI (closes sprint DEBT-1 in CI) | `f51683b` |
| WP13 | Candidate freeze operator workflow: `freeze derive\|verify\|durability` (G12) | `663afcf` |
| WP14 | Governance/docs reconciliation (roadmap, debt register, ledger, this file) | this commit |

## Migrations 0010–0012 summary

- **0010_experiment_outcome_state** — `durable_freeze_at` on freeze receipts
  (trigger-stamped canonical durability), `run_class` DEV/CONFIRMATORY,
  `opportunity_anchors` + blinded `outcome_resolutions` tables.
- **0011_experiment_attempt_detail** — mutable `detail` column on
  `experiment_run_attempts` for terminal-state reasons and `run_id` bindings.
- **0012_opportunity_memberships** — append-only per-boundary membership history for
  paired-run candidate/control universes (present/absent evidence with ranks).

## Scientific invariants preserved

- The naive baseline (`naive-episode-activity-v0`) remains authoritative; no reranking
  of baseline surfaces was introduced.
- PEF_V0 remains **EXPERIMENTAL_SHADOW**: no confirmatory authority; confirmatory
  evaluation requires DEV≠run-class gating, canonical DB context, a durable freeze, and
  `as_of > durable_freeze_at` (boundary tests A–F in
  `tests/unit/test_evaluation_loaders.py`).
- No LLM, no learned coefficients, no embedding dependency.
- No new domains: strata remain SOFTWARE_PACKAGES / AI_MODELS / SECURITY_VULNERABILITIES
  / UNQUALIFIED_MIXED / UNQUALIFIED.
- R6/R7 comparator and epistemic non-escalation guards intact (truth-key guard,
  digest-bound artifacts/receipts, G10 hostile-mutation gauntlet).

## Test evidence summary

- `uv run python scripts/verify.py` EXIT 0: **491 passed / 62 skipped** (all skips are
  `FRONTIER_TEST_DATABASE_URL` integration suites).
- Per-package (test functions): opportunity 17 unit + 3 PG; experiment orchestration
  14 unit + 4 PG; opportunity/outcome engine 47 unit + 2 PG; evaluation loaders
  40 unit (incl. boundary tests A–F) + 3 PG; experiment status 37 unit; drift sentry
  35 unit + 2 PG; experimental read plane 24 unit + 11 PG; worker lifecycle 10 unit +
  6 PG; backup/restore 1 PG; G10 gauntlet 21 replay + 3 PG replay; freeze workflow
  7 unit + 1 PG; lifecycle E2E 3 PG; terminal 40 (api 8, model 16, TerminalApp 16).
- `e2e-postgres.yml` (WP12b) runs the DB-bound suites with fresh-DB-per-file isolation
  on PR/nightly; the 10 PG suites previously skipped locally are proven live in CI.
- Ruff, strict Pyright, architecture-boundary and preflight gates PASS in `verify.py`.

## Explicit non-authority statement

This file is PR documentation, not authority. It confers no governance, ranking,
durability, or confirmatory authority. Authority remains the Constitution, accepted
ADRs, the PEF_V0 preregistration digest, and the frozen corpora/policies listed above.
No roadmap claim beyond shipped truth is made; GIGASPRINT_01 is IMPLEMENTED_ON_BRANCH
until independently reviewed and merged.

## Post-merge freeze sequencing

The real candidate freeze is NOT authorized during this sprint. After this branch
merges and a human operator explicitly authorizes persistence
(`FRONTIER_FREEZE_PERSIST_AUTHORIZED=1`), follow
[`docs/CANDIDATE_FREEZE_WORKFLOW.md`](CANDIDATE_FREEZE_WORKFLOW.md):
`freeze derive` (dry) → `freeze verify` → persist → `freeze durability` reports
`DURABLE` → confirmatory runs only with `as_of > durable_freeze_at`.
