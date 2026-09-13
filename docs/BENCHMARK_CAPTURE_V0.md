# FRONTIER BENCHMARK CAPTURE V0

Status: `CANDIDATE_SUBORDINATE_AUTHORITY`

Parent authority: `FRONTIER_VALUE_OBSERVATORY_V0` (PR #78).

Artifact substrate: `VALUE_OBSERVATORY_ARTIFACT_SCHEMA_V0` (PR #79).

Promotion rule: this protocol becomes `FROZEN_V0` only after its PR is merged on top of the merged parent authority and artifact substrate. Until then, no scored capture may claim conformance to this protocol.

## 1. Purpose

`BENCHMARK_CAPTURE_V0` freezes the first prospective, equal-alert-budget benchmark protocol for the FRONTIER Value Observatory before any scored benchmark capture can support a product-value claim.

The protocol measures whether FRONTIER surfaces useful emerging developments earlier than simpler discovery approaches. It does not authorize a new ranking model, public recommendation surface, or mutation of PEF_V1.

## 2. Non-escalation boundary

This protocol MUST NOT:

- mutate the PEF_V1 candidate, registry, freeze receipt, window, operator, or confirmatory records;
- change canonical public ranking;
- add LLM output to truth, identity, grouping, ranking, or outcome authority;
- backfill a missed scored benchmark boundary;
- reuse future evidence to repair an earlier benchmark capture;
- expose scored item lists publicly before their registered outcome horizons mature;
- treat a benchmark failure as a FRONTIER win.

## 3. Scored capture unit

One scored capture is a shared point-in-time comparison at one exact `knowledge_horizon`.

Every scheduled boundary attempts all four frozen arms against the same:

- `knowledge_horizon`;
- 24-hour selection window ending at that horizon;
- global product domain scope;
- alert budget `K = 5`;
- source-health snapshot semantics;
- capture protocol version.

Each arm produces one immutable `ValueObservatoryCapture` artifact with `COMPLETE` or `FAILED` status.

A capture is not silently dropped because an arm failed.

## 4. Cadence and initial run

Scored boundaries are aligned to UTC:

- `00:00`;
- `06:00`;
- `12:00`;
- `18:00`.

The initial V0 run is 14 consecutive UTC days beginning at the first aligned boundary after all activation preconditions are satisfied.

There is:

- no early stopping;
- no replacement of missed boundaries;
- no retrospective backfill;
- no extension of the initial V0 run based on observed results.

A later run requires a separately recorded activation receipt and must not be pooled silently with V0 if protocol identity changes.

## 5. Alert budget and item handling

The maximum surfaced set is five items per arm per boundary.

Rules:

- underfilled `COMPLETE` captures are valid and remain underfilled;
- no arm may borrow unused budget from another arm;
- no arm may top up after the capture deadline;
- within one capture, `item_key` values must be unique;
- ordering must be deterministic and positions contiguous from 1;
- ties use canonical `item_key` lexical order after the arm's frozen primary ordering;
- repeated items across later boundaries remain visible as repeated alerts and are not removed post hoc.

Outcome reporting may later aggregate by opportunity, but the raw alert burden must remain recoverable.

## 6. Capture deadline

Execution may start at the aligned boundary and must finish within 30 minutes.

The frozen `knowledge_horizon` remains the aligned boundary even when `captured_at` is later.

Evidence with a publication/observation timestamp later than the knowledge horizon is ineligible for that capture.

If an executor cannot enforce the knowledge-horizon filter, that arm must be recorded `FAILED` for the boundary.

There is no scored retry after a failed boundary.

## 7. Frozen benchmark arms

### 7.1 FRONTIER_NAIVE_CONTROL

Purpose: permanent simple FRONTIER baseline.

Input:

- the canonical point-in-time candidate population available at the knowledge horizon;
- no observatory outcome sidecars;
- no future evidence.

Ordering:

1. newest eligible `observed_at` first;
2. canonical `item_key` lexical order.

No experimental emergence feature or PEF score may influence this arm.

### 7.2 FRONTIER_EXISTING_EXPERIMENTAL

Purpose: observe existing frozen experimental output without mutating its authority.

V0 uses the latest valid PEF_V1 output whose own knowledge boundary is at or before the benchmark knowledge horizon.

Rules:

- do not recompute PEF_V1 with later code or data;
- do not change its candidate or threshold;
- do not fill missing output from another model;
- if no valid frozen output is available by the capture deadline, record `FAILED`.

This arm is observational evidence only.

### 7.3 ORDINARY_AGGREGATION

Purpose: a competent but simple public-discovery comparator without FRONTIER hidden history.

Frozen source set:

- `hn.frontpage`;
- `pypi.updates`;
- `github.ml-repos`;
- `arxiv.cs-ai`;
- `cisa.kev`;
- `hf.models`;
- `gdelt.frontier`.

Execution:

- perform one current public retrieval attempt per frozen source;
- do not query the FRONTIER database, historical observation ledger, grouping state, projections, PEF state, or observatory feature ledger;
- preserve each source's returned raw payload digest and attempt status;
- merge eligible items by source-declared publication/update time descending;
- exclude items whose eligible time cannot be established at or before the knowledge horizon;
- break equal timestamps by canonical `item_key`.

An individual source transport failure is retained as source-health/failure evidence and does not by itself convert the whole arm to `FAILED` if the aggregation executor completed all source attempts. An executor-level failure that prevents the frozen attempt set from completing is `FAILED`.

### 7.4 WEB_LLM_BENCHMARK

Purpose: compare against a competent web-connected general LLM at the same alert budget.

The prompt text is frozen in the preregistration JSON.

Each capture must record:

- provider;
- exact model identifier;
- provider-visible model/version identifier when available;
- executor version;
- prompt digest;
- complete raw response digest;
- returned citations/URLs;
- capture time.

Rules:

- the LLM receives no FRONTIER private database state or hidden historical features;
- it may use only its ordinary web-connected retrieval capability;
- returned evidence must be filterable to the benchmark knowledge horizon;
- output beyond five items is truncated deterministically to the first five returned eligible items;
- fewer than five eligible items remain underfilled;
- provider refusal, tool failure, missing citations when required, or inability to enforce the horizon is `FAILED`;
- no silent provider or model fallback is permitted.

A provider/model/version change starts a new benchmark series segment. Results from materially different model identities must be reported separately before any pooled view.

## 8. Frozen web-LLM prompt

The canonical prompt is stored verbatim in `experiments/value_observatory_v0/benchmark_capture_v0.json`.

The prompt asks for up to five consequential emerging public developments from the preceding 24 hours, constrained to evidence available by the supplied UTC knowledge horizon, with source URLs and source timestamps.

The prompt must not mention FRONTIER's own surfaced items or ask the model to validate a FRONTIER candidate.

## 9. Failure semantics

Every scheduled arm is persisted.

`COMPLETE` means the executor completed the frozen protocol, even if the surfaced set is empty or underfilled.

`FAILED` means the frozen arm could not be executed faithfully.

Failure rules:

- failures are reported as failures, not zero-yield captures;
- a failed comparator does not create a FRONTIER win;
- pairwise win/loss metrics for that arm/boundary are unresolved;
- benchmark failure rate is itself mandatory output;
- there is no scored retry or backfill.

## 10. Equal-budget comparison rule

Only items within positions 1 through 5 are scored for any arm.

Comparisons with different budgets are invalid under V0.

No later report may expand one arm's item set, use hidden lower-ranked results, or compare a complete five-item set against another arm's unrecorded overflow.

## 11. Source health and coverage

Every capture binds exact source-health evidence available at or before the knowledge horizon.

Coverage degradation must remain visible.

Silence under inadequate outcome coverage cannot later be converted into a negative label.

Benchmark execution health and outcome-observation health are separate concepts and must remain separately auditable.

## 12. Causal contamination

All scored benchmark item lists remain shadow/unexposed until the longest registered outcome horizon for the associated opportunities matures.

If an item is exposed earlier through an independent existing FRONTIER surface, the later outcome artifact must record that exposure state.

No FRONTIER-caused attention may be silently counted as organic confirmation.

## 13. Provider and implementation changes

The following require a new protocol identity before scored use:

- alert budget change;
- cadence change;
- selection-window change;
- arm definition change;
- ordinary-aggregation source-set change;
- prompt text change;
- deterministic ordering change;
- benchmark failure-policy change.

Executor bug fixes that do not change protocol semantics must still record a new executor version.

A web-LLM provider/model update does not rewrite this protocol, but starts a new explicitly reported series segment.

## 14. Activation preconditions

The first scored V0 boundary is forbidden until:

1. `FRONTIER_VALUE_OBSERVATORY_V0` is merged and frozen;
2. `VALUE_OBSERVATORY_ARTIFACT_SCHEMA_V0` is merged;
3. this `BENCHMARK_CAPTURE_V0` protocol is merged and frozen;
4. the exact protocol JSON digest is recorded by the operator;
5. all four executors can emit the immutable capture artifact shape without mutating PEF_V1;
6. one independent hostile review for this bounded phase is complete.

## 15. Verification and reporting

Before activation, implementation must prove:

- identical knowledge horizon across all attempted arms;
- exact `K = 5` enforcement;
- deterministic item ordering;
- failed-arm persistence;
- no future-timestamp item acceptance;
- no PEF_V1 mutation;
- no canonical public-ranking mutation;
- no LLM truth/ranking authority.

The eventual value report must include every scheduled boundary and preserve wins, losses, misses, false alerts, unresolved outcomes, coverage failures, and benchmark failures.

## 16. V0 interpretation

Completion of this protocol and its initial run proves only that FRONTIER can perform a prospective, auditable benchmark under equal alert budget.

It does not establish product superiority, statistical significance, or permission to promote a new emergence-ranking model.
