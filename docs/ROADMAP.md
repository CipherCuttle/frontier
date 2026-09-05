# FRONTIER Roadmap

Status: CURRENT_IMPLEMENTATION_STATE_V0

Snapshot parent: `main@1783c6b10ef92caab72c6e340f0e6bd8562a0ac5`.

Promotion rule for this file: merge of the roadmap promotion following PR #12 records `PUBLIC_READ_PLANE_V0` as CLOSED and makes `TERMINAL_V0` the next product phase. The exact merged tree `main@1783c6b10ef92caab72c6e340f0e6bd8562a0ac5` is the parent authority for that transition.

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
| Baseline intelligence V0 | #10 | CLOSED | frozen naive episode-activity baseline, PIT-safe windows, explicit health/coverage, deterministic ranking, retained COMPLETE snapshots + receipts |
| Public read plane V0 | #12 | CLOSED | read-only FastAPI over retained COMPLETE baseline snapshots, auditable RADAR/NOW/TRENDING views, PIT-safe evidence drill-down, deterministic OpenAPI/TypeScript contract |

## Current system capability after PR #12 promotion

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
- keep observation identity, episode interpretation, provenance-root independence, and entity identity separate;
- compute the permanent naive prospective episode-activity baseline using fixed 1h/6h/24h windows, velocity and acceleration;
- exclude BACKFILL and recovered backlog from live activity while retaining them as evidence;
- retain explicit aggregate transport/freshness/coverage/schema state without converting missing coverage into zero activity;
- keep evidence-root diversity and confirmation unavailable rather than fabricating independence;
- publish deterministic COMPLETE baseline snapshots and projection receipts atomically and append-only;
- retain prospective baseline snapshots for future advanced-model comparison;
- serve a GET-only public FastAPI read plane over retained COMPLETE baseline snapshots;
- expose stable baseline-derived RADAR, NOW and TRENDING views without transport-layer reranking;
- bind public intelligence responses to snapshot, receipt, version and `as_of` identity;
- reject receipt-schema, deterministic receipt-ID and payload-digest drift at the public trust boundary;
- expose episode and observation evidence drill-down with point-in-time-safe collection and relation metadata;
- surface aggregate and per-source health without converting degraded/missing coverage into optimistic certainty;
- generate deterministic OpenAPI and TypeScript client artifacts from the public contract.

FRONTIER still cannot:
- infer cross-source factual-root independence or true syndication ancestry;
- render the operator terminal;
- authorize advanced ranking beyond the frozen naive comparator;
- infer richer entity identity, factual confirmation or provenance-root ancestry.

## Immediate repository-control gap

GitHub still reports `main` unprotected after PR #12. Exact-head merges and CI reduce risk but do not replace branch/ruleset protection. This remains D007 until protection is enabled and verified.

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

### 3. BASELINE_INTELLIGENCE_V0 — CLOSED

Goal: run the permanent naive prospective baseline before sophisticated ranking.

Delivered:
- deterministic episode activity projection at a fixed `as_of`;
- half-open 1h, 6h, 24h, previous-6h and preprevious-6h windows using only `observed_at`;
- integer mention count, velocity and acceleration metrics;
- BACKFILL and recovered-after-gap observations retained but excluded from live activity windows;
- deterministic ranking policy `naive-episode-activity-v0`;
- explicit source-role diversity without false provenance-root or confirmation claims;
- aggregate transport, freshness, coverage and schema state;
- immutable retained COMPLETE snapshots plus projection receipts in PostgreSQL;
- atomic candidate publication with conflict/failure preserving the prior COMPLETE snapshot;
- prospective retained outputs for later advanced-model comparison.

Closure evidence:
- exact final reviewed head `cecb69b5877e8470a62b61054cd4760a1fea4de0`;
- one hostile review: Critical 0 / High 0;
- exact-head `verify` and hostile-fixture workflows PASS;
- squash merge `main@458e0c5e2284eb221c6d92785082ce1c6359c1a0`;
- post-merge `verify` and hostile-fixture workflows PASS.

No advanced/learned ranking, provenance-root inference, entity resolution, API or frontend was introduced.

### 4. PUBLIC_READ_PLANE_V0 — CLOSED

Goal: expose derived intelligence read models without allowing the public API to mutate canonical intelligence state.

Delivered:
- FastAPI GET-only public transport over retained COMPLETE `baseline-intelligence-v0` snapshots;
- deterministic OpenAPI and generated TypeScript client contract;
- RADAR = all baseline episodes, NOW = `mentions_1h > 0`, TRENDING = `velocity_6h_delta > 0`, always preserving frozen baseline rank;
- snapshot/receipt/version/`as_of` identity on every intelligence response;
- strict public PostgreSQL read-only session enforcement;
- exact episode-membership drill-down and historical observation filtering;
- point-in-time-safe collection occurrence and relation metadata, including masking collection completion learned after the selected horizon;
- explicit aggregate and per-source health visibility;
- fail-closed COMPLETE snapshot, receipt, version and canonical payload integrity checks;
- deterministic receipt schema and receipt-ID reconstruction at the public trust boundary;
- healthy local/CI p95 read target below the P03 `<250ms` candidate bound.

Closure evidence:
- exact final repaired/re-reviewed head `4af2ba90310e6a66ff559be62c2ad501385dde96`;
- one hostile closure review found H-001 HIGH: receipt schema and deterministic receipt identity were not fully verified;
- one bounded H-001 repair added frozen receipt-schema enforcement, deterministic receipt-ID reconstruction and corruption coverage;
- one targeted re-review PASS with Critical 0 / High 0;
- exact-head `verify`, `preflight-fixtures` and `preflight-contracts` PASS;
- squash merge `main@1783c6b10ef92caab72c6e340f0e6bd8562a0ac5`;
- post-merge push-triggered `verify`, `preflight-fixtures` and `preflight-contracts` PASS.

No advanced/learned ranking, provenance-root inference, entity resolution, factual confirmation authority or canonical mutation path was introduced.

### 5. TERMINAL_V0 — NEXT PRODUCT PHASE

Goal: implement the first dense operator terminal against real read models.

Primary operator tasks remain those in P02: what changed, what strange thing is moving, why, where it originated, whether evidence is independent, what is missing, and how the state evolved.

Planned presentation stack remains TypeScript strict + React 19 + Vite with keyboard-first interaction and explicit provenance/uncertainty/source-health display.

Required invariants:
- the terminal is a disposable read client, never an intelligence authority;
- all displayed intelligence remains traceable to the public read response snapshot/receipt/version/`as_of` binding;
- UI filtering, sorting and emphasis must not silently create a new authoritative rank;
- confirmation/provenance-root/entity claims unavailable from the read plane remain unavailable in the terminal;
- missing/degraded source health and coverage stay visible rather than being cosmetically normalized away;
- evidence drill-down preserves public-read membership and point-in-time semantics;
- keyboard-first dense workflows must not hide auditability behind hover-only or decorative interactions.

### 6. ADVANCED_INTELLIGENCE_EXPERIMENTS

Only after the prospective baseline exists and the read plane can expose it without semantic mutation:
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
