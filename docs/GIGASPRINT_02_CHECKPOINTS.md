# GIGASPRINT_02 checkpoints

Build evidence only. This document grants no freeze, confirmatory, scientific, governance, or promotion authority.

## G2-04 / D012 — shared freeze-persistence authorization

Implementation commit: `320a54a618bab2581a84dd3d293c7e1d5cab59cf`.

State: `IMPLEMENTED_FOCUSED_VERIFIED / FULL_PR_CI_PENDING`.

Change:

- `PostgresCandidateFreezeRepository` is read-capable by default but rejects `record_receipt()` unless constructed with an explicit `persistence_authorized=True` capability.
- the CLI retains the explicit `FRONTIER_FREEZE_PERSIST_AUTHORIZED=1` human/operator gate and only supplies the lower-level capability after that gate succeeds;
- fixture integration writes opt in explicitly;
- a new integration regression proves the default repository path raises `PermissionError` before writing a candidate-freeze row.

Focused remote verification executed before commit:

- `uv lock --check` — PASS
- `uv sync --all-extras --frozen` — PASS
- Ruff format/check on the changed Python files — PASS
- Pyright on the changed source files — PASS
- `tests/unit/test_freeze_cli.py` — PASS

The normal PR workflows on the bot-authored implementation commit were not treated as evidence because GitHub returned `action_required` without creating jobs. This user-authored checkpoint intentionally triggers normal exact-head PR CI. D012 is not declared closed until that CI and the PostgreSQL integration path are green.
