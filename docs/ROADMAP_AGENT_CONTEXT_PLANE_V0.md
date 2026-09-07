# FRONTIER Agent Context Plane Roadmap Addendum V0

Status: ROADMAP_DIRECTION_LOCKED / NO_IMPLEMENTATION_AUTHORITY

Parent roadmap snapshot: `main@fbf69ecd9f0bf810011e71e8dd2c1627e0b02011`.

This document records a future product/architecture direction only. It does not override `docs/CONSTITUTION.md`, accepted ADRs, the current `docs/ROADMAP.md`, or active phase authority. It does not authorize runtime code, embeddings, vector infrastructure, MCP exposure, model integration, persistence, new ranking, entity/provenance truth, or canonical mutation.

## Direction

FRONTIER should evolve into a point-in-time, evidence-native context substrate that arbitrary LLMs and agents can query efficiently without allowing an agent-facing layer to acquire canonical intelligence authority.

The V0 architecture direction is deliberately narrower than "vectorize Frontier" or "put an LLM inside Frontier".

Canonical rule:

`CANONICAL FRONTIER -> READ-ONLY AGENT CONTEXT PROJECTION -> RETRIEVAL/CONTEXT -> TRANSPORT ADAPTERS -> EXTERNAL AGENTS`

There is no reverse authority path from model output, semantic similarity, retrieval score, MCP client state, user/agent demand, or generated summaries into canonical FRONTIER evidence, ranking, entity identity, provenance, confirmation, health, or truth semantics.

## Naming

Use `AGENT_CONTEXT_PLANE_V0`, not `AGENT_INTELLIGENCE_PLANE_V0`.

Reason: the layer exposes and compresses already-governed FRONTIER state for agent use. It does not itself become an intelligence authority.

## Roadmap placement

This direction begins only after the active entity-ground-truth chain is closed and the canonical roadmap has been reconciled to the actual merged implementation state.

Preferred earned sequence:

1. `AGENT_CONTEXT_PROTOCOL_V0`
   - deterministic read-only resource model;
   - canonical enums remain primary;
   - versioned static semantic glosses only;
   - explicit point-in-time identity and trust classification;
   - no generated interpretation;
   - raw existing FRONTIER API access is the permanent control/baseline.

2. `AGENT_RETRIEVAL_EXPERIMENT_V0`
   - structured/lexical retrieval is the permanent simple comparator;
   - selective semantic retrieval is experimental only;
   - hybrid retrieval must prove incremental value;
   - use PostgreSQL-native mechanisms first; pgvector is permitted only after separate authority and only if earned by evaluation;
   - no external vector database unless measured requirements defeat the simpler PostgreSQL path.

3. `AGENT_CONTEXT_SELECTION_V0`
   - treat context selection as a ranking/selection algorithm, not neutral plumbing;
   - bind query, `as_of`, snapshot/universe, algorithm/configuration, selected resources, truncation, and token budget in a deterministic selection receipt where feasible;
   - authority remains `RETRIEVAL_ONLY`;
   - use progressive disclosure rather than context dumping.

4. `AGENT_TRANSPORT_ADAPTER_V0`
   - application/domain contract remains transport-independent;
   - HTTP/OpenAPI remains valid;
   - MCP may be added as an adapter, not as architecture authority;
   - A2A and autonomous internal agents remain deferred absent a measured requirement.

## Frozen design principles

### 1. Structured semantics remain primary

Agent-facing representations must preserve exact FRONTIER enums, identifiers, authority states, point-in-time semantics, health/coverage state, and evidence references.

Natural-language help may exist only as deterministic versioned glosses in V0. LLM-written summaries are non-authoritative convenience output and are not part of V0 authority.

### 2. Retrieval is not truth

- vector similarity != entity identity;
- vector similarity != factual corroboration;
- vector similarity != provenance;
- retrieval score != confidence;
- retrieval score != importance;
- retrieved source multiplicity != independent roots;
- context inclusion != FRONTIER endorsement.

### 3. Do not vectorize everything

Semantic indexing is appropriate only for selected content-bearing projections where semantic discovery is useful.

Structured fields such as timestamps, authority states, source roles, health, coverage, receipt identities, configuration digests, and point-in-time constraints remain structured filters/joins/audit dimensions rather than embedding semantics.

### 4. Point-in-time integrity applies to the agent plane

A current semantic projection must not silently answer a historical `as_of` query.

Every semantic/derived projection must bind at least:
- projection identity/version;
- projection input knowledge horizon;
- renderer identity/version;
- embedding model identity/version when applicable;
- index/retrieval identity when applicable.

Historical agent evaluation must distinguish truly point-in-time retrieval from retrospective retrieval using later representations.

### 5. Context selection is a form of ranking

Any mechanism that reduces a larger eligible evidence universe into a smaller token-bounded context can influence downstream conclusions. It therefore requires explicit algorithm identity, evaluation, non-escalation rules, and auditable selection/truncation metadata rather than being treated as neutral transport.

### 6. Progressive disclosure

Prefer layered detail:
- L0: identity, authority, epistemic warnings;
- L1: compact structured activity/evidence-role summary;
- L2: observation summaries;
- L3: full structured observations;
- L4: raw source evidence.

Any compressed response should disclose material omissions/truncation.

### 7. Read-only is necessary but not sufficient

External evidence is an active agent-security boundary even when FRONTIER exposes only GET/read operations.

All external-source-derived content supplied to agents must be classified as untrusted data with no instruction authority.

The V0 design must assume a downstream client may also possess filesystem, browser, GitHub, Slack, email, shell, or other mutating tools. FRONTIER therefore must not claim that read-only MCP/data access makes the overall downstream agent safe from prompt injection or cross-tool exfiltration.

