"""Add append-only PEF_V0 ranking artifacts (experimental shadow outputs).

Revision ID: 0004_pef_artifacts
Revises: 0003_baseline_snapshots
"""

from alembic import op

revision = "0004_pef_artifacts"
down_revision = "0003_baseline_snapshots"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        r"""
        CREATE TABLE pef_ranking_artifacts (
            artifact_id TEXT PRIMARY KEY CHECK (artifact_id ~ '^artifact_[0-9a-f]{64}$'),
            projection_version TEXT NOT NULL,
            schema_version TEXT NOT NULL,
            algorithm_version TEXT NOT NULL,
            ranking_policy_version TEXT NOT NULL,
            configuration_digest TEXT NOT NULL CHECK (configuration_digest ~ '^sha256:[0-9a-f]{64}$'),
            authority_state TEXT NOT NULL CHECK (authority_state IN ('EXPERIMENTAL_SHADOW')),
            status TEXT NOT NULL CHECK (status IN ('RAN','FAILED')),
            as_of TIMESTAMPTZ NOT NULL,
            control_snapshot_id TEXT NOT NULL CHECK (control_snapshot_id ~ '^snapshot_[0-9a-f]{64}$'),
            control_receipt_id TEXT NOT NULL CHECK (control_receipt_id ~ '^receipt_[0-9a-f]{64}$'),
            receipt_id TEXT NOT NULL UNIQUE REFERENCES projection_receipts(receipt_id) ON DELETE RESTRICT,
            output_digest TEXT NOT NULL CHECK (output_digest ~ '^sha256:[0-9a-f]{64}$'),
            failure_reason TEXT NULL,
            artifact_json JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
        );

        CREATE TRIGGER frontier_append_only_pef_artifacts
        BEFORE UPDATE OR DELETE ON pef_ranking_artifacts
        FOR EACH ROW EXECUTE FUNCTION frontier_reject_canonical_mutation();
        CREATE TRIGGER frontier_append_only_pef_artifacts_truncate
        BEFORE TRUNCATE ON pef_ranking_artifacts
        FOR EACH STATEMENT EXECUTE FUNCTION frontier_reject_canonical_mutation();

        CREATE INDEX pef_ranking_artifacts_asof_idx
            ON pef_ranking_artifacts(as_of DESC, artifact_id);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS pef_ranking_artifacts;")
