# BENCHMARK ORDINARY PREHORIZON SOURCE COMPATIBILITY R1

Status: `CANDIDATE_SUBORDINATE_AUTHORITY`

Parent authorities:

- `BENCHMARK_ORDINARY_PREHORIZON_SNAPSHOT_EVIDENCE_V0`
- `BENCHMARK_ORDINARY_PREHORIZON_SNAPSHOT_PROBE_V0`
- `BENCHMARK_ORDINARY_PREHORIZON_SNAPSHOT_PROBE_TRIGGER_V0`

Base main SHA: `a279f8c29302f83de7ef8d83bd2163f33dbb8a87`.

Frozen predecessor identities:

- source registry: `sha256:c95b29078eb002145b75538b947cfb651cc1d5d7f2921b2347cf68b6065115ee`
- `hf.models` source contract: `sha256:162b504717e640017a8b17de67dd37e6426265e9aebc734013fffe00a8c750bb`
- `gdelt.frontier` source contract: `sha256:e43f006820dd85d369fe64b48329785684acbf1c2e28d12afd05fed7b35b20af`

Implementation must fail closed if its predecessor registry or either named source contract does not match these identities before applying the authorized delta.

## Objective

Repair only the compatibility defects proven by two distinct manual, non-scored ordinary pre-horizon probe boundaries without weakening the frozen seven-source evidence semantics.

This authority is intentionally split:

1. `hf.models` may receive one endpoint-query compatibility repair under a new source-registry digest.
2. `gdelt.frontier` may receive failure-only transport diagnostics sufficient to identify the existing `CONNECT_FAILED` exception class.

No GDELT endpoint, resolver, retry, fallback, fetch-policy, source-set, normalization, scoring, or benchmark change is authorized by this phase.

## Runtime evidence entering this phase

### Probe 1

- snapshot: `ordinary-prehorizon-probe-20260916t0000z-01`
- workflow run: `35031433693`
- merge SHA: `9dbfe7ce7e1e467827e63a8f84ded42a9cff20a3`
- failure artifact digest: `sha256:96f01f45b6148ece26d5917f141c986825f693c6805bb89011a4e933f695d53b`
- completed sources: 5/7
- `gdelt.frontier`: `CONNECT_FAILED`
- `hf.models`: `CONNECT_FAILED`

### Probe 2

- snapshot: `ordinary-prehorizon-probe-20260916t0600z-01`
- workflow run: `35041016248`
- merge SHA: `a279f8c29302f83de7ef8d83bd2163f33dbb8a87`
- failure artifact digest: `sha256:cadbb98e9ac8ad12e89df80c21f6ccf6a68feb6dab622c0ff2233bf1f5f6abc8`
- completed sources: 5/7
- `gdelt.frontier`: `CONNECT_FAILED`
- `hf.models`: `HTTP_400`

Across both probes, `arxiv.cs-ai`, `cisa.kev`, `github.ml-repos`, `hn.frontpage`, and `pypi.updates` completed.

## HF compatibility hypothesis and authorized repair

The current frozen `hf.models` endpoint contains:

`sort=lastModified&direction=-1&limit=100&expand=author,createdAt,lastModified,pipeline_tag,sha,tags`

Current official Hugging Face client/API surfaces retain `sort`, `limit`, and `expand` but no longer expose a `direction` argument. Probe 2 reached Hugging Face and received `HTTP_400`.

The bounded compatibility hypothesis is therefore:

`direction=-1` is stale and is the smallest removable query component that can explain the observed HTTP 400 while preserving the intended latest-model ordering and the fields consumed by the existing normalizer.

Implementation is authorized to:

- start only from the frozen predecessor registry and source-contract identities listed above;
- remove only `direction=-1` from the `hf.models` endpoint URL;
- preserve source id `hf.models`;
- preserve acquisition class, signal roles, transport, policy profile, authentication, cadence, finite-window declaration, accepted content types, limit, sort, expand fields, normalizer, and all other source-contract fields;
- recompute the source-registry content digest and update `source_registry_version` to the exact resulting digest;
- preserve the historical registry and source-contract identities through Git history; prior probe evidence remains bound to its historical Git SHA and historical registry digest.

