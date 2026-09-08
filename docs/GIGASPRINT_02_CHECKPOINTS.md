# GIGASPRINT_02 checkpoints

Build evidence only. This document grants no freeze, confirmatory, scientific, governance, or promotion authority.

## Final pre-merge closure receipt

Runtime/code head reviewed and verified before this docs-only closure commit:

`93e7a05156a37d8b68e1fa7b4a6cfc6ad8f04609`

State: `CODE_CLOSED / DOCS_ONLY_CLOSURE_HEAD_REQUIRES_STANDARD_CI`.

No real candidate freeze was created. No confirmatory execution or evidence collection occurred. No promotion decision was made.

### G2-01 — frozen-registry confinement

State: `CLOSED_VERIFIED`.

The confirmatory read/build path is confined to the frozen source universe and immutable frozen signal-role authority; mutable database source state cannot silently expand the scientific universe. The extra/stale-source contamination regression is carried in the exact-head PostgreSQL suite.

### G2-02 — freeze clock / GitHub publication authority

State: `CLOSED_VERIFIED`.

The bounded hostile trace found a real High after the first implementation pass: publication rows could be persisted without proving that the publication commit was the canonical GitHub `main` publication commit. The repair now:

- derives the publication record from the candidate-freeze receipt and immutable Git shape;
- verifies `origin` resolves to `CipherCuttle/frontier`;
- resolves GitHub `refs/heads/main` and requires it to equal the derived publication commit before persistence;
- forbids raw production publication persistence;
- revalidates the stored publication digest and canonical payload on load before its committer timestamp is trusted;
- keeps synthetic publication insertion entirely under `tests/`, outside the packaged `src/frontier` product surface.

Repair chain:

- `18d1df9579fa03c9edd62e6df654cb6e965f375b` — bind publication authority to GitHub main;
- targeted re-review found the remaining production `record_fixture_publication()` bypass;
- `93e7a05156a37d8b68e1fa7b4a6cfc6ad8f04609` — remove the unchecked production fixture seam.

### G2-03 / D011 — confirmatory evaluation authority

State: `CLOSED_VERIFIED`.

The exact verified G2-03 artifact was materialized into the PR branch before this closure cycle. Persisted evaluator authority is reconstructed only from persisted run IDs/class plus the bound freeze/publication/window evidence. Caller `confirmatory`, `durable_freeze_at`, and canonical-context inputs are restrictive/equality assertions only and cannot escalate authority.

Verified artifact provenance retained from the landing gate:

- workflow run: `34168874086`;
- artifact: `10035054581` (`g203-verified-bytes`);
- archive SHA-256: `f185666b635a9af13cdd351a077ec7a91df72a50d20ca45084c514ab81457324`.

Boundary regressions cover DEV non-escalation, wrong/foreign freeze, authoritative Git-publication window, caller timestamp equality, outside-window rejection, and mixed DEV + CONFIRMATORY rejection.

### G2-04 / D012 — shared freeze-persistence authorization

Implementation commit: `320a54a618bab2581a84dd3d293c7e1d5cab59cf`.

State: `CLOSED_VERIFIED`.

- `PostgresCandidateFreezeRepository` is read-capable by default but rejects `record_receipt()` unless constructed with an explicit `persistence_authorized=True` capability;
- the CLI retains the explicit `FRONTIER_FREEZE_PERSIST_AUTHORIZED=1` human/operator gate and only supplies the lower-level capability after that gate succeeds;
- fixture integration writes opt in explicitly;
- integration regression proves the default repository path raises `PermissionError` before writing a candidate-freeze row.

### G2-05 / D014 — DB-side confirmatory time gate

State: `CLOSED_VERIFIED`.

Confirmatory attempt eligibility is decided from canonical persisted durability/publication facts inside the PostgreSQL claim/authority boundary. Application wall-clock skew cannot admit a boundary that the persisted authority rejects; exact-boundary and skew regressions fail closed.

## Exact-head standard CI on final code head

All standard workflows completed successfully on `93e7a05156a37d8b68e1fa7b4a6cfc6ad8f04609`:

- `verify #401` — run `34208795484` — PASS;
- `e2e-postgres #60` — run `34208795369` — PASS;
- `ops-capacity #237` — run `34208795219` — PASS;
- `ops-recovery #241` — run `34208795236` — PASS.

The PostgreSQL workflow includes the full experiment lifecycle proof, isolated DB-bound integration suite, generated-client contract check, and backup/restore recovery drill.

## Review closure

The single bounded hostile review produced one material publication-authority High. That High was repaired. Because a Critical/High repair was required, one targeted re-review was performed; it found the unchecked production fixture writer described above. That bypass was removed and the repaired boundary was reverified before landing.

Final review disposition on the code head: `CRITICAL=0 / HIGH=0 unresolved`.

Medium/Low carried debt remains governed by `docs/DEBT_REGISTER.md` and does not reopen this sprint unless it violates a frozen invariant, corrupts evidence, or creates fail-open authority ambiguity.

## Docs-only closure rule

This checkpoint update intentionally changes documentation only, so its commit becomes the new PR head. It must receive the normal exact-head PR workflows before the sprint is called merge-ready.

If `verify`, `e2e-postgres`, `ops-capacity`, and `ops-recovery` all succeed on that docs-only head with no unexpected diff or branch drift, the completion verdict is automatically:

`GIGASPRINT_02_READY_FOR_MERGE`

No further receipt-only commit is required; that would create a self-referential CI loop.
