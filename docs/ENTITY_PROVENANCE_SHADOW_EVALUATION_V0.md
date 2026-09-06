# ENTITY_PROVENANCE_SHADOW_EVALUATION_V0

Status: FROZEN_SHADOW_EVALUATION_AUTHORITY_CANDIDATE

Parent authority: `main@6e43ca0d588785c9d19a33a6dcdcd26944e43700`.

Promotion rule: merge of this authority PR promotes this document to `FROZEN_SHADOW_EVALUATION_AUTHORITY` and authorizes only the bounded offline evaluator, deterministic diagnostic report, and hostile tests defined here. It does **not** authorize entity/provenance truth, persistence, scheduling, API/terminal exposure, ranking changes, source-registry changes, schema changes, or promotion.

## Why this phase exists

`ENTITY_PROVENANCE_LAB_V0` selected transparent entity/provenance candidate families, and `ENTITY_PROVENANCE_BRIDGE_V0` proved that current canonical FRONTIER evidence can be mapped into those experimental inputs without inventing stronger semantics.

The bridge closure explicitly permits a separate shadow-evaluation authority next. It also established two hard scientific limits:

1. current entity evidence is largely the same provider-native identity evidence consumed by the candidate, so using it as the sole correctness label would be circular;
2. current canonical relations (`REFERENCES`, `CORRECTS`, `RETRACTS`) do not provide explicit derivation evidence and therefore cannot validate provenance derivation quality.

The next safe question is therefore:

**Can Frontier execute the frozen entity/provenance candidates over point-in-time canonical evidence reproducibly, expose real coverage/behavior, and fail closed on drift without pretending that self-derived signals are independent ground truth?**

## Lineage

- lab: `ENTITY_PROVENANCE_LAB_V0`;
- lab merge: `23cf10e0d65883c7b82356cf1bd18d9c56215604`;
- lab corpus digest: `sha256:04ac150abe4356ef06a6fda75429d5873d8dd519e79e29f5c5e2853f4432a386`;
- bridge authority merge: `0027ffcba7ab0d62be8101424ba8e5ecc09cb28c`;
- bridge implementation merge: `6e43ca0d588785c9d19a33a6dcdcd26944e43700`;
- bridge corpus digest: `sha256:34d1c75a7999f0338ae81add88e358d444f0bbd58d59696c08bb7ae0fbaf209f`;
- selected entity candidate: `transparent-entity-hybrid-v0`;
- selected provenance candidate: `explicit-reference-v0`.

Frozen shadow-evaluation corpus:

- path: `fixtures/entity_provenance/shadow_evaluation_corpus_v0.json`;
- schema: `frontier-entity-provenance-shadow-evaluation-corpus-v1`;
- case count: 24;
- exact Git blob SHA-1 identity: `58c91348a6f81f31d99aadf50a1c32fb22ac0882`.

The corpus intentionally binds its first 20 executable inputs to exact case IDs from the already-frozen bridge corpus at the bridge corpus digest above. The final four cases contain complete inline canonical fixture inputs. A bridge-case reference is not a suggestion: it resolves to the exact observations, relations, metadata, and `as_of` from that frozen bridge case. Fixture substitution is forbidden.

Every case now freezes:

- exact `as_of`;
- exact source-registry digest supplied to the evaluator;
- exact entity/provenance candidate identities;
- exact executable observation/relation input by immutable bridge-case reference or complete inline fixture;
- exact mandatory evaluation pair(s);
- exact integrity status;
- exact entity and provenance decision outcome, including literal `NO_EVALUATION` / `NOT_EVALUABLE` where applicable;
- exact PIT, malformed-evidence, native-signal, future-evidence, weak-relation, and direct-derivation counts;
- exact source-coverage contract;
- exact scientific quality statuses;
- exact empty forbidden-inference claim set;
- exact `UNAVAILABLE` promotion status.

There are no advisory `may` outcomes in the frozen expected diagnostics.

Exact source registry remains unchanged with digest:

`sha256:c95b29078eb002145b75538b947cfb651cc1d5d7f2921b2347cf68b6065115ee`.

## Authority boundary

This phase may implement only:

- an offline/in-memory shadow evaluator over the exact frozen inputs defined by the corpus;
- reuse of the merged `ENTITY_PROVENANCE_BRIDGE_V0` adapter;
- execution of the frozen selected entity/provenance candidates;
- deterministic experimental diagnostic reports;
- hostile tests for PIT, drift, replay, semantic non-escalation, underpowered evidence, and forbidden provenance-laundering signals.

It MUST NOT:

- choose convenient replacement fixtures after implementation results are visible;
- read arbitrary current database state as a substitute for a reconstructed historical horizon;
- add a migration or canonical schema field;
- persist evaluation output;
- schedule workers;
- add API or terminal surfaces;
- alter source registry membership/version;
- add new relation types;
- ingest or fabricate explicit derivation evidence;
- create canonical entity/provenance IDs;
- change episode grouping;
- change baseline or PEF ranking;
- produce a promotion PASS/FAIL decision;
- treat source multiplicity as independence;
- treat zero provenance coverage as evidence of no derivation.

## Point-in-time contract

For evaluation at `as_of = T`:

- observations are eligible only when canonical `observed_at <= T`;
- relations may influence evaluation only when durably known by `T`;
- future observations and relations remain explicitly counted as excluded evidence;
- ignored future observations must remain attributable to their source as well as globally;
- changing input iteration order must not change the canonical report bytes or report digest;
- source-registry digest mismatch makes the evaluation `INVALID_DRIFT` before quality counting.

## Entity evaluation contract

The frozen entity candidate is `transparent-entity-hybrid-v0` supplied only through the merged bridge.

