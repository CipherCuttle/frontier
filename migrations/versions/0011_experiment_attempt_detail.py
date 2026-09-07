"""Add attempt outcome detail column (WP2: prospective experiment orchestrator).

Revision ID: 0011_experiment_attempt_detail
Revises: 0010_experiment_outcome_state
"""

from alembic import op

revision = "0011_experiment_attempt_detail"
down_revision = "0010_experiment_outcome_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        r"""
        -- Attempt outcome detail (mutable operational column): carries the
        -- explicit human-readable reason for EXPIRED/FAILED/SKIPPED terminal
        -- states and the run_id binding for DONE attempts. The attempt
        -- lifecycle state itself remains the only new operational state model.
        ALTER TABLE experiment_run_attempts
            ADD COLUMN detail TEXT NULL;

        COMMENT ON COLUMN experiment_run_attempts.detail IS
            'outcome detail recorded at terminal transitions: lease-expiry, '
            'failure or skip reason, and the persisted run_id for DONE '
            'attempts; NULL while the attempt is active';
        """
    )


def downgrade() -> None:
    op.execute(
        r"""
        ALTER TABLE experiment_run_attempts DROP COLUMN IF EXISTS detail;
        """
    )
