# FRONTIER Roadmap

Status: CURRENT_IMPLEMENTATION_STATE_V1

Snapshot parent: `main@bb105d03cacba0d7bee4b3f871c1a1e5231fb3f0`.

This file records the canonical repository implementation state and current priority after merge of
PR #30. It does not override `docs/CONSTITUTION.md`, accepted ADRs, frozen phase authorities, or
scientific non-escalation rules. If this roadmap conflicts with higher authority, implementation
fails closed until governance is repaired.

Do not infer product phase from GitHub pull-request number. Governance, preflight, repair, and
implementation PRs intentionally make repository numbering diverge from product sequencing.

## Current system state

FRONTIER is now an evidence-native, point-in-time emerging-technology intelligence system with:

- seven live source lanes: `arxiv.cs-ai`, `cisa.kev`, `gdelt.frontier`, `github.ml-repos`,
  `hf.models`, `hn.frontpage`, and `pypi.updates`;
- hostile bounded acquisition, append-only canonical evidence, deterministic replay, and explicit
  source health/coverage semantics;
- deterministic episode grouping with explicit `GROUP`, `NO_GROUP`, and `AMBIGUOUS` behavior;
- a permanent naive prospective baseline with retained COMPLETE snapshots and receipts;
- a GET-only FastAPI public read plane and deterministic OpenAPI/TypeScript client contracts;
- a dense keyboard-first React/Vite operator terminal over the read plane;
- production-oriented cadence telemetry, database readiness, backup/restore recovery drills, and
  application-store capacity measurements;
- merged experimental intelligence infrastructure for PEF_V0 ranking, shadow runs,
  candidate-freeze receipts, preregistered evaluation receipts, feature vectors, analysis,
  experimental read models, and an EXPERIMENTAL terminal lens;
- a bounded entity/provenance experimental lab, canonical-to-experimental bridge, and shadow
  evaluation path;
- a prospectively frozen, reproducible `ENTITY_GROUND_TRUTH_PROTOCOL_V2` plus pure offline
  validator;
- a fail-closed real-trust preflight and pure offline real-trust material candidate validator.

The canonical direction remains:

`LIVE SOURCES -> HOSTILE ACQUISITION -> APPEND-ONLY EVIDENCE -> PIT SEMANTICS -> EPISODES -> BASELINE / EXPERIMENTS -> RECEIPTS -> READ PLANE -> CLIENTS`

Experimental or agent-facing layers do not acquire canonical truth authority merely by being
implemented, merged, retrieved, ranked, or displayed.

## Merged implementation history

| Work | GitHub PR(s) | State | Result |
|---|---:|---|---|
| Canonical governance / evidence / acquisition foundation | #1-#7 | CLOSED | Constitution, ADRs, append-only evidence, hostile fetch/source contracts, five-source live acquisition and source diversity |
| Grouping baseline | #8 | CLOSED | deterministic guarded grouping with explicit ambiguity and PIT-safe receipts |
| Baseline intelligence | #10 | CLOSED | permanent naive prospective activity comparator, COMPLETE snapshots and receipts |
| Public read plane | #12 | CLOSED | GET-only FastAPI, auditable RADAR/NOW/TRENDING, evidence/health drill-down, generated contracts |
| Operator terminal | #14 | CLOSED | dense keyboard-first React/Vite client preserving server authority and snapshot identity |
| Advanced-intelligence authority | #16 | CLOSED | frozen comparator/evaluation contract; no promotion granted |
| Domain expansion + operations | #17 | CLOSED | arXiv + GitHub lanes, seven-source registry, readiness, recovery and capacity workflows |
| Experimental intelligence implementation | #18 | CLOSED | PEF_V0, shadow execution, freeze/evaluation receipts, feature vectors, analysis, experimental read plane/lens |
| Entity/provenance lab | #19 | CLOSED | transparent experimental entity/provenance candidates on frozen synthetic corpus |
| Canonical -> experimental entity/provenance bridge | #20-#21 | CLOSED | one-way bounded bridge and offline coverage diagnostics |
| Entity/provenance shadow evaluation | #22-#23 | CLOSED | frozen hostile evaluation authority + offline diagnostic evaluator; no promotion |
| Entity ground-truth V0 authority | #24 | CLOSED | candidate-disjoint human adjudication protocol authority; real quality remains unproven |
| Agent Context Plane roadmap direction | #25 | CLOSED / PARKED | architecture direction locked; no implementation authority |
| Ground-truth v1 reproducibility repair | #26 | CLOSED | v1 missing-builder defect failed closed; v1 left immutable |
| Ground-truth protocol v2 freeze | #27 | CLOSED | prospective deterministic builder/spec, packet schema, 24 hostile cases and exact digests |
| Ground-truth protocol v2 offline validator | #28 | CLOSED | pure offline packet expansion + semantic validator; synthetic conformance only |
| Real-trust preflight | #29 | CLOSED | fail-closed prerequisites for real externally supplied trust material |
| Real-trust material candidate validator | #30 | CLOSED | pure offline validator for externally supplied candidate material; no real material frozen |

