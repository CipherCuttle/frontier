# FRONTIER Constitution V0

Status: CANDIDATE_FOR_CANONICAL_FREEZE

## Mission
FRONTIER is a public, non-personalized, point-in-time frontier-intelligence system for emerging technology, software, research, crypto, markets, security, and compatible future domains. It should surface important emerging changes earlier than ordinary aggregation while preserving enough provenance, uncertainty, history, and coverage state to challenge every conclusion.

## Product invariants
- One shared canonical public world state. Filters/watchlists may project it; they do not change canonical ranking truth.
- Observation is evidence/assertion, not truth.
- No mandatory paid data APIs or paid model APIs.
- No LLM in canonical ranking/truth path.
- Class-D fragile rendered-UI extraction must never be critical infrastructure.
- No access-control, CAPTCHA, paywall, or anti-bot circumvention.
- Source/system health is product data.

## Epistemic invariants
FRONTIER must not compress reality into one magic score. Canonical signal output separates at least: emergence strength, confirmation strength, evidence confidence, coverage completeness, manipulation/reflexivity risk, and freshness.

Strength != confidence != completeness.

Early emergence and later confirmation are different dimensions. RADAR may surface high-emergence/low-confirmation items. NOW means consequential current developments, not merely high-confirmation items. TRENDING is a versioned public projection over canonical evidence.

## Observation and time
Nothing may enter FRONTIER knowledge state before `observed_at`. Source/effective timestamps are contextual evidence and cannot retroactively grant earlier knowledge. Historical `as_of` reconstruction must use the FRONTIER knowledge horizon.

Canonical observations are append-only. Corrections/retractions are new observations/relations; historical evidence is not silently rewritten.

## Provenance
Explicit provenance and inferred provenance must be distinguishable. FRONTIER may represent earliest observed origin and bounded origin hypotheses; it must not claim omniscient true ancestry. Inferred provenance requires algorithm identity, confidence, and supporting evidence.

## Coverage
Missing data != observed absence. Source coverage must participate in interpretation. Source health is multidimensional: transport, freshness, completeness, schema validity.

## Collection causality
Every observation records why FRONTIER collected it. Initial reasons: SCHEDULED, DISCOVERY, ACTIVE_ENRICHMENT, BACKFILL. Active enrichment must carry a causal trigger when available so FRONTIER's own collection behavior cannot manufacture organic momentum.

## Assertion and trend state
Assertion lifecycle: OBSERVED, CORRECTED, RETRACTED.
Trend trajectory is separate: EMERGING, RISING, BREAKOUT, MATURE, COOLING.
`CORROBORATED` is not an assertion lifecycle state. `NOISE` is not a trend lifecycle state.

## Architecture
FRONTIER is a cleanroom modular monolith. Donor repos are research/donor lineage, not runtime authorities. Initial stack: Python 3.14 standard CPython intelligence plane; framework-independent domain; FastAPI only at transport boundary; Pydantic primarily at external boundaries; PostgreSQL 18 canonical mutable state; Psycopg 3 explicit SQL; TypeScript strict + React 19 + Vite frontend; generated OpenAPI TypeScript client.

Runtime roles may include `frontier-fetch`, `frontier-worker`, `frontier-api`, and static web while remaining one modular system.

`frontier-fetch` is a hostile trust boundary and must not possess canonical DB/admin credentials.

## Ledger and projections
Durable bounded observation precedes expensive interpretation. Derived state must be versioned/idempotent/replayable where feasible. Public snapshots must publish atomically; partial snapshots must not look complete.

## Baseline
At least one naive baseline must run prospectively alongside advanced ranking so FRONTIER can prove added value rather than complexity.

## Initially unauthorized infrastructure
Redis, Kafka, RabbitMQ, Elastic/OpenSearch, ClickHouse, TimescaleDB, Neo4j, vector DB, Kubernetes, GraphQL, independent microservices, LLM ranking, mandatory paid providers. These are unearned dependencies, not eternal bans. Reversal requires measured failing requirements, attempted simpler remedies, migration cost, and rollback path.

## Freeze discipline
Trend formulas, coefficients, thresholds, clustering algorithms, dedupe methods, entity resolution, provenance inference, source weights, embeddings, exact UI layout, and alert thresholds remain experimental until later evidence-backed authority.
