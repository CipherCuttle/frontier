"""Enforce experiment-scoped shadow-run boundary identity.

Revision ID: 0014_shadow_run_identity
Revises: 0013_freeze_publication
"""

from alembic import op

revision = "0014_shadow_run_identity"
down_revision = "0013_freeze_publication"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        r"""
        -- Fail closed if historical append-only evidence already violates the
        -- identity we are about to enforce. Never delete or rewrite evidence
        -- to make this migration fit.
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM shadow_experiment_runs
                GROUP BY experiment_id, as_of, run_class
                HAVING count(*) > 1
            ) THEN
                RAISE EXCEPTION
                    'cannot enforce shadow-run identity: duplicate (experiment_id, as_of, run_class) evidence exists';
            END IF;
        END;
        $$;

        CREATE UNIQUE INDEX shadow_experiment_runs_experiment_boundary_class_uidx
            ON shadow_experiment_runs(experiment_id, as_of, run_class);
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS shadow_experiment_runs_experiment_boundary_class_uidx;")
