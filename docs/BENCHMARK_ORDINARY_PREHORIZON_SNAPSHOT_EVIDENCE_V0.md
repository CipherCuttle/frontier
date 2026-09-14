# BENCHMARK ORDINARY PRE-HORIZON SNAPSHOT EVIDENCE V0

Status: `IMPLEMENTATION_CANDIDATE`

Parent authority:

- `FRONTIER_VALUE_OBSERVATORY_V0`
- `BENCHMARK_CAPTURE_V0`
- `BENCHMARK_EXECUTOR_READINESS_V0`
- `BENCHMARK_ORDINARY_HORIZON_SAFETY_PROOF_V0`

Base SHA: `2cde7d180cf94499849090360cc262f6eacdbde3`.

## Objective

Define and hostile-test the smallest credible prospective evidence route for the frozen seven-source `ORDINARY_AGGREGATION` comparator without implementing the comparator, scheduler, scored persistence, or activation.

The predecessor phase established that none of the seven frozen sources currently has sufficient trusted retrospective collection-state evidence. This phase does not weaken that result. It specifies what a prospectively captured immutable snapshot would have to bind before a later phase may attempt a real snapshot producer.

Current scientific state remains:

```text
HORIZON_SAFETY_EVIDENCE_COMPLETE: 0 / 7
ORDINARY_AGGREGATION_EXECUTOR_IMPLEMENTATION: NOT AUTHORIZED
SCORED_EXECUTION: NOT AUTHORIZED
```

## Task envelope

```text
BASE_SHA: 2cde7d180cf94499849090360cc262f6eacdbde3
OBJECTIVE: freeze a pure evidence contract for an immutable pre-horizon ordinary-comparator snapshot
ALLOWED_PATHS:
  - src/frontier/application/value_observatory_ordinary_snapshot_evidence.py
  - tests/unit/test_value_observatory_ordinary_snapshot_evidence.py
  - experiments/value_observatory_v0/ordinary_prehorizon_snapshot_evidence_v0.json
  - docs/BENCHMARK_ORDINARY_PREHORIZON_SNAPSHOT_EVIDENCE_V0.md
FORBIDDEN_PATHS:
  - migrations/**
  - sources/registry/**
  - acquisition runtime/fetcher changes
  - GitHub Actions workflow/scheduler changes
  - ordinary-aggregation executor implementation
  - Web-LLM executor implementation
  - scored observatory persistence
  - benchmark source-set or protocol mutation
  - canonical public ranking/read-plane semantics
  - executor/protocol activation authority
ACCEPTANCE_CHECKS:
  - uv lock --check
  - uv sync --all-extras --frozen
  - uv run python scripts/verify.py
  - normal repository CI
REVIEW_BUDGET: one hostile review; one targeted re-review only if Critical/High repair is required
MERGE_AUTHORITY: false
```

## Why a prospective snapshot route

`BENCHMARK_CAPTURE_V0` already permits a mutable collection/list/ranking source to use a previously captured immutable snapshot whose collection state is bound to the exact benchmark horizon.

The seven-source audit showed why later reconstruction from current public state is generally unsafe:

- Hacker News exposes live top/new/best lists and change notifications, but no reviewed arbitrary historical front-page ranking query.
- Hugging Face exposes current model listing/search and real-time repo webhooks, but no reviewed arbitrary historical global model-list state.
- GitHub repository search exposes mutable current repository/search state, not historical result-set membership and ordering.
- GDELT accepts publication-time bounds, but its own DOC API documentation says scoring changes may be applied retroactively across the backfile.
- PyPI's frozen comparator lane is the current Latest Updates RSS feed. The Index API's monotonic `X-PyPI-Last-Serial` is useful supporting telemetry but does not silently replace that frozen RSS lane.
- arXiv has useful incremental/export interfaces, but later date filtering of a current index is not the same thing as preserving the exact frozen Atom collection state.
- CISA's same-authority Git mirror preserves content history, but embedded Git author/committer times do not prove when GitHub publicly received or exposed a commit.

A prospective snapshot avoids those retrospective-substitution attacks by sealing the actual public collection state before the benchmark cutoff.

## External publication/receipt anchor candidate

The candidate authority substrate is a GitHub Actions artifact produced in this public repository.

GitHub's Actions artifact API exposes server-side metadata including:

- artifact ID;
- artifact `created_at`;
- artifact SHA-256 digest;
- workflow run ID;
- workflow head SHA.

