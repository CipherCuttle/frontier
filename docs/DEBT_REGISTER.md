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
| D002 | UNPROVEN_ASSUMPTION | PostgreSQL alone handles initial jobs/projections/read workload | EXP-08 / measured SLO failure after reasonable tuning |
| D003 | DEFERRED_REQUIREMENT | full bitemporal range schema | only if simple observed/source/effective/as_of clocks cannot satisfy required historical queries |
| D004 | DEFERRED_REQUIREMENT | specialist analytical store | only after Postgres workload evidence |
| D005 | DEFERRED_REQUIREMENT | graph storage | only after relational projection demonstrably fails operator/algorithm need |
| D006 | UNPROVEN_ASSUMPTION | exact trend/clustering/dedupe algorithms | P04+ experimental evidence; no pre-crowning |
| D007 | KNOWN_COMPROMISE | GitHub `main` was unprotected (GET /branches/main/protection -> 404 "Branch not protected"; GET /rules/branches/main -> [] as of 2026-09-06). Mitigated: branch ruleset `main-pr-verify-gate` (id 22366099, enforcement active) now requires pull_request + required_status_checks context `verify` on `refs/heads/main`; classic branch protection API still returns 404 (ruleset-only). Direct writes by admins are still possible via bypass; bypass_actors currently empty and current_user_can_bypass=never. | verify ruleset enforcement holds through first agent-parallel PR cycle |

Vague `TODO refactor later` debt is not governance.
