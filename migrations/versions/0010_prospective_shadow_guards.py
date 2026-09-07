"""Add prospective shadow window binding and atomic boundary uniqueness.

Revision ID: 0010_prospective_shadow_guards
Revises: 0009_experimental_analysis
"""

from alembic import op

revision = "0010_prospective_shadow_guards"
down_revision = "0009_experimental_analysis"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        r"""
        CREATE TABLE confirmatory_window_bindings (
            candidate_freeze_receipt_id TEXT PRIMARY KEY
                CHECK (candidate_freeze_receipt_id ~ '^freezereceipt_[0-9a-f]{64}$'),
            durable_freeze_commit TEXT NOT NULL
                CHECK (durable_freeze_commit ~ '^[0-9a-f]{40,64}$'),
            durable_freeze_at TIMESTAMPTZ NOT NULL,
            window_start TIMESTAMPTZ NOT NULL,
            window_end TIMESTAMPTZ NOT NULL,
            binding_json JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
            CHECK (window_start > durable_freeze_at),
            CHECK (window_end > window_start)
        );

        CREATE TRIGGER frontier_append_only_confirmatory_window_bindings
        BEFORE UPDATE OR DELETE ON confirmatory_window_bindings
        FOR EACH ROW EXECUTE FUNCTION frontier_reject_canonical_mutation();
        CREATE TRIGGER frontier_append_only_confirmatory_window_bindings_truncate
        BEFORE TRUNCATE ON confirmatory_window_bindings
        FOR EACH STATEMENT EXECUTE FUNCTION frontier_reject_canonical_mutation();

        CREATE UNIQUE INDEX shadow_experiment_runs_freeze_boundary_unique
            ON shadow_experiment_runs (
                (run_json ->> 'candidate_freeze_receipt_id'),
                as_of
            )
            WHERE run_json ->> 'candidate_freeze_receipt_id' IS NOT NULL;
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS shadow_experiment_runs_freeze_boundary_unique;")
    op.execute("DROP TABLE IF EXISTS confirmatory_window_bindings;")
