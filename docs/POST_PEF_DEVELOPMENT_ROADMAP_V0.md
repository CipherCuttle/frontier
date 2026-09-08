# POST_PEF_DEVELOPMENT_ROADMAP_V0

Status: CURRENT_POST_PEF_DEVELOPMENT_STATE

Parent development head: `dev/post-pef-v0@7430c9a5f5ff84900212412d8c9fbd8a7d5a25ae`.
Canonical confirmatory publication remains isolated on `main@db206cda7eed92b62c706a10089c2571b4381d66`.

## Purpose and precedence

`docs/ROADMAP.md` remains useful implementation history but its status text was last reconciled through PR #30 and contains now-obsolete statements about GIGASPRINT_01 and PEF confirmatory readiness.

This bounded addendum reconciles only the post-PEF development state and next unblocked development priority. Under `docs/PLANNING_INDEX.md`, this explicit later phase authority refines current implementation sequencing without changing the Constitution, ADRs, frozen scientific contracts, or canonical confirmatory authority.

Where this file conflicts with the following stale `docs/ROADMAP.md` statements, this file supersedes them only for the named scope:

- GIGASPRINT_01 is no longer merely `IMPLEMENTED_ON_BRANCH`;
- the pre-confirmatory integrity/launch stack is no longer future work;
- a replacement PEF_V0 candidate freeze/publication now exists on canonical `main`;
- the canonical confirmatory worker has been launched under that frozen authority;
- post-PEF debt D013, D015, D016, D017, D018 and D019 are closed on the isolated development lane;
- roadmap reconciliation through PR #30 is no longer the next development task.

This document does **not** claim a PEF promotion verdict or candidate value. Promotion remains separate and unauthorized.

## Frozen-lane separation

During the active confirmatory window:

- canonical `main` remains the frozen publication lane at `db206cda7eed92b62c706a10089c2571b4381d66` unless separately authorized scientific recovery requires otherwise;
- post-PEF product/debt work remains isolated on `dev/post-pef-v0` and descendant feature branches;
- no post-PEF development merge into canonical `main` is authorized by this roadmap;
- no source-registry, preregistration, candidate-ranking, evaluation-threshold, live confirmatory deployment, or promotion change is implied by development-lane work.

## Current merged post-PEF development state

The isolated development lane includes bounded closures for:

- D016 stale worker-heartbeat observability;
- D019 experiment-scoped shadow-run recovery identity and uniqueness;
- D013 explicit experimental overview `as_of_consistency`;
- D015 persisted run-class provenance in adopted/completed attempts;
- D018 COMPLETE-path persisted evaluation replay determinism;
- D017 removal of the dead client-side rank-delta calculator so terminal deltas remain server-provided.

These are development-lane changes only. Their presence on `dev/post-pef-v0` does not mutate the running confirmatory candidate.

## Still-blocked authority lanes

### Real entity ground truth

Remains:

`BLOCKED_PENDING_REAL_TRUST_ROOT_MATERIAL`

The blocker is genuine external trust material, not missing code. FRONTIER may not synthesize substitutes.

### Agent Context Plane

Remains parked under `docs/ROADMAP_AGENT_CONTEXT_PLANE_V0.md`.

No Agent Context protocol, semantic retrieval, vector infrastructure, context-selection ranker, MCP adapter, persistent agent memory, or agent-demand feedback path is authorized by this development roadmap.

## Next unblocked development priority

### EVIDENCE_QUERY_V0 — AUTHORIZED ON POST-PEF DEV LANE

Authority: `docs/EVIDENCE_QUERY_V0.md`.

Why this is next:

1. The existing public read plane exposes deterministic views and exact-ID drill-down but no user/query-driven evidence filter.
2. A point-in-time lexical filter improves the current terminal/API product without changing canonical ranking or truth semantics.
3. It reuses the existing COMPLETE-snapshot and read-only PostgreSQL boundary rather than adding infrastructure.
4. It creates a permanent simple structured/lexical comparator that future Agent Context retrieval experiments may evaluate against, without prematurely implementing that parked program.
5. It is independently reversible: no migration, no index, no vector store, no canonical mutation.

Frozen shape:

`COMPLETE BASELINE SNAPSHOT -> EXACT MEMBER OBSERVATIONS -> LEXICAL FILTER -> BASELINE RANK ORDER`

No relevance reranking, embeddings, LLMs, fuzzy entity resolution, semantic expansion, or new authority.

## Follow-on sequence after EVIDENCE_QUERY_V0

Reassess from evidence rather than pre-authorizing scope. Candidate follow-ons are:

1. terminal query interaction over the generated typed client, if the backend query contract closes cleanly;
2. bounded query latency/capacity measurement under real retained snapshots;
3. source/domain expansion only where measured coverage gaps justify it;
4. Agent Context remains parked until its independent gates are actually satisfied;
5. PEF promotion work remains separate and cannot be inferred from development progress.

## Completion discipline

Every post-PEF development phase follows:

`IMPLEMENT -> TEST -> ONE HOSTILE REVIEW -> FIX CRITICAL/HIGH -> ONE TARGETED RE-REVIEW ONLY IF CRITICAL/HIGH FIXES WERE REQUIRED -> CLOSE -> MOVE FORWARD`

Medium/Low findings do not restart a phase unless they undermine the objective, evidence, frozen authority, security/integrity, or fail-closed semantics.
