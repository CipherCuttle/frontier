# FRONTIER Debt Register

Allowed classifications only:
- KNOWN_COMPROMISE
- TEMPORARY_ADAPTER
- UNPROVEN_ASSUMPTION
- DEFERRED_REQUIREMENT

Each entry must state: accepted reason, blast radius, review/removal trigger, responsible phase.

Current carried items:

| ID | Class | Item | Trigger |
|---|---|---|---|
| D001 | UNPROVEN_ASSUMPTION | Python acquisition meets initial freshness/resource SLOs | profiling or P03 source-freshness failure |
| D002 | UNPROVEN_ASSUMPTION | PostgreSQL alone handles initial jobs/projections/read workload | EXP-08 / measured SLO failure after reasonable tuning. Supporting evidence (GIGASPRINT_01): this sprint added zero specialist infrastructure — worker single-instance coordination uses a Postgres-native session advisory lock and experiment state is plain relational tables, so the Postgres-only assumption held for all shipped prospective-intelligence workloads; remains OPEN by design until measured evidence |
| D003 | DEFERRED_REQUIREMENT | full bitemporal range schema | only if simple observed/source/effective/as_of clocks cannot satisfy required historical queries |
| D004 | DEFERRED_REQUIREMENT | specialist analytical store | only after Postgres workload evidence |
| D005 | DEFERRED_REQUIREMENT | graph storage | only after relational projection demonstrably fails operator/algorithm need |
| D006 | UNPROVEN_ASSUMPTION | exact trend/clustering/dedupe algorithms | P04+ experimental evidence; no pre-crowning |
| D007 | KNOWN_COMPROMISE | GitHub `main` was unprotected (GET /branches/main/protection -> 404 "Branch not protected"; GET /rules/branches/main -> [] as of 2026-09-06). CLOSED: branch ruleset `main-pr-verify-gate` (id 22366099, enforcement active) now requires pull_request + required_status_checks context `verify` on `refs/heads/main`; classic branch protection API still returns 404 (ruleset-only). Direct writes by admins remain theoretically possible via bypass; bypass_actors currently empty and current_user_can_bypass=never. | verify ruleset enforcement holds through first agent-parallel PR cycle |
| D008 | TEMPORARY_ADAPTER | `tests/integration/test_postgres_store.py` idempotency tests use fixed observation identities, so re-running the same file twice against the same non-fresh database hits canonical dedup and fails spuriously | HARMLESS under the CI per-file fresh-DB isolation (WP12b); becomes real only if suites are ever run repeatedly against one shared DB — fix identities or reset state then |
| D009 | TEMPORARY_ADAPTER | `pef_ranking_artifacts.artifact_json` payload lacks a top-level `generated_at`; the experimental read plane falls back to the run `as_of` as the artifact generation time | MEDIUM only if artifact generated-time ever needs to be contractually distinct from `as_of` (e.g. replay-time regeneration); currently benign because artifacts are deterministic for a given run |
| D010 | DEFERRED_REQUIREMENT | CLOSED (R-H01 repair, commit 7af3922): `frontier worker` now composes the `ExperimentOrchestrator` (DEV run-class, confirmatory gated) into both `--once` and continuous modes | re-open only if the worker composition loses the orchestrator wiring |
| D011 | KNOWN_COMPROMISE | CLOSED (GIGASPRINT_02 G2-03; verified on final code head `93e7a05156a37d8b68e1fa7b4a6cfc6ad8f04609`): persisted evaluation authority is reconstructed from persisted run identity/class, bound freeze/publication evidence, canonical context, drift sentry, and the fixed scientific window. Caller flags/timestamps are restrictive assertions only; DEV rows cannot be relabeled CONFIRMATORY, mixed DEV/CONFIRMATORY windows fail closed, and foreign-freeze windows cannot manufacture confirmatory evidence. | re-open only if caller-supplied flags/timestamps can escalate evaluation authority, persisted run identity can be bypassed, or DEV evidence can become CONFIRMATORY |
| D012 | KNOWN_COMPROMISE | CLOSED (GIGASPRINT_02 G2-04; implementation commit `320a54a618bab2581a84dd3d293c7e1d5cab59cf`, verified on final code head `93e7a05156a37d8b68e1fa7b4a6cfc6ad8f04609`): `PostgresCandidateFreezeRepository.record_receipt()` requires an explicit lower-level persistence capability; the CLI operator environment gate is additional UX rather than the security boundary, and unauthorized direct repository writes fail before DB mutation. | re-open only if any non-test persistence path can write a candidate-freeze receipt without the explicit lower-level authorization capability |
| D013 | KNOWN_COMPROMISE | L-01: the overview envelope may mix boundaries (identity visible to callers) | fix: add as_of consistency note or a single-boundary guard when the read plane serves mixed-boundary rows (hostile review L-01) |
| D014 | KNOWN_COMPROMISE | CLOSED (GIGASPRINT_02 G2-05; verified on final code head `93e7a05156a37d8b68e1fa7b4a6cfc6ad8f04609`): confirmatory attempt eligibility is checked from canonical persisted durability/publication facts inside the PostgreSQL claim/authority boundary; application wall-clock skew cannot admit an otherwise ineligible confirmatory boundary, and exact-boundary/skew regressions fail closed. | re-open only if confirmatory eligibility can again be decided by an untrusted application clock outside the canonical DB claim boundary |
| D015 | KNOWN_COMPROMISE | L-03: a DEV worker adopting a CONFIRMATORY boundary writes DEV-class attempt detail, which is misleading in attempt history | fix: tag adopted attempts with the boundary's existing run class or refuse cross-class adoption (hostile review L-03) |
| D016 | KNOWN_COMPROMISE | CLOSED (post-PEF ops observability, PR #42): retained heartbeat rows now carry explicit `FRESH`/`STALE` liveness; `worker_count` counts only heartbeats no older than the explicit 300-second threshold, while `stale_worker_count` and `worker_row_count` preserve diagnostic visibility. PostgreSQL regression coverage verifies fresh/stale counting and latest-heartbeat classification. | re-open only if stale retained heartbeats can again inflate the live worker count or heartbeat freshness loses an explicit bounded threshold |
| D017 | TEMPORARY_ADAPTER | L-05: dead client-side delta computation path in `web/terminal/src/model.ts` | delete it or mark it test-only before it diverges from server semantics (hostile review L-05) |
| D018 | KNOWN_COMPROMISE | L-06: the positive replay gauntlet proves determinism only for a degenerate INSUFFICIENT_SAMPLE evaluation receipt | fix: add a COMPLETE-receipt replay scenario (hostile review L-06) |
| D019 | KNOWN_COMPROMISE | L-07: `latest_run_id_and_class_for_as_of` is unscoped by experiment_id and relies on arbitrary row ordering | fix: add experiment_id filter and a per-(as_of, run_class) uniqueness constraint before any second experiment id exists (hostile review L-07) |

Vague `TODO refactor later` debt is not governance.
