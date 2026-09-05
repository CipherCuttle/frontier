from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

psycopg = pytest.importorskip("psycopg")

from frontier.adapters.postgres.readiness import (
    EXPECTED_DATABASE_REVISION,
    DatabaseReadinessError,
    verify_database_readiness,
)
from frontier.cli.main import doctor_database

DB_URL = os.getenv("FRONTIER_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="FRONTIER_TEST_DATABASE_URL not set")


def test_migrated_database_is_ready() -> None:
    assert DB_URL is not None
    with psycopg.connect(DB_URL) as connection:
        readiness = verify_database_readiness(connection)

    assert readiness.migration_revision == EXPECTED_DATABASE_REVISION
    assert readiness.database_name == "frontier"
    assert "observations" in readiness.required_relations
    assert "baseline_intelligence_snapshots" in readiness.required_relations


def test_stale_database_revision_fails_closed_without_persisting_test_mutation() -> None:
    assert DB_URL is not None
    with psycopg.connect(DB_URL) as connection:
        connection.execute("UPDATE alembic_version SET version_num = '0000_stale'")
        try:
            with pytest.raises(DatabaseReadinessError, match="migration revision mismatch"):
                verify_database_readiness(connection)
        finally:
            connection.rollback()

    with psycopg.connect(DB_URL) as connection:
        row = connection.execute("SELECT version_num FROM alembic_version").fetchone()
    assert row == (EXPECTED_DATABASE_REVISION,)


def test_doctor_reports_database_and_source_registry(capsys: pytest.CaptureFixture[str]) -> None:
    assert DB_URL is not None
    assert doctor_database(DB_URL, Path(".")) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["migration_revision"] == EXPECTED_DATABASE_REVISION
    assert payload["database_name"] == "frontier"
    assert payload["configured_sources"] == sorted(payload["configured_sources"])
    assert "arxiv.cs-ai" in payload["configured_sources"]
    assert "github.ml-repos" in payload["configured_sources"]
    assert str(payload["source_registry_version"]).startswith("sha256:")