## Scientific and authority state

The following remain authoritative after PR #30:

- entity candidate: `transparent-entity-hybrid-v0`;
- entity quality: `INSUFFICIENT_INDEPENDENT_GROUND_TRUTH`;
- provenance quality: `BLOCKED_NO_EXPLICIT_DERIVATION_EVIDENCE`;
- promotion: `UNAVAILABLE`;
- real label collection: **NOT AUTHORIZED**;
- candidate quality PASS/FAIL: **NOT AUTHORIZED**;
- canonical entity truth: **NOT AUTHORIZED**;
- production provenance truth: **NOT AUTHORIZED**;
- experimental ranking merge: **NOT promotion**.

Synthetic protocol fixtures, test roots, test signatures, model output, source multiplicity,
agreement, mirrors, bridge-native IDs, or validator acceptance cannot be upgraded into independent
real-world ground truth.

## Current hard blocker — real entity ground truth

The entity-ground-truth chain has reached an external-material boundary.

Next phase when its prerequisites actually exist:

`ENTITY_GROUND_TRUTH_REAL_TRUST_MATERIAL_V0`

That phase requires genuine externally supplied, non-placeholder public trust material, including
at minimum:

- two distinct real human adjudicator identity attestations bound to exact public keys;
- subject-controlled proof-of-possession under those bound adjudicator keys;
- complete public verification material for adjudicator, service-sealing, durability-publication,
  and identity-attestation roles;
- independently attested controller separation across the required roles;
- independently anchored terminal content -> upstream-equivalence expectations;
- content-addressed provenance material;
- authenticated validity/revocation state and current-head binding.

FRONTIER, its tests, its model tooling, and repository automation may not invent, synthesize,
self-attest, or substitute those prerequisites. Until they are supplied out-of-band, this lane is:

`BLOCKED_PENDING_REAL_TRUST_ROOT_MATERIAL`

The block is a scientific/trust-boundary condition, not a missing implementation task.

## Advanced intelligence status

`ADVANCED_INTELLIGENCE_EXPERIMENTS` is no longer a future implementation phase. Its V0 authority
and experimental infrastructure are merged.

However:

- PEF_V0 remains `EXPERIMENTAL_SHADOW` unless a separately authorized promotion chain succeeds;
- candidate-freeze and evaluation machinery do not themselves create evidence of candidate value;
- entity/provenance experimental results remain diagnostic where independent ground truth or direct
  derivation evidence is unavailable;
- no advanced model may silently replace the permanent naive baseline.

The permanent baseline remains the control for future prospective evaluation.

## Agent Context Plane — direction locked, implementation parked

`docs/ROADMAP_AGENT_CONTEXT_PLANE_V0.md` remains the authority for this future direction.

Canonical one-way boundary:

`CANONICAL FRONTIER -> READ-ONLY AGENT CONTEXT PROJECTION -> RETRIEVAL/CONTEXT -> TRANSPORT ADAPTERS -> EXTERNAL AGENTS`

Preferred earned sequence remains:

1. `AGENT_CONTEXT_PROTOCOL_V0`
2. `AGENT_RETRIEVAL_EXPERIMENT_V0`
3. `AGENT_CONTEXT_SELECTION_V0`
4. `AGENT_TRANSPORT_ADAPTER_V0`

This roadmap reconciliation does **not** authorize any of those implementations.

