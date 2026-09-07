# PEF_V0 pre-freeze integrity repair

Status: `PREFREEZE_INTEGRITY_REPAIR_CANDIDATE`

Parent: `main@a1cd427696ce76dd07fcd28abf06012df5767b78`.

## Objective

Close two already-identified fail-closed defects before any durable PEF_V0 candidate freeze or confirmatory boundary is allowed.

## Defect 1 — incomplete source-contract binding could freeze

`collect_freeze_inputs()` returns `registry_entry_digests=None` when the registry is readable but one or more referenced source-contract files cannot be bound. The freeze builder previously treated that state as eligible for `FROZEN` when the top-level registry digest was present.

Repair: unavailable registry-entry digests now add an explicit drift reason and force `DRIFTED`.

## Defect 2 — unresolved opportunities could satisfy the resolved sample floor

The preregistration requires `min_resolved_opportunities_per_domain = 30`. The existing domain helper could report sample adequacy when the retained denominator was 30 but fewer than 30 opportunities were actually resolved, provided the 9000-bps resolved-label fraction also passed.

Repair: the confirmatory application boundary now fail-closes any such stale helper result by requiring `resolved_label_fraction_numerator >= 30` before a domain can remain sample-adequate or promotion-eligible.

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
