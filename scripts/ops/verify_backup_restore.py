from __future__ import annotations

import json
import os
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import unquote, urlsplit, urlunsplit
from uuid import UUID

import psycopg
from psycopg import sql

from frontier.adapters.postgres import PostgresEvidenceStore
from frontier.domain.collection import CollectionReason, CollectionRun, CollectionRunStatus
from frontier.domain.digests import sha256_digest
from frontier.domain.observation import DocumentPayload, ObservationCandidate, ObservationKind
from frontier.domain.source import AcquisitionClass, SignalRole, SourceContract, SourceTransport

SOURCE_DATABASE = "frontier_recovery_source"
RESTORE_DATABASE = "frontier_recovery_restore"
POSTGRES_IMAGE = "postgres:18"
ALLOW_ENV = "FRONTIER_RECOVERY_DRILL_ALLOW"
DATABASE_URL_ENV = "FRONTIER_RECOVERY_DATABASE_URL"

RECOVERY_TIME = datetime(2026, 9, 5, 20, 0, tzinfo=UTC)
RECOVERY_RUN_ID = UUID("00000000-0000-4000-8000-000000000001")
RECOVERY_SOURCE = SourceContract(
    source_id="ops.recovery-fixture",
    display_name="Recovery fixture",
    acquisition_class=AcquisitionClass.A_AUTHORITATIVE_STRUCTURED,
    signal_roles=(SignalRole.PRIMARY_EMISSION,),
    transport=SourceTransport.FIXTURE,
    enabled=False,
)
RECOVERY_CANDIDATE = ObservationCandidate(
    source_id=RECOVERY_SOURCE.source_id,
    source_item_key="frontier-backup-restore-probe-v1",
    kind=ObservationKind.DOCUMENT,
    payload=DocumentPayload(
        canonical_url="https://example.invalid/frontier/recovery-probe",
        title="FRONTIER backup restore recovery probe",
        excerpt=None,
        language="en",
        source_metadata={"fixture": "backup-restore-v1"},
    ),
    retrieved_at=RECOVERY_TIME,
    fetch_digest=sha256_digest(b"frontier-recovery-fetch-v1"),
)


def _database_url(base_url: str, database: str) -> str:
    parsed = urlsplit(base_url)
    if parsed.scheme not in {"postgres", "postgresql", "postgresql+psycopg"}:
        raise RuntimeError("recovery drill requires a PostgreSQL URL")
    if parsed.hostname is None or parsed.username is None:
        raise RuntimeError("recovery drill database URL must include host and user")
    return urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            f"/{database}",
            parsed.query,
            parsed.fragment,
        )
    )


def _sqlalchemy_url(database_url: str) -> str:
    parsed = urlsplit(database_url)
    scheme = "postgresql+psycopg" if parsed.scheme in {"postgres", "postgresql"} else parsed.scheme
    return urlunsplit((scheme, parsed.netloc, parsed.path, parsed.query, parsed.fragment))


def _connection_parts(database_url: str) -> tuple[str, str, str, int]:
    parsed = urlsplit(database_url)
    if parsed.hostname is None or parsed.username is None:
        raise RuntimeError("recovery drill database URL must include host and user")
    return (
        parsed.hostname,
        unquote(parsed.username),
        unquote(parsed.password or ""),
        parsed.port or 5432,
    )


def _reset_database(admin_url: str, database: str) -> None:
    with psycopg.connect(admin_url, autocommit=True) as connection:
        connection.execute(
            sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(database))
        )
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))


def _drop_database(admin_url: str, database: str) -> None:
    with psycopg.connect(admin_url, autocommit=True) as connection:
        connection.execute(
            sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(database))
        )


def _migrate(database_url: str) -> None:
    environment = os.environ.copy()
    environment["FRONTIER_DATABASE_URL"] = _sqlalchemy_url(database_url)
    subprocess.run(["alembic", "upgrade", "head"], check=True, env=environment)


def _seed_probe(database_url: str) -> tuple[str, str]:
    with psycopg.connect(database_url) as connection:
        store = PostgresEvidenceStore(connection)
        store.upsert_source(RECOVERY_SOURCE)
        run = CollectionRun(
            run_id=RECOVERY_RUN_ID,
            source_id=RECOVERY_SOURCE.source_id,
            reason=CollectionReason.SCHEDULED,
            started_at=RECOVERY_TIME,
        )
        store.start_collection_run(run)
        observation, inserted = store.append_observation(RECOVERY_CANDIDATE, run.run_id)
        if not inserted or observation.observation_id != RECOVERY_CANDIDATE.observation_id:
            raise RuntimeError("canonical recovery probe was not inserted through evidence store")
        store.complete_collection_run(
            run.run_id,
            status=CollectionRunStatus.SUCCESS,
            records_received=1,
            records_accepted=1,
            records_rejected=0,
            duplicates=0,
            failure_code=None,
        )
        revision = connection.execute("SELECT version_num FROM alembic_version").fetchone()
        if revision is None or not isinstance(revision[0], str) or not revision[0]:
            raise RuntimeError("source database has no Alembic head")
        return revision[0], observation.observation_id


