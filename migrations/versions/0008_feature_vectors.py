"""Add append-only EXPERIMENTAL advanced feature vectors (slice E).

Revision ID: 0008_feature_vectors
Revises: 0007_evaluation_receipts
"""

from alembic import op

revision = "0008_feature_vectors"
down_revision = "0007_evaluation_receipts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        r"""
        CREATE TABLE feature_vectors (
            feature_vector_id TEXT PRIMARY KEY
                CHECK (feature_vector_id ~ '^featurevector_[0-9a-f]{64}$'),
            batch_id TEXT NOT NULL CHECK (batch_id ~ '^featurebatch_[0-9a-f]{64}$'),
            batch_digest TEXT NOT NULL CHECK (batch_digest ~ '^sha256:[0-9a-f]{64}$'),
            episode_id TEXT NOT NULL,
            control_snapshot_id TEXT NOT NULL CHECK (control_snapshot_id ~ '^snapshot_[0-9a-f]{64}$'),
            control_receipt_id TEXT NOT NULL CHECK (control_receipt_id ~ '^receipt_[0-9a-f]{64}$'),
            episode_universe_digest TEXT NOT NULL CHECK (episode_universe_digest ~ '^sha256:[0-9a-f]{64}$'),
            as_of TIMESTAMPTZ NOT NULL,
            generated_at TIMESTAMPTZ NOT NULL,
            feature_schema_version TEXT NOT NULL,
            algorithm_version TEXT NOT NULL,
            configuration_digest TEXT NOT NULL CHECK (configuration_digest ~ '^sha256:[0-9a-f]{64}$'),
            authority_state TEXT NOT NULL CHECK (authority_state IN ('EXPERIMENTAL_SHADOW')),
            status TEXT NOT NULL CHECK (status IN ('RAN','FAILED')),
            vector_digest TEXT NOT NULL CHECK (vector_digest ~ '^sha256:[0-9a-f]{64}$'),
            vector_json JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
        );

        CREATE TRIGGER frontier_append_only_feature_vectors
        BEFORE UPDATE OR DELETE ON feature_vectors
        FOR EACH ROW EXECUTE FUNCTION frontier_reject_canonical_mutation();
        CREATE TRIGGER frontier_append_only_feature_vectors_truncate
        BEFORE TRUNCATE ON feature_vectors
        FOR EACH STATEMENT EXECUTE FUNCTION frontier_reject_canonical_mutation();

        CREATE INDEX feature_vectors_batch_idx
            ON feature_vectors(batch_id);
        CREATE INDEX feature_vectors_episode_idx
            ON feature_vectors(episode_id, as_of DESC);
        CREATE INDEX feature_vectors_as_of_idx
            ON feature_vectors(as_of DESC);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS feature_vectors;")
