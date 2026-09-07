# PEF_V0 pre-freeze integrity repair

Status: `PREFREEZE_INTEGRITY_REPAIR_CLOSURE_CANDIDATE`

Parent: `main@a1cd427696ce76dd07fcd28abf06012df5767b78`.

## Objective

Close two already-identified fail-closed defects before any durable PEF_V0 candidate freeze or confirmatory boundary is allowed.

## Defect 1 — incomplete source-contract binding could freeze

`collect_freeze_inputs()` returns `registry_entry_digests=None` when the registry is readable but one or more referenced source-contract files cannot be bound. The freeze builder previously treated that state as eligible for `FROZEN` when the top-level registry digest was present.

Repair:

- unavailable registry-entry digests add an explicit drift reason and force the preferred builder path to `DRIFTED`;
- `CandidateFreezeReceipt.__post_init__` independently rejects `FROZEN` receipts with `registry_entry_digests=None`, so direct construction and `dataclasses.replace` reconstruction fail closed as well.

## Defect 2 — unresolved opportunities could satisfy the resolved sample floor

The preregistration requires `min_resolved_opportunities_per_domain = 30`. The existing domain helper could report sample adequacy when the retained denominator was 30 but fewer than 30 opportunities were actually resolved, provided the 9000-bps resolved-label fraction also passed.

Repair:

- `frontier.domain.evaluation.sample_adequacy_pass()` now requires `resolved_label_fraction_numerator >= 30` at the authoritative domain layer;
- the application-layer `_enforce_resolved_sample_floor()` remains as defense in depth rather than the sole enforcement point.

The focused hostile regression proves 27 resolved + 3 `UNRESOLVED_COVERAGE` is rejected while the exact 30-resolved floor still passes when the remaining gates pass.

## Closure evidence

The broad pre-freeze review of `fc93f6449f1327bcc59cc99b22f4e23c81c8de09` found exactly the two P1 bypasses above.

The repaired code/test head `a0fc171c32c89d7d9e607606ac54ef22cc04f1a2` passed:

- `verify`;
- `ops-recovery`;
- `ops-capacity`.

The single permitted targeted Codex re-review then reviewed `a0fc171c32` for only those two P1 closures and reported no major issues. No second broad review is authorized or required.

## Non-scope

This repair does not change:

- PEF candidate ID, algorithm version, configuration digest, feature set, or ranking order;
- global K, evaluation window, outcome-label rules, domain taxonomy, statistical thresholds, or promotion semantics;
- source registry or source contracts;
- baseline authority or public ranking;
- entity/provenance authority;
- candidate-freeze creation or durable-freeze launch.

No candidate freeze may be created and no confirmatory window may begin from this branch.

## Completion discipline

`REPAIR -> FULL CI -> ONE hostile pre-freeze review -> repair Critical/High iff needed -> ONE targeted re-review iff Critical/High repair is needed -> MERGE -> VERIFY MAIN -> PREPARE DURABLE CANDIDATE FREEZE`