The evaluator may report the exact frozen candidate behavior for each mandatory evaluation pair: `SAME_ENTITY`, `DIFFERENT_ENTITY`, `AMBIGUOUS`, or the explicit non-assessment states frozen by the corpus.

However current bridge/native-ID-derived evidence is not an independent correctness oracle for that same candidate. Therefore V0 freezes:

`entity_quality_status = INSUFFICIENT_INDEPENDENT_GROUND_TRUTH`

This status is mandatory even when all integrity tests pass or native-ID continuity looks perfect.

The evaluator may not emit entity-quality `PASS` or `FAIL`, accuracy, precision, recall, or promotion eligibility from self-derived bridge/native-ID labels alone.

A later independent entity-ground-truth program requires a separate frozen authority.

## Provenance evaluation contract

The frozen provenance candidate is `explicit-reference-v0`.

Current canonical relation types remain only:

- `REFERENCES`
- `CORRECTS`
- `RETRACTS`

None is authorized as explicit derivation evidence. Therefore V0 freezes:

`provenance_quality_status = BLOCKED_NO_EXPLICIT_DERIVATION_EVIDENCE`

and:

`direct_derivation_evidence_count = 0`

unless a future separately merged authority changes the evidence substrate. This evaluator itself may not accept ad-hoc stronger relation inputs to escape the block.

The frozen hostile corpus explicitly exercises all presently identified laundering paths. None of these signals may become `DIRECT_DERIVATIVE`, true origin, provenance root, or factual independence:

- `REFERENCES`;
- `CORRECTS`;
- `RETRACTS`;
- exact/mirrored text;
- earliest `observed_at`;
- GitHub `fork` booleans without separately authorized explicit parent evidence;
- shared canonical URLs, including a pair where both sources otherwise have supported bridge identities;
- source multiplicity;
- zero direct-derivation coverage.

`NO_LINK_EVIDENCE` is never factual independence.

## Integrity status

V0 separates evaluator integrity from scientific quality.

Allowed integrity states:

- `COMPLETE_DIAGNOSTIC` — the frozen evaluator ran over conforming exact inputs and produced the exact deterministic diagnostics required by the corpus;
- `INVALID_DRIFT` — frozen identity/config/registry/PIT constraints were violated.

`COMPLETE_DIAGNOSTIC` does not mean candidate quality passed.

## Required report fields

A deterministic shadow report must include at least:

- phase/schema version;
- `as_of`;
- exact registry digest;
- exact bridge/candidate identities;
- integrity status and drift reasons;
- PIT-eligible observation count;
- per-source supported/degraded/unsupported coverage;
- native-ID signal count;
- malformed identity-field count;
- ignored future observation count globally and per source;
- ignored future relation count;
- entity decision outcome(s);
- provenance decision outcome(s);
- direct-derivation evidence count;
- forbidden-inference claims, which must remain the exact empty set for V0;
- entity quality status;
- provenance quality status;
- promotion status `UNAVAILABLE`;
- canonical report digest.

Zero values must remain literal zeros and must not be narrated into stronger conclusions.

## Frozen hostile evaluation corpus

The 24 executable cases attack:

- supported native-identity continuity;
- conflicting stable identities;
- repository rename continuity via numeric ID only;
- malformed CISA/GitHub identity metadata;
- unsupported arXiv/GDELT/HN identity upgrades;
- PIT-future observation and relation leakage;
- registry drift before quality counting;
- deterministic replay under reordered inputs;
- circular entity validation using the candidate's own input signal;
- `REFERENCES` / `CORRECTS` / `RETRACTS` derivation escalation;
- mirrored-text derivation/origin inference;
- earliest-observation origin inference;
- GitHub fork-boolean derivation inference;
- shared-URL derivation/origin inference across two bridge-supported sources;
- zero-provenance-coverage and source-multiplicity independence claims.

The corpus is frozen before evaluator implementation. Its inputs, expected outputs, statuses, and evidence limits may not be weakened after implementation results are visible.

## Success / falsification

Implementation closes only if:

- all 24 frozen executable cases produce their exact mandatory diagnostics;
- deterministic replay is byte-identical with an identical report digest;
- registry drift fails closed before quality counting;
- no future evidence leaks through PIT boundaries;
- unsupported sources remain unsupported;
- malformed native identity evidence fails closed;
- no canonical relation or forbidden laundering signal becomes derivation/origin/independence evidence;
- `forbidden_inference_claims` remains empty in every frozen case;
- entity quality remains `INSUFFICIENT_INDEPENDENT_GROUND_TRUTH`;
- provenance quality remains `BLOCKED_NO_EXPLICIT_DERIVATION_EVIDENCE`;
- promotion remains `UNAVAILABLE`;
- one bounded hostile implementation review has no unresolved Critical/High defect after the normal single repair/re-review policy.

A scientifically honest result where the evaluator runs perfectly but both quality tracks remain underpowered is a **successful phase outcome**.

## Explicit exclusions

No persistence, migration, worker/scheduler, API, terminal, public labels, graph/vector database, LLM, learned model, source-registry change, relation-enum change, entity/provenance truth, or promotion.

## Closure discipline

Authority phase:

`AUTHORIZE -> FREEZE CONTRACT/CORPUS -> ONE hostile authority review -> fix Critical/High -> ONE targeted re-review only if needed -> VERIFY -> MERGE -> VERIFY MERGED TREE`

After authority merge:

`IMPLEMENT -> TEST -> ONE hostile implementation review -> fix Critical/High -> ONE targeted re-review only if needed -> CLOSE`

After closure, the only legitimate next scientific advances are separate authorities that earn genuinely independent entity ground truth and/or explicit provenance-derivation evidence. Neither may be smuggled into this evaluator.