This is a compatibility repair hypothesis, not a claim that HF feasibility is established. Only a later distinct non-scored probe can establish runtime compatibility.

## GDELT diagnostic authority

`gdelt.frontier` produced `CONNECT_FAILED` at two distinct aligned boundaries. The existing fetch layer already reduces connection exceptions to a safe exception-class string in `FetchFailure.safe_message`, but the ordinary probe report currently retains only `failure_code`.

Implementation is authorized to emit a separate failure-only diagnostic sidecar with schema `frontier-ordinary-snapshot-probe-transport-diagnostics-v0` containing only, per failed source:

- `source_id`;
- `failure_code`;
- `safe_message` copied verbatim from the existing `FetchFailure.safe_message` field.

The sidecar may be retained only with the existing failed-probe diagnostics artifact. It is noncanonical operational evidence and must not enter a successful snapshot payload, ranking, benchmark score, normalized collection, or source-health authority.

The diagnostic must not include raw response bodies, response excerpts, secrets, authorization material, resolved IP addresses, DNS answers, TLS certificates, request headers, response headers, stack traces, or unrestricted exception text.

No GDELT transport repair is authorized until this diagnostic identifies the failure class or later evidence separately justifies a repair.

## Registry and benchmark identity

This phase explicitly supersedes the prior probe non-escalation rule `source_registry_mutated: false` only for the single bounded `hf.models` endpoint-query maintenance change described above.

It does not supersede:

- exact seven-source membership;
- benchmark arm definition;
- benchmark protocol digest rules;
- one primary request per source;
- concurrent source requests;
- no retries;
- no fallback mirrors;
- no FRONTIER private state;
- no raw-body persistence;
- fail-closed seven-source payload semantics;
- source-contract/request/payload digest binding;
- separate pre-upload payload and post-upload receipt;
- no scored execution;
- no scheduler or recurring execution;
- no horizon-safety claim.

The repaired registry is a successor operational registry identity for later non-scored feasibility probes. It does not retroactively alter either prior failed probe and does not by itself become a scored comparator authority.

Before any future scored ordinary comparator activation, the exact source-registry identity used for scoring must be frozen under the applicable activation authority.

## Implementation gate

The compatibility implementation must occur in a later PR after this authority merges.

That implementation PR must:

1. verify the frozen predecessor registry and named source-contract digests before applying changes;
2. make only the authorized HF endpoint query change plus exact registry-digest update;
3. add the bounded failure-only transport diagnostic sidecar;
4. add focused tests proving the HF contract delta is exactly the authorized delta and diagnostics expose only the existing safe exception-class field;
5. pass exact-head CI;
6. receive one independent hostile review focused on authority drift, diagnostic leakage, source identity, and fail-closed behavior;
7. fix Critical/High findings only, with one targeted re-review if such fixes are required.

A later distinct aligned non-scored probe may be requested only after that implementation merges.

## Non-escalation

This phase does **not** authorize:

- changing the GDELT endpoint or query;
- changing DNS/address-selection logic;
- adding retries, fallback hosts, mirrors, proxies, or browser automation;
- weakening SSRF/TLS/HTTPS policy;
- changing any source other than the exact HF endpoint parameter removal;
- changing normalizers;
- changing the seven-source set;
- changing benchmark ranking/ordering/selection semantics;
- scored execution;
- ordinary-executor activation;
- Value Observatory activation;
- scheduler/cron/recurring execution;
- PEF changes;
- canonical public-ranking changes;
- claiming feasibility, horizon safety, executor readiness, decision value, or product superiority.

## Promotion rule

Merge of the governance PR containing this document and the paired machine-readable authority promotes only `BENCHMARK_ORDINARY_PREHORIZON_SOURCE_COMPATIBILITY_R1` to `FROZEN_R1`.

The governance merge itself must not alter source contracts, source-registry digests, probe code, workflow code, or trigger a probe.
