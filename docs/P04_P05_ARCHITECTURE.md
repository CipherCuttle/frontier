# P04/P05 Architecture Tournament

Status: PASS — HYBRID MODULAR MONOLITH SELECTED

Compared candidates:
A. Python intelligence + PostgreSQL + FastAPI boundary + TypeScript/React/Vite presentation.
B. Full TypeScript/Node modular monolith.
C. Go acquisition + Python intelligence + TypeScript frontend.

Decision: A selected. B rejected for V0 because single-language simplicity solves a lower-priority problem than Python's extraction/research/evaluation ecosystem and a generated OpenAPI boundary already constrains Python/TS drift. C deferred because Go offers real acquisition concurrency/isolation benefits but adds a third ecosystem and prematurely hardens an unstable cross-runtime source seam.

Canonical improvement learned from C: keep the `frontier-fetch` semantic contract language-neutral enough for a later Go replacement if measured acquisition SLO/resource failures occur.

Sensitivity points: acquisition throughput, Postgres mixed workload, source-model churn, clustering CPU cost, API/domain coupling, frontend DOM/chart density.

Tradeoffs resolved:
- ecosystem specialization beats single-language ideology;
- preserve Go replacement seam, do not add Go now;
- Postgres-only wins until measured failure;
- ledger + idempotent projections beats one synchronous conveyor transaction;
- explicit/inferred provenance uncertainty beats false definitive roots.

Risk themes: epistemic overclaim; source/coverage decay; hostile acquisition; Postgres overextension; algorithm ossification.

No architecture tournament may be reopened absent a defined reversal gate.