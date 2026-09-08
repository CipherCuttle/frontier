# PEF_V0 CONFIRMATORY RUN — ABORT RECORD (2026-09-08)

Status: PROPOSED_CANONICAL_RECORD / NO_PROMOTION_VERDICT

Experiment: `advanced-ranking-pef-v0`
Candidate: `prospective-primary-emission-freshness-v0`
Frozen publication commit: `db206cda7eed92b62c706a10089c2571b4381d66`
Frozen publication tree: `5134857849b03c0dcff4595c8c9fe1059ffe47a6`

## Classification

PEF_V0 confirmatory execution is **ABORTED_BY_OPERATIONAL_SCALABILITY_FAILURE**.

This is not a positive or negative scientific verdict on the candidate ranking hypothesis. The fixed confirmatory window did not complete and the retained partial evidence is not eligible for promotion.

Promotion remains **NOT AUTHORIZED**.

## Retained valid confirmatory evidence

Eleven successful CONFIRMATORY boundaries were durably persisted before the scalability failure:

- 2026-09-08T15:00:00Z
- 2026-09-08T15:05:00Z
- 2026-09-08T15:10:00Z
- 2026-09-08T15:15:00Z
- 2026-09-08T15:20:00Z
- 2026-09-08T15:25:00Z
- 2026-09-08T15:30:00Z
- 2026-09-08T15:35:00Z
- 2026-09-08T15:40:00Z
- 2026-09-08T15:45:00Z
- 2026-09-08T15:50:00Z

All retained attempts were DONE and their corresponding confirmatory runs were RAN. The latest retained worker heartbeat was `2026-09-08T15:55:07.401041Z` with drift state OK.

These rows remain immutable evidence of the aborted run. They MUST NOT be rewritten, deleted to hide the incident, backfilled, shifted to a new boundary, or pooled as confirmatory evidence under a successor freeze identity.

## Operational findings

### Session-lock endpoint mismatch

The deployed worker credential used Neon's transaction-pooled `-pooler` endpoint while the singleton lease used session-level PostgreSQL advisory locks.

Observed evidence included repeated `worker lease release failed: lock not held` messages and a FRONTIER advisory lock stranded on a PgBouncer backend session.

Recovery changed the root-only VM credential to the corresponding direct/session Neon endpoint after proving direct advisory-lock acquire/release. A root-only backup of the prior credential was retained on the VM. No credential value is recorded here.

Any successor that retains session advisory locks MUST fail closed on a known transaction-pooled endpoint.

### Frozen grouping/receipt scalability failure

The V0 grouping implementation assesses all unordered eligible observation pairs and explicitly retains all ambiguous pair assessments. The baseline input digest then canonicalizes the full grouping projection.

Evidence-universe growth on the successful V0 boundaries:

| as_of UTC | eligible observations | unordered pairs |
|---|---:|---:|
| 15:00 | 899 | 403,651 |
| 15:05 | 1,129 | 636,756 |
| 15:10 | 1,129 | 636,756 |
| 15:15 | 1,182 | 697,971 |
| 15:20 | 1,242 | 770,661 |
| 15:25 | 1,421 | 1,008,910 |
| 15:30 | 1,424 | 1,013,176 |
| 15:35 | 1,525 | 1,162,050 |
| 15:40 | 1,657 | 1,371,996 |
| 15:45 | 1,679 | 1,408,681 |
| 15:50 | 1,679 | 1,408,681 |

At approximately 19:40 UTC the retained source universe had grown to 2,425 observations, or 2,939,100 unordered pairs. Raw observation payload was only about 1.6 MiB total, so payload size was not the memory cause.

Kernel OOM evidence showed the FRONTIER Python process repeatedly reaching the service cgroup's exact 2,500 MiB hard limit, with approximately 2.55 GiB anonymous RSS, before being killed. Earlier `MemoryHigh=1800M` had instead produced prolonged memory-pressure throttling and a scientifically stale-but-active process.

## Reproduction

Two temporary isolated GitHub Actions benchmarks used the exact frozen grouping implementation with 2,425 same-day low-overlap synthetic observations. The temporary workflow was removed after measurement.

1. Grouping projection only:
   - 2,939,100 pairs
   - 2,939,100 ambiguous pair assessments
   - peak RSS: 785,936 kB
   - wall time: about 56.82 s
   - workflow run: `34271264471`

2. Grouping projection plus exact `baseline_input_digest()` canonicalization:
   - 2,939,100 ambiguous pair assessments
   - peak RSS: 3,457,236 kB (~3.30 GiB)
   - wall time: about 78.41 s
   - workflow run: `34271750873`

This quantitatively reproduces why the frozen 2.5 GiB worker cannot complete the current universe.

## Why hardware scaling does not rescue V0

From 15:50 to roughly 19:40, the eligible universe grew by 746 observations in about 230 minutes (~194.6 observations/hour). A simple linear scale stress test—not a scientific forecast—would imply roughly 128k observations after another 27 days and over 8 billion unordered pairs.

The frozen projection explicitly materializes ambiguous pair records, so both runtime and artifact volume scale quadratically. Increasing RAM would postpone rather than remove the fixed-window failure.

## Governance consequence

`GROUPING_BASELINE_V0` explicitly states that its initial O(n^2) implementation is acceptable only for a bounded baseline and that sustained scaling remains measured debt. It also requires explicit ambiguous pair assessments.

The PEF preregistration/candidate-freeze authority binds the exact implementation identity and requires `NEW_FREEZE_AND_RESTART` when bound identity changes.

Therefore:

- PEF_V0 MUST NOT resume under a patched implementation;
- its original fixed window MUST NOT be shifted or extended;
- missed boundaries MUST NOT be backfilled;
- the 11 retained boundaries MUST NOT count toward a successor confirmatory window;
- a scalable grouping representation requires a new grouping authority/version;
- a successor advanced-ranking experiment requires a new preregistration, freeze/publication identity, and fresh prospective window.

## Non-actions

This abort record does not:

- modify historical observations, collection runs, attempts, baseline snapshots, shadow runs, or receipts;
- authorize source-registry changes;
- authorize a PEF candidate promotion;
- determine whether the PEF ranking hypothesis is supported or unsupported;
- authorize a successor implementation before its own authority and bounded review complete.
