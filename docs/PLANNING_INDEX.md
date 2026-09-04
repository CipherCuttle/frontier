# FRONTIER Planning Authority Index

Status: CANDIDATE_AUTHORITY — PROMOTES_ON_PR00_MERGE

This directory records the planning authority established before product implementation.

## Promotion semantics
While PR-00 is open, every file in this PR is candidate authority. Merge of PR-00 promotes:
- `CONSTITUTION.md` -> `FROZEN_V0` authority;
- ADRs marked `ACCEPTED_CANDIDATE` -> `ACCEPTED_V0` authority;
- P01-P08, `SOURCE_POLICY.md`, `DONOR_LEDGER.md`, and `DEBT_REGISTER.md` -> supporting canonical planning/governance authority for V0.

The literal pre-merge status strings do not leave the merged authority provisional; this promotion rule is itself canonical on merge.

## Precedence
1. `CONSTITUTION.md`.
2. Accepted ADRs under `docs/adr/` for the specific decision they govern.
3. `P08_DATA_CONTRACT.md` for PR-01 evidence-substrate implementation details.
4. P01-P07 planning/evaluation documents.
5. `SOURCE_POLICY.md` for source-governance details.
6. `DONOR_LEDGER.md` and `DEBT_REGISTER.md` for provenance/debt tracking.

Rules:
- Specific lower-level authority may refine but may not contradict a higher-level authority.
- File order, numbering, or modification time never silently supersedes another authority.
- A later authority may supersede an earlier one only when it explicitly names the superseded decision and scope.
- Unresolved contradiction is fail-closed: implementation stops and governance is repaired before code chooses an interpretation.

## Implementation governance
IMPLEMENT -> TEST -> ONE independent hostile review -> repair Critical/High -> ONE targeted re-review only if Critical/High fixes were required -> COMMIT/CLOSE -> MOVE FORWARD.

Medium/Low findings do not reopen a phase unless they undermine the phase objective, evidence, frozen authority, security/integrity, or fail-closed semantics.

No production runtime implementation is authorized by PR-00 itself. PR-01 becomes authorized only after PR-00 is merged.
