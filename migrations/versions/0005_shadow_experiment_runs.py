"""Add append-only paired shadow experiment runs (experimental shadow outputs).

Revision ID: 0005_shadow_experiment_runs
Revises: 0004_pef_artifacts
"""

from alembic import op

revision = "0005_shadow_experiment_runs"
down_revision = "0004_pef_artifacts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        r"""
        CREATE TABLE shadow_experiment_runs (
            run_id TEXT PRIMARY KEY CHECK (run_id ~ '^shadowrun_[0-9a-f]{64}$'),
            experiment_id TEXT NOT NULL,
            candidate_id TEXT NOT NULL,
            schema_version TEXT NOT NULL,
            algorithm_version TEXT NOT NULL,
            configuration_digest TEXT NOT NULL CHECK (configuration_digest ~ '^sha256:[0-9a-f]{64}$'),
            authority_state TEXT NOT NULL CHECK (authority_state IN ('EXPERIMENTAL_SHADOW')),
            status TEXT NOT NULL CHECK (status IN ('RAN','FAILED')),
            as_of TIMESTAMPTZ NOT NULL,
            control_snapshot_id TEXT NOT NULL CHECK (control_snapshot_id ~ '^snapshot_[0-9a-f]{64}$'),
            control_receipt_id TEXT NOT NULL CHECK (control_receipt_id ~ '^receipt_[0-9a-f]{64}$'),
            candidate_artifact_id TEXT NOT NULL CHECK (candidate_artifact_id ~ '^artifact_[0-9a-f]{64}$'),
            candidate_output_digest TEXT NOT NULL CHECK (candidate_output_digest ~ '^sha256:[0-9a-f]{64}$'),
            coverage_state TEXT NOT NULL CHECK (coverage_state IN ('OK','DEGRADED','UNKNOWN','FAILED')),
            episode_universe_digest TEXT NOT NULL CHECK (episode_universe_digest ~ '^sha256:[0-9a-f]{64}$'),
            run_digest TEXT NOT NULL CHECK (run_digest ~ '^sha256:[0-9a-f]{64}$'),
            failure_reason TEXT NULL,
            run_json JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
            CHECK (
                (status = 'RAN' AND failure_reason IS NULL)
                OR (status = 'FAILED' AND failure_reason IS NOT NULL)
            )
        );

        CREATE TRIGGER frontier_append_only_shadow_experiment_runs
        BEFORE UPDATE OR DELETE ON shadow_experiment_runs
        FOR EACH ROW EXECUTE FUNCTION frontier_reject_canonical_mutation();
        CREATE TRIGGER frontier_append_only_shadow_experiment_runs_truncate
        BEFORE TRUNCATE ON shadow_experiment_runs
        FOR EACH STATEMENT EXECUTE FUNCTION frontier_reject_canonical_mutation();

        CREATE INDEX shadow_experiment_runs_asof_idx
            ON shadow_experiment_runs(as_of DESC, run_id);
        CREATE INDEX shadow_experiment_runs_candidate_idx
            ON shadow_experiment_runs(candidate_id, as_of DESC);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS shadow_experiment_runs;")
