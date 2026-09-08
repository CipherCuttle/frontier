# GROUPING SCALABILITY V1 — Authority Review Receipt

Status: AUTHORIZED_FOR_IMPLEMENTATION_ONLY

## Authority inputs

- parent canonical commit: `db206cda7eed92b62c706a10089c2571b4381d66`
- initial authority commit: `690bf40ac728dc4ae63f473061fdf4e5c5c19f1d`
- reviewed authority content blob after repair: `22a1c9516ade82bb7e4498fa11437be72e143b8e`
- reviewed hostile/scale corpus blob after repair: `30554ae7d416bb29e8717a4bf81f1f686dcf3b2c`
- immutable V0 grouping oracle blob: `943affde20b08f500f8dba2716ffedfc428f58e1`

## One hostile authority review

Result: **Critical 0 / High 2**.

### H1 — insufficient end-window scale horizon

The initial gates stopped at 25k sparse observations plus a 5k dense case. Incident evidence showed a simple 27-day linear stress scale around 128k observations, so an implementation could pass authority while remaining likely to fail before a fresh 28-day window ended.

Repair:

- added a 150k mixed 30-day production-path gate;
- gate includes receipt generation;
- hardware-only scaling is explicitly not an acceptable substitute for a failed gate.

### H2 — mutable reference-oracle risk

The initial authority referred to `assess_pair` as the reference semantics but did not prevent V1 from editing that implementation and accidentally comparing the candidate to itself.

Repair:

- pinned reference commit/tree/blob and V0 algorithm/projection identities;
- prohibited using the mutable V1 implementation as both candidate and oracle;
- required isolated pinned execution or digest-bound oracle artifacts;
- required a clause-by-clause GROUP-completeness proof backed by executable bounded exhaustive comparison.

## One targeted re-review

Scope: H1 and H2 repairs only.

Result: **Critical 0 / High 0**.

The review budget for authority is closed.

## Authorization

Implementation may proceed only against the reviewed authority/corpus above.

This receipt does **not**:

- merge anything to canonical `main`;
- resume PEF_V0;
- authorize a PEF successor confirmatory run;
- authorize source/ranking/evaluation semantic changes;
- waive equivalence or scale gates;
- authorize candidate freeze/publication.

A successor PEF experiment remains a separate preregistration/freeze/publication decision after V1 grouping implementation passes all required evidence gates.