Official reference:

`https://docs.github.com/en/rest/actions/artifacts`

GitHub artifact attestations use Sigstore. For public repositories, GitHub documents that the Sigstore bundle is also written to an immutable publicly readable transparency log.

Official reference:

`https://docs.github.com/en/actions/concepts/security/artifact-attestations`

These properties make GitHub artifact metadata plus an attestation a stronger prospective receipt/publication candidate than a self-declared application timestamp or a Git commit's embedded author/committer time.

This phase does **not** trust caller-supplied copies of those fields. A later separately reviewed authority verifier must query and bind the external GitHub/Sigstore evidence independently.

## P1 repair: payload first, receipt second

The hostile review correctly identified a circular design in the first draft: an uploadable snapshot cannot honestly contain its own GitHub artifact ID, GitHub creation time, GitHub artifact digest, or later attestation because those values exist only after upload. Embedding them in the uploaded artifact would also make the artifact digest self-referential.

The repaired contract therefore has two distinct objects.

### 1. `OrdinarySnapshotPayloadClaim`

This is the object that can actually exist **before upload**. It contains:

- snapshot ID;
- exact target `knowledge_horizon`;
- frozen benchmark protocol digest;
- frozen source-registry version;
- exactly one source row for each of the seven frozen ordinary sources;
- source-contract digest per source;
- request-identity digest per source;
- raw-payload digest per source;
- canonical normalized-collection digest per source;
- retrieval-completion timestamp per source.

It contains **no** server-assigned artifact metadata and no attestation fields.

`ordinary_snapshot_payload_digest_v0` deterministically canonicalizes this payload and computes its SHA-256 digest. Source tuple order is normalized so equivalent payload content cannot receive a different digest merely by reordering the seven source rows.

### 2. `OrdinarySnapshotReceiptClaim`

This is a **separate post-upload receipt**. Only after GitHub has stored the artifact can it contain:

- repository identity;
- server-assigned artifact ID;
- server-reported artifact creation time;
- GitHub artifact digest;
- workflow run ID;
- workflow head SHA;
- the canonical `snapshot_payload_digest` computed before upload;
- attestation reference;
- attestation digest.

The pure gate requires the receipt's `snapshot_payload_digest` to equal a fresh canonical digest of the supplied payload. This removes the first-draft circularity and gives a later external verifier an explicit bridge:

```text
pre-upload canonical payload
    -> snapshot_payload_digest
    -> uploaded artifact
    -> GitHub artifact metadata/digest
    -> attestation
    -> separate receipt binding snapshot_payload_digest
```

A future independent verifier must download the sealed artifact and prove that the canonical payload inside it has exactly the `snapshot_payload_digest` named by the externally verified receipt. The current pure gate cannot confer that authority because the receipt fields are still caller supplied.

## Retention boundary

Raw response bodies are explicitly forbidden in the uploadable payload. The current source policy requires `raw_artifact_retention == NONE`; this phase does not create a hidden raw-response archive to work around that policy.

The normalized collection retained by a future producer must contain only the public metadata necessary to reproduce the frozen comparator's deterministic later selection/merge, plus provenance/digests. That sufficiency is not assumed by this phase; it must be proved by the future producer phase.

## Fail-closed structural rules

`assess_ordinary_snapshot_evidence_v0` rejects malformed or substitution-prone evidence when:

- a frozen source row is missing;
- an extra source row is supplied;
- a source appears twice;
- source rows target different knowledge horizons;
- the receipt's `snapshot_payload_digest` does not equal the canonical digest of the supplied uploadable payload;
- the artifact repository is not the frozen expected repository;
- the workflow head is not an exact 40-hex Git SHA;
- the external attestation reference is absent;
- raw response-body retention is claimed.

It returns `BLOCKED` when:

- the claimed artifact was created after the knowledge horizon;
- any source retrieval completed after the knowledge horizon;
- any source retrieval completion time is later than the claimed artifact creation time.

Even a structurally perfect payload plus receipt returns only:

`EVIDENCE_COMPLETE_PENDING_AUTHORITY`

There is deliberately no `READY_FOR_EXECUTOR_IMPLEMENTATION` or activation state.

## Source-specific candidate matrix

The frozen machine-readable matrix is:

`experiments/value_observatory_v0/ordinary_prehorizon_snapshot_evidence_v0.json`

