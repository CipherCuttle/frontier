# FRONTIER Roadmap

Status: CURRENT_IMPLEMENTATION_STATE_V0

Snapshot parent: `main@4c70e92c6ceb42a009a63d6f71c0d2eba90ddd77`.

Promotion rule for this file: merge of PR #8 promotes `GROUPING_BASELINE_V0` to CLOSED and makes `BASELINE_INTELLIGENCE_V0` the next product phase. The exact merged tree `main@4c70e92c6ceb42a009a63d6f71c0d2eba90ddd77` is the parent authority for that transition.

This file records implementation state and next-phase priority. It does not override the Constitution or accepted ADRs. If this roadmap conflicts with higher authority, implementation fails closed until governance is repaired.

Do not infer implementation phase from GitHub pull-request number. Preflight and governance PRs make GitHub numbering diverge from product-phase sequencing.

## Closed foundation

| Work | GitHub PR | Status | Result |
|---|---:|---|---|
| Canonical governance / architecture authority | #1 | CLOSED | Constitution V0, P01-P08, source policy, ADR-0001..0012 |
| Canonical evidence substrate | #2 | CLOSED | append-only PostgreSQL evidence, deterministic identity/replay, point-in-time knowledge horizon |
| PR-02 hostile preflight authority | #3 | CLOSED | 56 acquisition / transport / normalization / provenance attack fixtures |
| PR-02 executable fetch/source contracts | #4 | CLOSED | machine-readable fetch, source, policy and registry contracts |
| Live acquisition V0 | #5 | CLOSED | secure `frontier-fetch`, PyPI Latest Updates, CISA KEV, source health, trusted canonical writes |
| Roadmap / implementation-state authority | #6 | CLOSED | living roadmap, stale bootstrap repair, D007 unprotected-main debt |
| Source diversity V0 | #7 | CLOSED | HN ATTENTION, GDELT DISCOVERY, Hugging Face PRIMARY_EMISSION; five-source registry |
| Grouping baseline V0 | #8 | CLOSED | frozen 22-case grouping authority, guarded-hybrid-v0, explicit ambiguity, PIT-safe receipts, pairwise-safe episode groups |

## Current system capability after PR #8 promotion

FRONTIER can:
- acquire five zero-paid / no-mandatory-key live source lanes;
- observe authoritative primary emission through PyPI, CISA KEV and Hugging Face model metadata;
- observe Hacker News as an `ATTENTION` surface without promoting linked claims into factual truth;
- observe GDELT as a `DISCOVERY` surface without treating syndication as independent corroboration;
- keep the hostile fetch role DB-blind;
- reject forbidden/private network targets and bounded-resource violations;
- preserve first-durable `observed_at`, collection causality and multidimensional source health;
- mark capped finite result windows as incomplete rather than silently healthy;
- distinguish discovery/attention timestamps from publisher publication time and FRONTIER knowledge time;
- replay and verify canonical evidence deterministically;
- group observations into deterministic, versioned episode projections with explicit `GROUP`, `NO_GROUP`, and `AMBIGUOUS` semantics;
- prevent a direct `NO_GROUP` or `AMBIGUOUS` pair from entering one episode through transitive bridge merging;
- keep observation identity, episode interpretation, provenance-root independence, and entity identity separate.

FRONTIER still cannot:
- infer cross-source factual-root independence or true syndication ancestry;
- compute a prospective naive trend baseline;
- publish immutable public intelligence snapshots;
- serve a public read API;
- render the operator terminal.

## Immediate repository-control gap

GitHub still reports `main` unprotected after PR #8. Exact-head merges and CI reduce risk but do not replace branch/ruleset protection. This remains D007 until protection is enabled and verified.

## Priority sequence

### 0. Repository control hardening

Goal: protect canonical `main` from accidental/direct writes while preserving the reviewed PR workflow.

Required outcome:
- branch protection or ruleset for `main`;
- required verification check(s) where supported;
- PR-based merge path retained;
- no bypass assumption embedded in automation.

This is operational governance, not a product phase, and remains open as D007.

### 1. SOURCE_DIVERSITY_V0 — CLOSED

Goal: create structurally different live evidence roles so emergence, attention, discovery, syndication and coverage can be tested empirically.

Delivered lanes:
- Hacker News official front-page RSS as `ATTENTION`;
- GDELT DOC ArticleList as `DISCOVERY`;
- Hugging Face public Hub model metadata as `PRIMARY_EMISSION`;
- existing PyPI and CISA KEV source semantics preserved.

