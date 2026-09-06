"""Add append-only EXPERIMENTAL experimental-analysis artifacts (slice F).

Revision ID: 0009_experimental_analysis
Revises: 0008_feature_vectors
"""

from alembic import op

revision = "0009_experimental_analysis"
down_revision = "0008_feature_vectors"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        r"""
        CREATE TABLE experimental_analysis_artifacts (
            analysis_id TEXT PRIMARY KEY
                CHECK (analysis_id ~ '^expanalysis_[0-9a-f]{64}$'),
            artifact_kind TEXT NOT NULL CHECK (
                artifact_kind IN (
                    'GROUPING_HYPOTHESES',
                    'ENTITY_PROVENANCE',
                    'CORROBORATION',
                    'PROPAGATION_GRAPH',
                    'INDICATORS',
                    'TRAJECTORY'
                )
            ),
            status TEXT NOT NULL CHECK (status IN ('HYPOTHESIS','DESCRIPTOR','INDICATORS','PROJECTION')),
            authority_state TEXT NOT NULL CHECK (authority_state IN ('EXPERIMENTAL_SHADOW')),
            as_of TIMESTAMPTZ NOT NULL,
            generated_at TIMESTAMPTZ NOT NULL,
            control_snapshot_id TEXT NULL
                CHECK (control_snapshot_id IS NULL OR control_snapshot_id ~ '^snapshot_[0-9a-f]{64}$'),
            control_receipt_id TEXT NULL
                CHECK (control_receipt_id IS NULL OR control_receipt_id ~ '^receipt_[0-9a-f]{64}$'),
            source_registry_version TEXT NULL
                CHECK (source_registry_version IS NULL OR source_registry_version ~ '^sha256:[0-9a-f]{64}$'),
            episode_universe_digest TEXT NULL
                CHECK (episode_universe_digest IS NULL OR episode_universe_digest ~ '^sha256:[0-9a-f]{64}$'),
            schema_version TEXT NOT NULL,
            algorithm_version TEXT NOT NULL,
            configuration_digest TEXT NOT NULL CHECK (configuration_digest ~ '^sha256:[0-9a-f]{64}$'),
            input_digest TEXT NULL CHECK (input_digest IS NULL OR input_digest ~ '^sha256:[0-9a-f]{64}$'),
            output_digest TEXT NOT NULL CHECK (output_digest ~ '^sha256:[0-9a-f]{64}$'),
            analysis_json JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
            CONSTRAINT experimental_analysis_snapshot_binding CHECK (
                (
                    artifact_kind = 'TRAJECTORY'
                    AND control_snapshot_id IS NULL
                    AND control_receipt_id IS NULL
                )
                OR (
                    artifact_kind <> 'TRAJECTORY'
                    AND control_snapshot_id IS NOT NULL
                    AND control_receipt_id IS NOT NULL
                    AND source_registry_version IS NOT NULL
                    AND episode_universe_digest IS NOT NULL
                )
            )
        );

        CREATE TRIGGER frontier_append_only_experimental_analysis
        BEFORE UPDATE OR DELETE ON experimental_analysis_artifacts
        FOR EACH ROW EXECUTE FUNCTION frontier_reject_canonical_mutation();
        CREATE TRIGGER frontier_append_only_experimental_analysis_truncate
        BEFORE TRUNCATE ON experimental_analysis_artifacts
        FOR EACH STATEMENT EXECUTE FUNCTION frontier_reject_canonical_mutation();

        CREATE INDEX experimental_analysis_kind_as_of_idx
            ON experimental_analysis_artifacts(artifact_kind, as_of DESC);
        CREATE INDEX experimental_analysis_snapshot_idx
            ON experimental_analysis_artifacts(control_snapshot_id, artifact_kind);
        CREATE INDEX experimental_analysis_as_of_idx
            ON experimental_analysis_artifacts(as_of DESC);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS experimental_analysis_artifacts;")