Before Agent Context implementation begins, its existing gate still requires:

- the real independent entity-ground-truth/evaluation path required by current authority to be
  handled as separately authorized work;
- the canonical roadmap to reflect actual merged implementation state;
- `AGENT_CONTEXT_PROTOCOL_V0` to receive its own bounded authority and hostile corpus.

This reconciliation satisfies only the roadmap-state prerequisite. The external real-ground-truth
prerequisite remains blocked, so Agent Context implementation remains parked.

## Repository control state

The old roadmap statement that `main` is unprotected is no longer operationally accurate.

GitHub currently has active repository ruleset `main-pr-verify-gate` applying to `refs/heads/main`
with:

- pull-request workflow required;
- required status check `verify`;
- no bypass actors;
- current user bypass reported as `never`.

`docs/DEBT_REGISTER.md` remains the canonical debt authority. This roadmap therefore records the
observed control as satisfied evidence but does not silently close or delete D007; debt-register
closure, if still required there, must be performed explicitly against that evidence.

## Current priority sequence

### 0. ROADMAP_RECONCILIATION_POST_REAL_TRUST_VALIDATOR_V0 — CURRENT GOVERNANCE WORK

Goal: reconcile the canonical roadmap from its stale post-#14 snapshot to the actual merged state
through PR #30.

Scope is governance/documentation only. No runtime, schema, source, ranking, entity/provenance
truth, API, terminal, embedding, vector, MCP, or model authority is created by this transition.

### 1. ENTITY_GROUND_TRUTH_REAL_TRUST_MATERIAL_V0 — BLOCKED ON EXTERNAL INPUT

When genuine external material exists, freeze and validate it against the merged real-trust
preflight and offline validator. Do not use synthetic substitutes.

Even successful material validation will not by itself authorize real label collection, candidate
quality PASS/FAIL, promotion, or canonical entity truth. Those require later separately frozen
authority.

### 2. REAL INDEPENDENT ENTITY-GROUND-TRUTH / QUALITY EVALUATION — FUTURE AUTHORITY

After valid real trust material is frozen, separately authorize real collection/evaluation with the
candidate-disjoint, blinded, PIT-safe, content-addressed protocol. Keep evaluation evidence and
promotion authority distinct.

### 3. AGENT_CONTEXT_PROTOCOL_V0 — PARKED

Once its gates are satisfied, freeze a deterministic read-only resource protocol before runtime
implementation. Structured canonical semantics remain primary; historical `as_of` must fail closed
unless every derived projection is horizon-valid; generated interpretation has no V0 authority.

### 4. AGENT_RETRIEVAL_EXPERIMENT_V0 — PARKED

Structured/lexical retrieval is the permanent simple comparator. Semantic/hybrid retrieval must
prove incremental value before pgvector or any larger vector infrastructure is authorized.

### 5. AGENT_CONTEXT_SELECTION_V0 — PARKED

Treat token-bounded context selection as an auditable ranking/selection algorithm with explicit
identity, truncation, point-in-time binding, and non-escalation rules.

### 6. AGENT_TRANSPORT_ADAPTER_V0 — PARKED

Keep application/domain contracts transport-neutral. HTTP/OpenAPI remains valid. MCP may be added
only as an adapter after separate authority; MCP does not become architecture or truth authority.

### 7. DOMAIN EXPANSION + OPERATIONS — CONTINUOUS / BOUNDED

Continue source and operational work only through source-policy, trust-boundary, reproducibility,
capacity, recovery, and health/coverage gates. New domains or infrastructure do not inherit truth,
confirmation, or ranking authority merely by being connected.

## Carried debt

`docs/DEBT_REGISTER.md` remains the authority for accepted debt. No roadmap phase may silently
resolve, discard, or relabel a debt item; closure requires evidence against its recorded trigger and
an explicit debt-authority transition.

## Completion discipline

Each bounded implementation or governance phase follows:

`IMPLEMENT -> TEST -> ONE hostile review -> repair Critical/High -> ONE targeted re-review only if Critical/High repair was required -> CLOSE -> MOVE FORWARD`

Medium/Low findings do not restart a phase unless they undermine the phase objective, evidence,
frozen authority, security/integrity, or fail-closed semantics.
