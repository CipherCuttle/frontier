# FRONTIER Roadmap

Status: CURRENT_IMPLEMENTATION_STATE_V0

Snapshot parent: `main@a084fe67b1d60fe73d67b08dcf0ae67dd7b822dc`.

Promotion rule for this file: merge of PR #7 promotes `SOURCE_DIVERSITY_V0` to CLOSED and makes `GROUPING_BASELINE_V0` the next product phase. Until that merge, the parent `main` state remains authoritative.

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
| Source diversity V0 | #7 | CLOSED_ON_MERGE | HN ATTENTION, GDELT DISCOVERY, Hugging Face PRIMARY_EMISSION; five-source registry |

## Current system capability after PR #7 promotion

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
- replay and verify canonical evidence deterministically.

FRONTIER still cannot:
- infer cross-source factual-root independence or true syndication ancestry;
- group observations into topics/episodes;
- compute a prospective naive trend baseline;
- publish immutable public intelligence snapshots;
- serve a public read API;
- render the operator terminal.

## Immediate repository-control gap

GitHub reported `main` unprotected at the roadmap snapshot. Exact-head merges and CI reduce risk but do not replace branch/ruleset protection. This remains D007 until protection is enabled and verified.

## Priority sequence

### 0. Repository control hardening

Goal: protect canonical `main` from accidental/direct writes while preserving the reviewed PR workflow.

Required outcome:
- branch protection or ruleset for `main`;
- required verification check(s) where supported;
- PR-based merge path retained;
- no bypass assumption embedded in automation.

This is operational governance, not a product phase, and remains open as D007.

### 1. SOURCE_DIVERSITY_V0 — CLOSED_ON_PR7_MERGE

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

### 2. GROUPING_BASELINE_V0 — NEXT PRODUCT PHASE

Goal: establish the simplest defensible observation grouping/dedupe layer needed to say that multiple observations concern the same episode without pretending to know true ancestry.

Method:
- label a representative corpus spanning primary-emission, attention, discovery, syndication, correction/retraction and ambiguous-alias cases;
- compare canonical URL / exact content / title / SimHash / MinHash / TF-IDF and similarly simple candidates;
- select the simplest Pareto-efficient method that meets the required cases;
- preserve propagation magnitude separately from evidence independence;
- keep uncertain provenance reversible and explicit;
- retain an explicit no-group / ambiguous outcome when evidence is insufficient.

Acceptance direction:
- two HN submissions to the same external root may share an episode while remaining two attention observations;
- GDELT syndication cascades may preserve propagation count without inflating independent-root count;
- similar titles or equal content digests never automatically prove common origin;
- corrections/retractions remain append-only evidence and can affect episode interpretation without rewriting history;
- grouping is deterministic/versioned for frozen inputs and `as_of`;
- historical `as_of` cannot use observations first seen later.

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
