from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import unquote, urlsplit, urlunsplit

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb

SOURCE_DATABASE = "frontier_recovery_source"
RESTORE_DATABASE = "frontier_recovery_restore"
POSTGRES_IMAGE = "postgres:18"
ALLOW_ENV = "FRONTIER_RECOVERY_DRILL_ALLOW"
DATABASE_URL_ENV = "FRONTIER_RECOVERY_DATABASE_URL"

SOURCE_ID = "ops.recovery-fixture"
SOURCE_ITEM_KEY = "frontier-backup-restore-probe-v0"
OBSERVATION_ID = "obs_" + hashlib.sha256(SOURCE_ITEM_KEY.encode()).hexdigest()
CONTRACT_DIGEST = "sha256:" + hashlib.sha256(b"frontier-recovery-contract-v0").hexdigest()
CONTENT_DIGEST = "sha256:" + hashlib.sha256(b"frontier-recovery-payload-v0").hexdigest()
FETCH_DIGEST = "sha256:" + hashlib.sha256(b"frontier-recovery-fetch-v0").hexdigest()
PAYLOAD = {
    "canonical_url": "https://example.invalid/frontier/recovery-probe",
    "excerpt": None,
    "language": "en",
    "source_metadata": {"fixture": "backup-restore-v0"},
    "title": "FRONTIER backup restore recovery probe",
}


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


def _seed_probe(database_url: str) -> str:
    with psycopg.connect(database_url) as connection:
        connection.execute(
            """
            INSERT INTO sources (
                source_id,
                contract_schema_version,
                display_name,
                acquisition_class,
                signal_roles,
                transport,
                enabled,
                contract_json,
                contract_digest
            ) VALUES (
                %s,
                'source-contract-v0',
                'Recovery fixture',
                'A_AUTHORITATIVE_STRUCTURED',
                ARRAY['PRIMARY_EMISSION'],
                'FIXTURE',
                FALSE,
                %s,
                %s
            )
            """,
            (
                SOURCE_ID,
                Jsonb({"fixture": "backup-restore-v0", "source_id": SOURCE_ID}),
                CONTRACT_DIGEST,
            ),
        )
        connection.execute(
            """
            INSERT INTO observations (
                observation_id,
                schema_version,
                canonicalization_version,
                source_id,
                source_item_key,
                kind,
                payload_json,
                source_published_at,
                effective_at,
                observed_at,
                retrieved_at,
                content_digest,
                fetch_digest
            ) VALUES (
                %s,
                'observation-v0',
                'canonical-json-v0',
                %s,
                %s,
                'DOCUMENT',
                %s,
                NULL,
                NULL,
                TIMESTAMPTZ '2026-09-05 20:00:00+00',
                TIMESTAMPTZ '2026-09-05 20:00:00+00',
                %s,
                %s
            )
            """,
            (
                OBSERVATION_ID,
                SOURCE_ID,
                SOURCE_ITEM_KEY,
                Jsonb(PAYLOAD),
                CONTENT_DIGEST,
                FETCH_DIGEST,
            ),
        )
        revision = connection.execute("SELECT version_num FROM alembic_version").fetchone()
        if revision is None or not isinstance(revision[0], str) or not revision[0]:
            raise RuntimeError("source database has no Alembic head")
        return revision[0]


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


def _verify_restore(database_url: str, expected_revision: str) -> None:
    with psycopg.connect(database_url) as connection:
        revision = connection.execute("SELECT version_num FROM alembic_version").fetchone()
        if revision != (expected_revision,):
            raise RuntimeError(
                f"restored Alembic revision mismatch: expected {expected_revision!r}, got {revision!r}"
            )

        restored = connection.execute(
            """
            SELECT source_id, source_item_key, payload_json, content_digest, fetch_digest
            FROM observations
            WHERE observation_id = %s
            """,
            (OBSERVATION_ID,),
        ).fetchone()
        expected = (SOURCE_ID, SOURCE_ITEM_KEY, PAYLOAD, CONTENT_DIGEST, FETCH_DIGEST)
        if restored != expected:
            raise RuntimeError("restored canonical recovery probe does not match source database")

        try:
            with connection.transaction():
                connection.execute(
                    "UPDATE observations SET source_item_key = 'mutated' WHERE observation_id = %s",
                    (OBSERVATION_ID,),
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
        revision = _seed_probe(source_url)
        with tempfile.TemporaryDirectory(prefix="frontier-recovery-") as directory:
            dump_path = Path(directory) / "frontier.dump"
            backup_bytes = _dump_database(admin_url, dump_path)
            _reset_database(admin_url, RESTORE_DATABASE)
            _restore_database(admin_url, dump_path)
            _verify_restore(restore_url, revision)
        print(
            json.dumps(
                {
                    "backup_bytes": backup_bytes,
                    "migration_revision": revision,
                    "observation_id": OBSERVATION_ID,
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
