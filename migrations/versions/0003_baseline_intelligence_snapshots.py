"""Add immutable retained baseline intelligence snapshots.

Revision ID: 0003_baseline_snapshots
Revises: 0002_live_acquisition_state
"""

from alembic import op

revision = "0003_baseline_snapshots"
down_revision = "0002_live_acquisition_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        r"""
        CREATE TABLE baseline_intelligence_snapshots (
            snapshot_id TEXT PRIMARY KEY CHECK (snapshot_id ~ '^snapshot_[0-9a-f]{64}$'),
            projection_version TEXT NOT NULL,
            schema_version TEXT NOT NULL,
            algorithm_version TEXT NOT NULL,
            ranking_policy_version TEXT NOT NULL,
            as_of TIMESTAMPTZ NOT NULL,
            output_digest TEXT NOT NULL CHECK (output_digest ~ '^sha256:[0-9a-f]{64}$'),
            receipt_id TEXT NOT NULL UNIQUE REFERENCES projection_receipts(receipt_id) ON DELETE RESTRICT,
            snapshot_json JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
        );

        CREATE TRIGGER frontier_append_only_baseline_snapshots
        BEFORE UPDATE OR DELETE ON baseline_intelligence_snapshots
        FOR EACH ROW EXECUTE FUNCTION frontier_reject_canonical_mutation();
        CREATE TRIGGER frontier_append_only_baseline_snapshots_truncate
        BEFORE TRUNCATE ON baseline_intelligence_snapshots
        FOR EACH STATEMENT EXECUTE FUNCTION frontier_reject_canonical_mutation();

        CREATE INDEX baseline_intelligence_snapshots_asof_idx
            ON baseline_intelligence_snapshots(as_of DESC, snapshot_id);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS baseline_intelligence_snapshots;")