### 8. No persistent agent memory by default

FRONTIER does not authorize untrusted retrieved evidence to become persistent downstream agent memory in V0.

Persistent memory ingestion requires separate policy/authority because memory poisoning can outlive the request that introduced malicious content.

### 9. No agent-demand feedback into world signal

Agent queries, tool calls, watchlists, retrieval popularity, click/selection telemetry, or generated outputs must not silently enter canonical emergence, attention, confirmation, provenance, or ranking semantics.

If future agent-triggered active enrichment exists, collection causality must remain explicit and must not manufacture organic momentum.

### 10. Transport neutrality

MCP is an interoperability adapter, not a domain dependency.

The internal application contract must remain independently usable through HTTP/OpenAPI or future transports without importing MCP lifecycle/session/tool concepts into canonical domain logic.

## Baselines and falsification

The agent-context program must be falsifiable rather than adopted because agent tooling is fashionable.

Permanent control:

`capable agent + existing structured FRONTIER read API`

Candidate sequence:

- A: web/public research only;
- B: existing FRONTIER structured API;
- C: deterministic agent-context resources;
- D: C + structured/lexical retrieval;
- E: D + semantic/hybrid retrieval;
- F: E + governed context selection.

Within a valid comparison, hold model family/version, reasoning effort, task, `as_of`, token budget, turn/tool budget, and relevant harness settings constant where possible.

Pre-register killable hypotheses:

- H1: agent-context access materially improves task success and/or groundedness over raw FRONTIER API access;
- H2: hybrid retrieval materially improves evidence recall over structured/lexical retrieval without unacceptable false retrieval, latency, or cost;
- H3: explicit FRONTIER epistemic metadata materially reduces unsupported semantic escalation;
- H4: governed context selection materially reduces context/tool cost without degrading task success or evidence quality.

If a candidate does not demonstrate meaningful incremental value, delete/defer that layer rather than preserving complexity.

## Evaluation dimensions

At minimum measure:
- task completion;
- evidence recall;
- evidence precision;
- unsupported factual claims;
- semantic-escalation errors;
- correct `UNKNOWN`/`UNAVAILABLE`/`AMBIGUOUS` behavior;
- future/as-of leakage;
- tool-selection errors;
- token consumption;
- tool-call count;
- latency;
- context volume;
- retrieval stability/replay characteristics.

Separate retrieval evaluation, agent-trajectory evaluation, and final-answer evaluation.

Use deterministic graders where FRONTIER already supplies exact machine truth about evidence existence, identity, `as_of`, authority, and expected non-escalation. LLM judges may supplement human/structured grading for subjective synthesis qualities but may not become the sole truth oracle.

Use development, hostile, held-out, and real-user task sets. Do not optimize and certify against the same synthetic corpus.

## Mandatory hostile cases before implementation

The future authority must freeze adversarial coverage for at least:
- prompt injection embedded in evidence;
- malicious evidence attempting cross-tool exfiltration;
- tool-result text impersonating system/tool instructions;
- Unicode/confusable entity names;
- semantically similar but different entities;
- differently worded same-episode evidence;
- future evidence/projection leaking into historical `as_of`;
- stale semantic projection mixed with newer canonical state;
- renderer/model/index drift;
- embedding-space/version mixing;
- context flooding/truncation hiding contrary evidence;
- recursive tool loops;
- cursor/snapshot mismatch;
- experimental output presented as canonical;
- missing/degraded coverage converted to confidence;
- ATTENTION converted to factual confirmation;
- mirrors/source multiplicity converted to independent corroboration;
- downstream memory overriding current FRONTIER state;
- tenant/scope leakage if private data is later supported;
- authorization token passthrough/confused-deputy behavior;
- cache results newer than requested `as_of`;
- agent/user demand feeding back into canonical trend signal.

## Infrastructure posture

Encourage:
- JSON-Schema-validated structured tools/resources;
- explicit resource identities;
- small composable tool surfaces;
- just-in-time context expansion;
- PostgreSQL/FTS first;
- selective pgvector only if separately authorized and measured useful;
- explicit traces/receipts around retrieval and context selection;
- least privilege and separate authorization scopes;
- transport-neutral application contracts.

Avoid in V0:
- LLM in canonical truth/ranking/entity/provenance paths;
- vector-only RAG;
- standalone vector DB without measured reversal gate;
- Kafka/event broker merely for agent deltas;
- autonomous internal FRONTIER agent;
- multi-agent orchestration;
- MCP write tools;
- persistent untrusted memory;
- A2A;
- hidden transport session authority;
- one magic confidence/relevance/truth score;
- model-specific domain contracts;
- silent projection/index lag;
- generated summaries masquerading as evidence.

## Product intent

If the experiments succeed, FRONTIER can become a machine-readable evidence substrate for external coding, research, investment, ecosystem, security, and other compatible agents.

The terminal remains one client of FRONTIER rather than the sole product surface.

The long-term moat hypothesis is not "RAG" or "MCP". It is the combination of point-in-time evidence, versioned semantics, source/coverage health, entity/provenance discipline, historical replay, prospective evaluation, and auditable context/retrieval interfaces that let agents reason over the live external world without silently upgrading weak evidence into truth.

## Current gate

This roadmap direction is intentionally parked behind the current entity-ground-truth chain.

Do not begin implementation until:
- `ENTITY_GROUND_TRUTH_V0` authority is closed;
- the real independent entity-ground-truth/evaluation path required by current authority is handled as separately authorized work;
- the canonical roadmap is reconciled to the actual merged implementation state;
- `AGENT_CONTEXT_PROTOCOL_V0` receives its own bounded authority and hostile corpus.

No merge or implementation is authorized by this addendum alone.