Frozen phase semantics:
- multiple attention/discovery observations do not become multiple factual confirmations;
- GDELT discovery time is not publisher time or FRONTIER knowledge time;
- capped result windows degrade completeness;
- absence of usable source timestamps yields freshness `UNKNOWN`;
- volatile Hugging Face popularity counters do not contaminate canonical model-emission identity;
- no advanced ranking, entity authority or embedding dependency was introduced.

### 2. GROUPING_BASELINE_V0 — CLOSED

Goal: establish the simplest defensible observation grouping/dedupe layer needed to say that multiple observations concern the same episode without pretending to know true ancestry.

Delivered method:
- froze a representative 22-case corpus spanning primary-emission, attention, discovery, syndication, correction/retraction, shared-index, revision, Unicode and ambiguous-alias cases before runtime selection;
- compared canonical URL, exact semantic text, normalized title, token Jaccard, SimHash, MinHash, TF-IDF and a guarded transparent hybrid;
- selected `guarded-hybrid-v0` at pair precision `1.000000`, group recall `0.900000`, false-group count `0` on the frozen corpus;
- preserved propagation/attention observations separately from evidence independence;
- retained explicit `NO_GROUP` / `AMBIGUOUS` outcomes;
- made grouping deterministic, versioned, point-in-time safe and receipt-backed;
- repaired hostile-review H-001 so final episode groups merge only when every cross-component pair is directly `GROUP`, preventing transitive uncertainty/negative-evidence collapse.

Closure evidence:
- one hostile review;
- one High repaired narrowly;
- one targeted re-review PASS with no new Critical/High findings;
- exact merged-tree verification on `main@4c70e92c6ceb42a009a63d6f71c0d2eba90ddd77`;
- Ruff/Pyright/architecture/preflights PASS;
- `58 passed`.

No embeddings, provenance-root inference, entity resolution, trend scoring, public API or frontend were introduced.

### 3. BASELINE_INTELLIGENCE_V0 — NEXT PRODUCT PHASE

Goal: run the permanent naive prospective baseline before sophisticated ranking.

Initial outputs may include:
- chronological recency;
- mention/event count;
- rate of change / velocity;
- simple acceleration where numerically meaningful;
- source-role diversity;
- origin/evidence-root diversity where available;
- coverage state;
- freshness.

Requirements:
- deterministic, versioned projection;
- point-in-time `as_of` correctness;
- immutable COMPLETE snapshot receipt;
- failed candidate snapshot leaves prior complete snapshot current;
- prospectively retained results for later comparison against advanced models.

### 4. PUBLIC_READ_PLANE_V0

Goal: expose derived intelligence read models without allowing the public API to mutate canonical intelligence state.

Planned stack:
- FastAPI transport only;
- generated OpenAPI TypeScript client;
- materialized read models for source/system health and baseline RADAR/NOW/TRENDING substrate;
- evidence/provenance drill-down endpoints;
- p95 read target evaluated against P03 candidate requirements.

### 5. TERMINAL_V0

Goal: implement the first dense operator terminal against real read models.

Primary operator tasks remain those in P02: what changed, what strange thing is moving, why, where it originated, whether evidence is independent, what is missing, and how the state evolved.

Planned presentation stack remains TypeScript strict + React 19 + Vite with keyboard-first interaction and explicit provenance/uncertainty/source-health display.

### 6. ADVANCED_INTELLIGENCE_EXPERIMENTS

Only after the prospective baseline exists:
- emergence vs confirmation models;
- manipulation/reflexivity features;
- persistence/novelty models;
- richer episode/entity resolution;
- provenance inference;
- advanced ranking.

An advanced model receives authority only if it demonstrates prospective value over the naive baseline at comparable precision across multiple domains, as required by P03.

### 7. DOMAIN EXPANSION + OPERATIONS

Broaden toward the full mission using source-policy gates: AI/model hubs, research, GitHub activity, package ecosystems, security, regulatory, crypto and markets.

In parallel, close production-operability requirements: observability, retention, backup + restore verification, capacity/load measurement, source freshness SLOs, deployment, and recovery drills.

## Carried debt

`docs/DEBT_REGISTER.md` remains the authority for accepted debt. No roadmap phase may silently resolve or discard a debt item; closure requires evidence against its trigger.

## Completion discipline

Each bounded implementation phase follows:

`IMPLEMENT -> TEST -> ONE hostile review -> repair Critical/High -> ONE targeted re-review only if Critical/High repair was required -> CLOSE -> MOVE FORWARD`

Medium/Low findings do not restart a phase unless they undermine its objective, evidence, frozen authority, security/integrity or fail-closed semantics.
