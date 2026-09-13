# FRONTIER bounded-change skill

Operational guidance only. Canonical authority lives in `docs/` and phase-specific artifacts.

## Trigger

Use this procedure for any implementation, repair, refactor, workflow, documentation, or remote-agent task in FRONTIER.

## 1. Rehydrate

Read, in order:

1. `AGENTS.md`
2. `docs/PLANNING_INDEX.md`
3. `docs/ROADMAP.md`
4. the authority/preregistration/ADR for the requested surface
5. current Git/PR state for the exact base SHA

Return a compact task envelope before editing:

```text
BASE_SHA=<sha>
OBJECTIVE=<single bounded objective>
AUTHORITY=<files/receipts/preregistration>
ALLOWED_PATHS=<paths>
FORBIDDEN_PATHS=<paths>
VERIFY=<commands/checks>
REVIEW_BUDGET=<bounded policy>
MERGE_AUTHORITY=<true|false>
```

If authority is contradictory, stop fail-closed rather than choosing a convenient interpretation.

## 2. Plan the smallest diff

The plan must answer:

- What single defect/capability is being changed?
- Which files must change?
- Which tempting adjacent files must not change?
- What evidence would falsify the implementation?
- What rollback is available?

Prefer additive tooling and isolated experiments over changes to frozen/runtime authority.

## 3. Implement

Rules:

- Preserve unrelated WIP.
- Do not rewrite receipts, preregistrations, or historical evidence.
- Do not weaken tests, time bounds, health semantics, or fail-closed checks to obtain a pass.
- Do not backfill missed prospective experiment boundaries unless a specific authority grants it.
- Do not silently promote experimental/generated information into canonical truth/ranking.
- Keep dependency additions earned and explicit.

## 4. Verify

Start with the narrowest check that can falsify the change, then run the governing repository gate.

Default ordinary Python gate:

```bash
uv lock --check
uv sync --all-extras --frozen
uv run python scripts/verify.py
```

Add phase-specific PostgreSQL/E2E/ops/replay checks when required.

Report exact commands and exact pass/fail state. A skipped, unavailable, quota-blocked, or non-materialized review is not a passed review.

## 5. Hostile review

Use the repository bounded-completion policy:

- one independent hostile review;
- repair Critical/High only unless a lower finding invalidates the phase objective/evidence/frozen invariant;
- one targeted re-review only if Critical/High fixes were needed;
- no recursive review loops.

The reviewer should attack the stated objective and invariants, not invent a new product scope.

## 6. Verdict

Return:

```text
PLAN
CHANGESET
VERIFY
VERDICT
```

`VERDICT` must state one of:

- `PASS / READY_FOR_MERGE_GATE`
- `BLOCKED_BY_REVIEW`
- `BLOCKED_BY_CI`
- `BLOCKED_BY_AUTHORITY`
- `BLOCKED_BY_EXTERNAL_INPUT`
- `FAILED_OBJECTIVE`

Never claim merge completion unless the merge is actually observed.

## Remote-agent safety

For issue/comment-triggered agents, the safest default is:

1. repository read access only during reasoning;
2. isolated workspace/sandbox;
3. patch output or a new branch/PR only;
4. separately scoped write step;
5. no direct `main` write;
6. no secrets except the minimum provider/repo credentials;
7. normal CI and review gates still apply.

The remote agent is an implementation worker, not a new authority layer.