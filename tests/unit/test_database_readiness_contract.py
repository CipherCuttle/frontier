from __future__ import annotations

from alembic.config import Config
from alembic.script import ScriptDirectory

from frontier.adapters.postgres.readiness import EXPECTED_DATABASE_REVISION


def test_expected_database_revision_matches_alembic_head() -> None:
    script = ScriptDirectory.from_config(Config("alembic.ini"))
    assert script.get_current_head() == EXPECTED_DATABASE_REVISION
