# FRONTIER Operations Runbook

This runbook defines the current platform-neutral startup, readiness, recovery-drill, and capacity-measurement contract for FRONTIER.

It does **not** choose a deployment platform. Kubernetes, systemd, Docker Compose, managed PostgreSQL, and other packaging/orchestration decisions remain outside this contract until there is evidence that one is required.

## Required runtime inputs

FRONTIER requires:

- Python 3.14 or newer;
- the frozen project environment (`uv sync --all-extras --frozen`);
- PostgreSQL at the schema revision expected by the application;
- `FRONTIER_DATABASE_URL`, unless `--database-url` is passed explicitly;
- a config root containing the fetch policy and source registry used by the worker.

The repository root is the default config root.

## Startup sequence

Do not start collection against an unknown or stale database schema.

1. Apply migrations:

   ```bash
   FRONTIER_DATABASE_URL='postgresql+psycopg://...' uv run alembic upgrade head
   ```

2. Verify database and configuration readiness:

   ```bash
   FRONTIER_DATABASE_URL='postgresql://...' uv run frontier doctor
   ```

   `frontier doctor` is read-only. It fails closed unless:

   - the database is reachable;
   - the exact expected Alembic revision is present;
   - required canonical/operational relations exist;
   - the fetch policy loads;
   - the source registry loads.

   The command prints JSON containing the database name, PostgreSQL version, migration revision, required relations, configured source IDs, and source-registry digest.

3. Run one bounded worker cycle before continuous operation:

   ```bash
   FRONTIER_DATABASE_URL='postgresql://...' uv run frontier worker --once
   ```

   The cycle prints structured JSON with acquisition results, schedule state, cadence SLO state, retry state, lateness, and timing.

4. Start the continuous worker only after the bounded cycle behaves as expected:

   ```bash
   FRONTIER_DATABASE_URL='postgresql://...' uv run frontier worker
   ```

The `ingest-fixture`, `acquire`, and `worker` database-mutating commands all execute the same database readiness gate before mutation.

## Schema mismatch behavior

The application does not auto-migrate on startup.

If the deployed application and database migration revision do not match, database-mutating CLI paths fail before collection begins. The operator must apply the intended migration explicitly and then run `frontier doctor` again.

This is deliberate: startup must not silently mutate schema authority or continue against an unknown database shape.

## Worker lifecycle

The worker currently uses one synchronous psycopg connection and performs acquisition sequentially.

Do not add concurrent database writes merely to increase apparent throughput; concurrency requires an explicit connection/transaction design and evidence that the existing sequential worker is the bottleneck.

A normal interactive stop is `SIGINT` / `Ctrl-C`; the CLI handles `KeyboardInterrupt` and exits cleanly after control returns from the active acquisition operation.

## Recovery drill

The repository contains an isolated PostgreSQL backup/restore recovery drill:

```bash
FRONTIER_RECOVERY_DRILL_ALLOW=1 \
FRONTIER_RECOVERY_DATABASE_URL='postgresql://...' \
uv run python scripts/ops/verify_backup_restore.py
```

The drill is intentionally destructive **only** to these scratch databases:

- `frontier_recovery_source`
- `frontier_recovery_restore`

It:

1. creates a fresh source scratch database;
2. migrates it to Alembic head;
3. writes a deterministic canonical probe observation;
4. creates a PostgreSQL 18 custom-format dump;
5. restores the dump into a second scratch database;
6. verifies the restored Alembic revision;
7. verifies the exact canonical probe row;
8. verifies the restored append-only trigger still rejects canonical mutation;
9. drops both scratch databases.

The drill never dumps or restores the normal `frontier` database.

This is recovery verification, not a production backup-retention policy. Backup destination, retention, encryption, off-site replication, and production restore authorization remain deployment-specific decisions and are not claimed by this repository yet.

## Capacity measurement

The bounded capacity receipt runs against the migrated scratch database `frontier_capacity_probe`:

```bash
FRONTIER_CAPACITY_MEASURE_ALLOW=1 \
FRONTIER_CAPACITY_DATABASE_URL='postgresql://...' \
FRONTIER_CAPACITY_OBSERVATIONS=1000 \
uv run python scripts/ops/measure_capacity.py
```

The measurement uses the real `PostgresEvidenceStore` path and records:

- observation count;
- total insert elapsed time;
- insert observations/second;
- p50, p95, and maximum per-observation insert latency;
- full observation-ID readback time and row count;
- scratch database size;
- PostgreSQL version.

The receipt intentionally emits `threshold_verdict: null`. A single CI or workstation measurement is not a production SLO and must not be converted into one without representative workload evidence.

## CI operational gates

Pull requests currently exercise four independent gates:

- `verify` — formatting, linting, strict Pyright, architecture/preflight checks, generated-contract checks, and tests;
- `preflight-contracts` — source/fetch contract authority;
- `ops-recovery` — isolated backup/restore recovery drill;
- `ops-capacity` — bounded application-store capacity measurement.

A green recovery or capacity workflow does not override a failing `verify` or preflight workflow. Operational changes require the relevant workflows to pass on the same exact commit before they are treated as a verified checkpoint.

## Current non-claims

The current operations contract does not claim:

- high availability;
- automatic failover;
- horizontal worker scaling;
- zero-downtime schema migration;
- a production backup-retention policy;
- a production throughput SLO;
- a specific container/service/orchestration platform;
- that source availability or freshness is guaranteed by the worker.

Those require separate evidence and explicit authority rather than being inferred from a green CI run.
