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
| D011 | KNOWN_COMPROMISE | A confirmatory-looking evaluation receipt is producible via `confirmatory=False` plus a supplied `durable_freeze_at` outside the four-gate path (latent; no shipped caller passes a supplied `durable_freeze_at`) | fix: explicit `evaluation_class` parameter or route all durable evaluations through the four-gate path (hostile review M-03) |
| D012 | KNOWN_COMPROMISE | Freeze-persist authorization guard (`FRONTIER_FREEZE_PERSIST_AUTHORIZED`) is CLI-layer only; the repository write path is unprotected | fix: move the guard to a shared persistence gate before any non-CLI caller can persist freeze receipts (hostile review M-04) |
| D013 | KNOWN_COMPROMISE | L-01: the overview envelope may mix boundaries (identity visible to callers) | fix: add as_of consistency note or a single-boundary guard when the read plane serves mixed-boundary rows (hostile review L-01) |
| D014 | KNOWN_COMPROMISE | L-02: confirmatory gate has a clock-skew residual (application-side clock vs DB commit clock) | fix: evaluate the as_of-vs-durable gate DB-side inside the same transaction when confirmatory runs go live (hostile review L-02) |
| D015 | KNOWN_COMPROMISE | L-03: a DEV worker adopting a CONFIRMATORY boundary writes DEV-class attempt detail, which is misleading in attempt history | fix: tag adopted attempts with the boundary's existing run class or refuse cross-class adoption (hostile review L-03) |
| D016 | KNOWN_COMPROMISE | L-04: `ops status` worker_count counts stale heartbeats as present workers | fix: add FRESH/STALE verdict to worker heartbeat reporting (hostile review L-04) |
| D017 | TEMPORARY_ADAPTER | L-05: dead client-side delta computation path in `web/terminal/src/model.ts` | delete it or mark it test-only before it diverges from server semantics (hostile review L-05) |
| D018 | KNOWN_COMPROMISE | L-06: the positive replay gauntlet proves determinism only for a degenerate INSUFFICIENT_SAMPLE evaluation receipt | fix: add a COMPLETE-receipt replay scenario (hostile review L-06) |
| D019 | KNOWN_COMPROMISE | L-07: `latest_run_id_and_class_for_as_of` is unscoped by experiment_id and relies on arbitrary row ordering | fix: add experiment_id filter and a per-(as_of, run_class) uniqueness constraint before any second experiment id exists (hostile review L-07) |

Vague `TODO refactor later` debt is not governance.