All seven sources remain horizon-safety `BLOCKED_UNPROVEN` today. For each source, the new result is only that the already-frozen current public retrieval can plausibly be sealed prospectively by the same generic snapshot mechanism. No source's endpoint or semantics are changed.

### PyPI supporting serial

PyPI documents `X-PyPI-Last-Serial` on its Index API. A future snapshot producer may record that serial as supporting telemetry when available, but it must not replace the frozen `pypi.updates` RSS arm with the Index API or XML-RPC journal without separate protocol authority.

Official references:

- `https://docs.pypi.org/api/feeds/`
- `https://docs.pypi.org/api/index-api/`
- `https://docs.pypi.org/api/`

PyPI currently advises new integrations to use JSON/RSS/Index APIs rather than XML-RPC, so this phase does not introduce a new XML-RPC dependency merely to obtain historical journal state.

### GDELT backfile warning

GDELT's DOC API supports `STARTDATETIME`/`ENDDATETIME`, but its documentation also states that ranking/scoring models may later be refined and applied retroactively to the entire backfile. Therefore a later current-state query with an old end timestamp is not upgraded to point-in-time collection-state proof.

Official reference:

`https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/`

### HN and Hugging Face live-state support

HN's official API describes near-real-time top/new/best lists and change notifications. Hugging Face documents current Hub listing/search plus real-time repo webhooks. Those capabilities support prospective observation but do not by themselves establish arbitrary historical global collection state after the fact.

Official references:

- `https://github.com/HackerNews/API`
- `https://huggingface.co/docs/hub/api`
- `https://huggingface.co/docs/huggingface_hub/guides/webhooks`

## Important unresolved timing question

This phase intentionally does **not** invent a maximum pre-horizon snapshot age.

A snapshot completed before the horizon is causally safe from future leakage, but a snapshot that is too old could make the ordinary comparator artificially weak. The frozen benchmark already has source-health/cadence concepts, but this phase has not established that those existing semantics are sufficient to judge snapshot freshness for scored comparison.

Therefore the future producer/authority work must either:

1. demonstrate that existing frozen source-health/cadence authority already determines acceptable snapshot freshness without changing benchmark semantics; or
2. stop and create separately reviewed protocol authority before introducing any new lag tolerance.

It must not hide a new freshness rule inside implementation code.

## Next bounded implementation candidate

If this evidence-contract phase passes review and is merged, the next phase should be a **manual, non-scored snapshot producer probe**, not the ordinary comparator.

That probe should:

1. load the exact source registry from a frozen Git ref;
2. fetch the seven frozen public endpoints through the existing secure bounded fetcher without changing normal acquisition semantics;
3. require each successful body to be fully read before recording `retrieval_completed_at` and its raw payload digest;
4. normalize/canonicalize only the metadata required for later ordinary-comparator replay;
5. discard raw bodies;
6. construct the uploadable canonical snapshot payload and its `snapshot_payload_digest`;
7. upload **only that payload** as an immutable GitHub Actions artifact;
8. obtain GitHub's server-assigned artifact metadata/digest and generate the artifact attestation;
9. create a **separate post-upload receipt** binding those external fields to the precomputed `snapshot_payload_digest`;
10. independently verify the artifact metadata, attestation, downloaded artifact, and contained payload digest in a later authority step;
11. remain manual/non-scored until freshness and authority gates are closed.

The probe must fail rather than silently omit a frozen source.

## Non-escalation

This phase does not:

- implement or run the snapshot producer;
- schedule anything;
- change a source contract, endpoint, source set, or source policy;
- retain raw public response bodies;
- query or serialize FRONTIER private observation/history/grouping/projection/PEF/feature-ledger state;
- implement `ORDINARY_AGGREGATION` selection/scoring;
- construct a scored `ValueObservatoryCapture`;
- mutate benchmark cadence, alert budget, failure rules, or knowledge-horizon semantics;
- authorize executor implementation or benchmark activation;
- alter PEF_V1 or canonical public ranking.

## Verdict

The intended bounded phase verdict is:

`SNAPSHOT_EVIDENCE_CONTRACT_DEFINED / RUNTIME_PROOF_MISSING / HORIZON_SAFETY_REMAINS_0_OF_7 / NO_EXECUTOR_AUTHORITY`

Engineering success here means the future route is implementable and harder to substitute or backdate. It does not mean any of the seven source blockers has been scientifically closed yet.
