# FRONTIER Planning Authority Index

Status: CANONICAL_V0

PR-00 promotion is complete. This directory now contains the canonical V0 planning/governance authority established before implementation, plus later reviewed preflight and roadmap artifacts that refine implementation state without overriding higher authority.

## Authority precedence

1. `CONSTITUTION.md`.
2. Accepted ADRs under `docs/adr/` for the specific decision they govern.
3. Explicit later phase/contract authorities for the implementation surface they govern, when they name their scope and do not contradict higher authority.
4. `P08_DATA_CONTRACT.md` for the canonical evidence-substrate contract established for PR-01.
5. P01-P07 planning/evaluation documents.
6. `SOURCE_POLICY.md` for source-governance details.
7. `DONOR_LEDGER.md` and `DEBT_REGISTER.md` for provenance/debt tracking.
8. `ROADMAP.md` for current implementation state, sequencing and next-phase priority.

Rules:
- Specific lower-level authority may refine but may not contradict higher-level authority.
- File order, numbering, modification time or GitHub PR number never silently supersedes another authority.
- A later authority may supersede an earlier decision only when it explicitly names the superseded decision and scope.
- Unresolved contradiction is fail-closed: implementation stops and governance is repaired before code chooses an interpretation.
- `ROADMAP.md` records what is done and what comes next; it cannot rewrite Constitution/ADR semantics.

## Closed implementation lineage

- PR #1: canonical governance / architecture authority — CLOSED.
- PR #2: canonical evidence substrate — CLOSED.
- PR #3: hostile acquisition / transport / normalization / provenance fixture authority — CLOSED.
- PR #4: executable fetch/source contracts — CLOSED.
- PR #5: live acquisition V0 with PyPI + CISA — CLOSED.

The roadmap snapshot following PR #5 is anchored to `main@012bfffecc761c0ff25df9deeb730bba63e5103f`.

## Current implementation direction

The next product phase is source diversity, not advanced ranking. FRONTIER needs live structurally different ATTENTION / DISCOVERY evidence before grouping and trend models can be evaluated honestly.

See `ROADMAP.md` for the bounded sequence.

## Implementation governance

`IMPLEMENT -> TEST -> ONE independent hostile review -> repair Critical/High -> ONE targeted re-review only if Critical/High fixes were required -> COMMIT/CLOSE -> MOVE FORWARD`

Medium/Low findings do not reopen a phase unless they undermine the phase objective, evidence, frozen authority, security/integrity or fail-closed semantics.