def _postgres_client_command(
    admin_url: str,
    executable: str,
    database: str,
    *arguments: str,
    interactive: bool = False,
) -> tuple[list[str], dict[str, str]]:
    host, user, password, port = _connection_parts(admin_url)
    environment = os.environ.copy()
    environment["PGPASSWORD"] = password
    command = ["docker", "run"]
    if interactive:
        command.append("-i")
    command.extend(
        [
            "--rm",
            "--network",
            "host",
            "-e",
            "PGPASSWORD",
            POSTGRES_IMAGE,
            executable,
            "-h",
            host,
            "-p",
            str(port),
            "-U",
            user,
            "-d",
            database,
            *arguments,
        ]
    )
    return command, environment


def _dump_database(admin_url: str, dump_path: Path) -> int:
    command, environment = _postgres_client_command(
        admin_url,
        "pg_dump",
        SOURCE_DATABASE,
        "--format=custom",
        "--no-owner",
        "--no-privileges",
    )
    with dump_path.open("wb") as output:
        subprocess.run(command, check=True, env=environment, stdout=output)
    size = dump_path.stat().st_size
    if size <= 0:
        raise RuntimeError("backup artifact is empty")
    return size


def _restore_database(admin_url: str, dump_path: Path) -> None:
    command, environment = _postgres_client_command(
        admin_url,
        "pg_restore",
        RESTORE_DATABASE,
        "--exit-on-error",
        "--no-owner",
        "--no-privileges",
        interactive=True,
    )
    with dump_path.open("rb") as backup:
        subprocess.run(command, check=True, env=environment, stdin=backup)


def _verify_restore(database_url: str, expected_revision: str, observation_id: str) -> None:
    with psycopg.connect(database_url) as connection:
        revision = connection.execute("SELECT version_num FROM alembic_version").fetchone()
        if revision != (expected_revision,):
            message = (
                f"restored Alembic revision mismatch: expected {expected_revision!r}, "
                f"got {revision!r}"
            )
            raise RuntimeError(message)

        restored_source = connection.execute(
            """
            SELECT contract_schema_version, contract_json, contract_digest
            FROM sources
            WHERE source_id = %s
            """,
            (RECOVERY_SOURCE.source_id,),
        ).fetchone()
        expected_source = (
            "source-contract-v1",
            RECOVERY_SOURCE.to_canonical(),
            str(RECOVERY_SOURCE.contract_digest),
        )
        if restored_source != expected_source:
            raise RuntimeError("restored source contract does not match current domain contract")

        restored = connection.execute(
            """
            SELECT schema_version, canonicalization_version, source_id, source_item_key,
                   kind, payload_json, source_published_at, effective_at,
                   content_digest, fetch_digest
            FROM observations
            WHERE observation_id = %s
            """,
            (observation_id,),
        ).fetchone()
        expected = (
            RECOVERY_CANDIDATE.schema_version,
            RECOVERY_CANDIDATE.canonicalization_version,
            RECOVERY_CANDIDATE.source_id,
            RECOVERY_CANDIDATE.source_item_key,
            RECOVERY_CANDIDATE.kind.value,
            RECOVERY_CANDIDATE.payload.to_canonical(),
            RECOVERY_CANDIDATE.source_published_at,
            RECOVERY_CANDIDATE.effective_at,
            str(RECOVERY_CANDIDATE.content_digest),
            str(RECOVERY_CANDIDATE.fetch_digest),
        )
        if restored != expected:
            raise RuntimeError("restored canonical recovery probe does not match domain identity")

        run_status = connection.execute(
            "SELECT status FROM collection_runs WHERE run_id = %s", (RECOVERY_RUN_ID,)
        ).fetchone()
        if run_status != (CollectionRunStatus.SUCCESS.value,):
            raise RuntimeError("restored recovery collection run is not complete")

        try:
            with connection.transaction():
                connection.execute(
                    "UPDATE observations SET source_item_key = 'mutated' WHERE observation_id = %s",
                    (observation_id,),
                )
        except psycopg.Error as exc:
            if exc.sqlstate != "55000":
                raise RuntimeError(
                    "restored append-only trigger failed with wrong SQLSTATE"
                ) from exc
        else:
            raise RuntimeError("restored canonical observation unexpectedly accepted mutation")


def main() -> int:
    if os.environ.get(ALLOW_ENV) != "1":
        raise RuntimeError(f"set {ALLOW_ENV}=1 to run the destructive scratch-database drill")
    admin_url = os.environ.get(DATABASE_URL_ENV)
    if admin_url is None or not admin_url.strip():
        raise RuntimeError(f"{DATABASE_URL_ENV} is required")

    source_url = _database_url(admin_url, SOURCE_DATABASE)
    restore_url = _database_url(admin_url, RESTORE_DATABASE)
    _drop_database(admin_url, RESTORE_DATABASE)
    _drop_database(admin_url, SOURCE_DATABASE)
    try:
        _reset_database(admin_url, SOURCE_DATABASE)
        _migrate(source_url)
        revision, observation_id = _seed_probe(source_url)
        with tempfile.TemporaryDirectory(prefix="frontier-recovery-") as directory:
            dump_path = Path(directory) / "frontier.dump"
            backup_bytes = _dump_database(admin_url, dump_path)
            _reset_database(admin_url, RESTORE_DATABASE)
            _restore_database(admin_url, dump_path)
            _verify_restore(restore_url, revision, observation_id)
        print(
            json.dumps(
                {
                    "backup_bytes": backup_bytes,
                    "migration_revision": revision,
                    "observation_id": observation_id,
                    "restore_verified": True,
                },
                sort_keys=True,
            )
        )
    finally:
        _drop_database(admin_url, RESTORE_DATABASE)
        _drop_database(admin_url, SOURCE_DATABASE)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
