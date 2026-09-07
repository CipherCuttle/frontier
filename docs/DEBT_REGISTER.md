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
| D010 | DEFERRED_REQUIREMENT | `frontier worker` composes only the acquisition orchestrator; the prospective experiment orchestrator is supported by `run_once` but is not wired into the default continuous worker composition (heartbeat handles `experiment=None` gracefully) | Wire the experiment orchestrator into the default worker composition when production experiments start; until then experiment cycles are driven explicitly |

Vague `TODO refactor later` debt is not governance.
