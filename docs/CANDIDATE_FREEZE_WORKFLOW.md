# FRONTIER Candidate Freeze Operator Workflow (WP13, G12)

This document is the operator runbook for the PEF_V0 candidate freeze. It is the ONLY authoritative description of the `frontier freeze` commands.

Doctrine (R8, WP2): a candidate freeze binds the PEF_V0 candidate identity (preregistration digest + embedded configuration digest, implementation commit/tree digest, dependency lock digest, source registry digest + per-entry digests). Any drift — missing, inconsistent, or later-changed components — is explicit and fail-closed; it is never silently accepted.

## The two clocks: `receipt_created_at` vs `durable_freeze_at`

These two timestamps are NEVER the same authority and must never be collapsed:

- `receipt_created_at` (`frozen_at` in the receipt canonical payload) is the **local wall clock** at which the receipt was built by `frontier freeze derive`. It is recorded inside the receipt content and contributes to the receipt digest, but it is NOT a durability fact.
- `durable_freeze_at` is stamped ONLY by the canonical PostgreSQL insert transaction (the `frontier_set_durable_freeze_at` BEFORE INSERT trigger, migration 0010): it equals `clock_timestamp()` of the committing transaction that inserted the receipt into `candidate_freeze_receipts`. `NULL` means NOT_DURABLE.

All confirmatory eligibility math uses `durable_freeze_at` ONLY: a run is confirmatory-eligible only with a FROZEN bound receipt, non-NULL `durable_freeze_at`, and strict `as_of > durable_freeze_at`, executed in the canonical DB context. A receipt that was never persisted to the canonical DB is never durable, no matter what any local clock says.

## Operator sequence

### 1. Derive (dry-run, always safe)

```bash
uv run frontier freeze derive --root .
```

Default behavior is dry-run: it collects the freeze inputs from the CURRENT repository state (`git rev-parse HEAD`/`HEAD^{tree}`, file digests of `uv.lock`, `sources/registry/registry_v0.json`, the registry entry files, and the preregistration document), builds the receipt, verifies it against the same inputs, and prints one JSON document containing:

- `receipt` — the full canonical receipt JSON;
- `receipt_id` — the deterministic content-derived receipt id;
- `receipt_created_at` — the wall clock used at build time;
- `expected_components` — the freshly collected identity components;
- `status` and `verify_status`.

Nothing is written anywhere. The receipt id is deterministic given the repository state and the build timestamp: re-deriving at the same `frozen_at` over identical state yields the identical `receipt_id`.

Exit codes: 0 (report produced — check `status`/`verify_status` in the payload; `freeze verify` is the drift gate), 2 (preregistration missing or receipt unloadable).

### 2. Verify

```bash
uv run frontier freeze verify --receipt-file freeze.json --root .
# or against a stored receipt:
uv run frontier freeze verify --receipt-id freezereceipt_<hex> --root . --database-url 'postgresql://...'
```

The receipt source is either a file containing the canonical receipt JSON (a file printed by `derive` with the `receipt` wrapper is accepted) or a stored receipt id resolved through the canonical DB. Every component is recomputed against current state and compared under WP5 drift-report semantics: a previously DRIFTED freeze stays DRIFTED even if live inputs now match.

Exit codes:

- `0` — OK: status `FROZEN`, no drift reasons;
- `1` — DRIFTED: the payload lists the exact drift reasons (e.g. "dependency lock digest drifted", "implementation commit unavailable at verification time");
- `2` — the receipt could not be loaded (missing file, invalid JSON, unknown stored id, missing database URL).

### 3. Persist (post-merge, human-authorized ONLY)

```bash
FRONTIER_FREEZE_PERSIST_AUTHORIZED=1 \
FRONTIER_DATABASE_URL='postgresql://...' \
uv run frontier freeze derive --persist --root .
```

**The real freeze is NOT authorized during this sprint.** The final, real candidate freeze happens only AFTER the GIGASPRINT branch merges into `main` AND a human operator explicitly authorizes it by setting `FRONTIER_FREEZE_PERSIST_AUTHORIZED=1` in the environment.

The safe default is absolute: without that exact override, `--persist` prints a `FREEZE_PERSIST_UNAUTHORIZED` refusal to stderr and exits 2 without touching the database. The guard must never be weakened, bypassed, or made implicit. `--persist` also refuses (exit 2) to persist a DRIFTED receipt.

When (and only when) authorized, the receipt is inserted through the existing append-only path (`PostgresCandidateFreezeRepository.record_receipt`), and the insert transaction's `BEFORE INSERT` trigger stamps `durable_freeze_at` from the canonical DB commit clock. The persisted receipt's `durable_freeze_at` is printed in the payload. The database is readiness-gated before the write, exactly like every other mutating command.

### 4. Durability

```bash
uv run frontier freeze durability --receipt-id freezereceipt_<hex> --database-url 'postgresql://...'
```

Reports `durability: DURABLE` (with the stamped `durable_freeze_at` value) or `durability: NOT_DURABLE` (with `durable_freeze_at: null`) for a stored receipt. Durability truth comes from the canonical DB commit — never from local clocks. A `NOT_DURABLE` freeze cannot gate confirmatory runs (WP2 gate b).

Exit codes: 0 (report — read `durability` in the payload), 2 (receipt not found / DB unavailable).

### 5. Confirmatory sequencing

A confirmatory run is eligible only when ALL of the following hold (enforced by `evaluate_confirmatory_gates` / the persisted-evaluation binding gates):

1. a freeze receipt is bound and resolvable to a FROZEN row in the canonical DB;
2. `durable_freeze_at` is NOT NULL;
3. the run `as_of` is strictly AFTER `durable_freeze_at`;
4. the run executes in the canonical DB context.

So the full authorized sequence is: derive (dry) → verify → **[post-merge, human-authorized]** persist → durability reports `DURABLE` → confirmatory runs with `as_of > durable_freeze_at`. Anything else stays DEV and is never confirmatory evidence.
