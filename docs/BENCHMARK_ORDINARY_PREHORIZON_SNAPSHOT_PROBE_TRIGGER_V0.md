# BENCHMARK ORDINARY PREHORIZON SNAPSHOT PROBE TRIGGER V0

Status: `CANDIDATE_SUBORDINATE_AUTHORITY`

Parent authority:

- `BENCHMARK_ORDINARY_PREHORIZON_SNAPSHOT_PROBE_V0`

Base main SHA: `7add47f99e6e6e4fcbbc9d2097a49ba63de65b83`.

## Objective

Authorize one additional **manual, non-scored** invocation transport for the already-frozen seven-source pre-horizon snapshot probe so the probe can be requested through normal repository changes without paid browser automation.

This authority changes **trigger transport only**. It does not change the probe algorithm, source set, fetch policy, normalization, artifact sequence, timing semantics, scientific interpretation, or any benchmark/executor authority.

## Explicit supersession scope

This subordinate authority supersedes only the parent statement that `.github/workflows/ordinary-prehorizon-snapshot-probe-v0.yml` is `workflow_dispatch` only.

The parent `MANUAL_NON_SCORED` execution mode remains frozen.

Allowed manual trigger transports after this authority is merged:

1. `WORKFLOW_DISPATCH` — the existing explicit GitHub Actions manual dispatch with `knowledge_horizon` and `snapshot_id` inputs.
2. `REPOSITORY_REQUEST_FILE` — an explicit new immutable request file merged or committed to the frozen request path on `main`.

No other trigger transport is authorized by this phase.

## Repository-request contract

The frozen request path is:

`.github/probe-requests/ordinary-prehorizon-v0/*.json`

A repository-request execution is authorized only when all of the following hold:

- exactly one request file is **newly added** by the triggering `main` commit relative to its first parent;
- modifying, renaming, or deleting an existing request file does not authorize a probe and must fail closed;
- the request contains exactly the frozen V0 fields: `schema_version`, `snapshot_id`, `knowledge_horizon`, `non_scored`;
- `schema_version` equals `frontier-ordinary-prehorizon-probe-request-v0`;
- `non_scored` is exactly `true`;
- `snapshot_id` is a stable non-empty lowercase identifier suitable for artifact identity;
- `knowledge_horizon` is an explicit UTC `Z` timestamp aligned to one of the frozen benchmark boundaries `00:00`, `06:00`, `12:00`, or `18:00` UTC;
- the workflow resolves the request identity before running the existing producer;
- both allowed trigger transports converge on the same existing probe producer and receipt path;
- artifact names and attestation subject names bind the resolved request `snapshot_id` rather than a trigger-specific field.

A repository request is a manual operator action because a human or authorized development agent must deliberately create and merge/commit the immutable request file. The existence of a `push` event does not create recurring or scheduled authority.

## Fail-closed rules

The implementation must fail closed when:

- zero or more than one new request file is present in the triggering commit;
- the changed request path is a modification, deletion, or rename rather than a new file;
- request JSON is malformed;
- any extra or missing field is present;
- `non_scored` is not exactly `true`;
- the horizon is not exact UTC or is not aligned to a frozen boundary;
- the trigger event is neither one of the two allowed transports;
- the resolved request identity is unavailable to any downstream artifact/receipt step.

A failed repository request may produce workflow diagnostics but cannot silently fall back to another request, another boundary, another source set, or a scored execution.

## Preserved parent invariants

This authority does not change:

- exact seven-source membership;
- one primary request per frozen source;
- concurrent source requests;
- no retries or fallback mirrors;
- no FRONTIER private/history/grouping/projection/PEF/feature state;
- no raw-response-body persistence;
- normalized replay-content digest binding;
- fail-closed seven-source payload semantics;
- separate pre-upload payload and post-upload receipt;
- artifact attestation and server-metadata binding;
- no invented freshness tolerance;
- `FEASIBILITY_OBSERVED` as the strongest runtime-success label;
- requirement for an independent verifier before horizon-safety authority.

## Non-escalation

This phase does **not** authorize:

- a cron/scheduled trigger;
- recurring execution;
- automatic retry of a request file;
- editing an old request to create a new run;
- scored benchmark execution;
- ordinary comparator executor implementation;
- Value Observatory activation;
- benchmark protocol or source-set changes;
- source-registry changes;
- a freshness threshold;
- PEF_V1 changes;
- canonical ranking changes;
- a claim of horizon safety, executor readiness, decision value, or product superiority.

## Promotion rule

Merge of the governance PR containing this document and the paired machine-readable authority promotes only `BENCHMARK_ORDINARY_PREHORIZON_SNAPSHOT_PROBE_TRIGGER_V0` to `FROZEN_V0`.

Implementation of the repository-request trigger must occur in a later bounded implementation PR against the merged authority. The governance merge itself must not trigger a probe.
