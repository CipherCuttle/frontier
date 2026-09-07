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

Resolved items:

| ID | Former class | Item | Closure evidence |
|---|---|---|---|
| D007 | KNOWN_COMPROMISE | GitHub `main` branch protection / reviewed-merge enforcement | CLOSED on repository state observed after `main@a1cd427696ce76dd07fcd28abf06012df5767b78`: active repository ruleset `main-pr-verify-gate` (ruleset id `22366099`) targets `refs/heads/main`, requires the pull-request workflow and required status check `verify`, has no bypass actors, and reports current-user bypass as `never`. This satisfies D007's recorded trigger to enable and verify branch protection/ruleset before parallel agent development becomes routine. |

Vague `TODO refactor later` debt is not governance.
