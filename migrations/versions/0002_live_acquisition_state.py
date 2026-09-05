"""Add trusted operational state for PR-02 live acquisition.

Revision ID: 0002_live_acquisition_state
Revises: 0001_evidence_substrate
"""

from alembic import op

revision = "0002_live_acquisition_state"
down_revision = "0001_evidence_substrate"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE source_fetch_state (
            source_id TEXT PRIMARY KEY REFERENCES sources(source_id) ON DELETE RESTRICT,
            etag TEXT NULL CHECK (etag IS NULL OR octet_length(etag) <= 4096),
            last_modified TEXT NULL CHECK (last_modified IS NULL OR octet_length(last_modified) <= 4096),
            last_body_digest TEXT NULL CHECK (
                last_body_digest IS NULL OR last_body_digest ~ '^sha256:[0-9a-f]{64}$'
            ),
            last_success_at TIMESTAMPTZ NULL,
            consecutive_failures INTEGER NOT NULL DEFAULT 0 CHECK (consecutive_failures >= 0),
            next_retry_at TIMESTAMPTZ NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
        );

        CREATE INDEX source_fetch_state_retry_idx
            ON source_fetch_state(next_retry_at)
            WHERE next_retry_at IS NOT NULL;
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS source_fetch_state;")
