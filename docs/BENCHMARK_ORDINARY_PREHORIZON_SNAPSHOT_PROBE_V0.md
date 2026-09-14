# BENCHMARK_ORDINARY_PREHORIZON_SNAPSHOT_PROBE_V0

## Objective

Test the candidate `IMMUTABLE_PRECAPTURE_SNAPSHOT` route from
`BENCHMARK_ORDINARY_PREHORIZON_SNAPSHOT_EVIDENCE_V0` with a real, manual,
non-scored seven-source capture.

This phase is a falsification-first feasibility probe. It does not establish
horizon safety, executor readiness, benchmark activation, or superiority.

## Frozen boundaries

The probe:

- uses exactly the seven frozen `ORDINARY_AGGREGATION` source IDs;
- loads the source registry from the exact checked-out Git SHA;
- uses the existing `structured_public_v0` secure fetch policy;
- makes one primary-endpoint request per source, concurrently;
- does not use conditional requests, retries, fallback mirrors, FRONTIER DB state,
  grouping, projection, PEF, feature-ledger state, or scored artifacts;
- records `retrieval_completed_at` from the secure fetch result, after the body was
  fully consumed;
- hashes the raw body, normalizes it, then excludes the raw body from every persisted
  probe artifact;
- persists only canonical normalized public metadata sufficient to replay the
  captured source collection plus its digest and provenance claims.

A failed, rejected, malformed, digest-inconsistent, or content-type-invalid source
makes the seven-source payload unavailable. The workflow retains a diagnostic report
and fails closed. It never silently shrinks the comparator source set.

## Payload and receipt sequence

A successful probe follows the reviewed predecessor contract:

1. construct all seven normalized collections;
2. construct the pre-upload snapshot payload claim;
3. compute the canonical `snapshot_payload_digest`;
4. write one payload artifact containing the claim and digest-bound normalized
   collections, with no post-upload metadata and no raw response body;
5. upload that payload as an immutable GitHub Actions artifact;
6. attest the uploaded artifact digest with GitHub artifact attestation;
7. retrieve the artifact record back through GitHub's REST API;
8. create a separate receipt binding artifact ID, artifact digest, server
   `created_at`, workflow identity, payload digest, and attestation bundle digest;
9. run the predecessor pure evidence assessment for a diagnostic verdict only.

The receipt remains insufficient authority for scored use. A later independent
verifier must retrieve the artifact and attestation rather than trusting the receipt
writer's copies.

## Timing rule

This probe measures timing; it does not invent a freshness tolerance.

The predecessor evidence assessment already blocks source retrieval after the target
`knowledge_horizon` and artifact creation after the horizon. A mechanically complete
run can therefore still produce `BLOCKED` timing evidence.

No implementation in this phase may convert observed timing margin into a new
benchmark rule. Whether the existing frozen source cadence/health rules provide a
scientifically fair maximum snapshot age remains a later explicit authority decision.

## Manual workflow

`.github/workflows/ordinary-prehorizon-snapshot-probe-v0.yml` is
`workflow_dispatch` only. It has no schedule.

Inputs:

- `knowledge_horizon`: explicit UTC target horizon;
- `snapshot_id`: unique non-scored probe identifier.

The workflow can only become a real GitHub-hosted runtime probe after the workflow
file is present on the default branch. Before that point, PR CI can verify the code
and tests but cannot count as runtime feasibility evidence.

## Acceptance

Engineering acceptance requires:

- exact seven-source membership;
- one request per frozen source;
- normalized replay content digest-bound into each source claim;
- no raw response body in persisted payload or report;
- source failure fails closed;
- payload uploaded before receipt construction;
- artifact REST digest agrees with the upload action digest;
- artifact attestation generated over the uploaded artifact digest;
- post-upload receipt remains separate from the payload;
- unit/CI verification passes;
- one independent hostile review, with only Critical/High repairs reopening targeted
  review.

Runtime feasibility is only `FEASIBILITY_OBSERVED` after a real manual run provides a
seven-source payload and an externally anchored receipt. It is not `HORIZON_SAFE`,
`EXECUTOR_READY`, or scored-execution authority.

## Non-escalation

This phase does not implement or authorize:

- a schedule;
- the ordinary comparator executor or top-K selection;
- scored persistence;
- Value Observatory activation;
- source-set or benchmark-protocol changes;
- a snapshot freshness threshold;
- the Web-LLM comparator;
- PEF_V1 changes;
- canonical public ranking changes.
