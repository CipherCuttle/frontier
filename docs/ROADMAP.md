# FRONTIER Roadmap

Status: CURRENT_IMPLEMENTATION_STATE_V0

Snapshot base: `main@012bfffecc761c0ff25df9deeb730bba63e5103f`.

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

## Current system capability

FRONTIER can currently:
- acquire two zero-paid/keyless authoritative structured source lanes;
- keep the hostile fetch role DB-blind;
- reject forbidden/private network targets and bounded-resource violations;
- normalize PyPI releases and CISA KEV items into canonical observations;
- preserve first-durable `observed_at`, collection causality and source health;
- replay and verify canonical evidence deterministically;
- distinguish transport, freshness, completeness and schema health.

FRONTIER cannot yet:
- observe a live ATTENTION lane;
- observe a live DISCOVERY lane;
- establish cross-source evidence independence / syndication structure;
- group observations into topics/episodes;
- compute a prospective naive trend baseline;
- publish immutable public intelligence snapshots;
- serve a public read API;
- render the operator terminal.

## Immediate repository-control gap

GitHub reported `main` unprotected at this roadmap snapshot. Exact-head merges and CI reduce risk but do not replace branch/ruleset protection. Record this as debt and enable protection before parallel agent development becomes routine.

## Priority sequence

### 0. Repository control hardening

Goal: protect canonical `main` from accidental/direct writes while preserving the reviewed PR workflow.

Required outcome:
- branch protection or ruleset for `main`;
- required verification check(s) where supported;
- PR-based merge path retained;
- no bypass assumption embedded in automation.

This is operational governance, not a product phase.

### 1. SOURCE_DIVERSITY_V0 — NEXT PRODUCT PHASE

Goal: create structurally different live evidence roles so emergence, attention, discovery, syndication and coverage can be tested empirically.

Preferred first lanes:
- Hacker News public API as `ATTENTION`;
- GDELT as `DISCOVERY`;
- one additional overlapping technical/research lane selected through the existing source gates, with Hugging Face, arXiv or GH Archive as leading candidates.

Acceptance direction:
- same external root appearing through multiple attention/discovery observations does not become multiple factual confirmations;
- source outage/degradation remains visible;
- backfill/recovery bursts do not become organic emergence;
- new source adapters do not require edits to unrelated adapters or future ranking code;
- all sources pass technical, policy, information-value and reliability gates.

Explicit exclusions:
- no advanced trend score;
- no entity-resolution authority;
- no embedding/vector dependency;
- no public frontend.

### 2. GROUPING_BASELINE_V0

Goal: establish the simplest defensible observation grouping/dedupe layer needed to say that multiple observations concern the same episode without pretending to know true ancestry.

Method:
- label a representative corpus;
- compare canonical URL / exact content / title / SimHash / MinHash / TF-IDF and similarly simple candidates;
- select the simplest Pareto-efficient method that meets the required cases;
- preserve propagation magnitude separately from evidence independence;
- keep uncertain provenance reversible and explicit.

No embeddings are authorized unless simpler methods fail measured requirements.

### 3. BASELINE_INTELLIGENCE_V0

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
