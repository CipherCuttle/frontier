"""Add append-only candidate freeze receipts (candidate identity binding).

Revision ID: 0006_candidate_freeze_receipts
Revises: 0005_shadow_experiment_runs
"""

from alembic import op

revision = "0006_candidate_freeze_receipts"
down_revision = "0005_shadow_experiment_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        r"""
        CREATE TABLE candidate_freeze_receipts (
            receipt_id TEXT PRIMARY KEY CHECK (receipt_id ~ '^freezereceipt_[0-9a-f]{64}$'),
            schema_version TEXT NOT NULL,
            candidate_id TEXT NOT NULL,
            experiment_id TEXT NOT NULL,
            algorithm_version TEXT NOT NULL,
            configuration_digest TEXT NOT NULL CHECK (configuration_digest ~ '^sha256:[0-9a-f]{64}$'),
            status TEXT NOT NULL CHECK (status IN ('FROZEN','DRIFTED')),
            preregistration_path TEXT NOT NULL,
            preregistration_digest TEXT NOT NULL CHECK (preregistration_digest ~ '^sha256:[0-9a-f]{64}$'),
            preregistration_config_digest TEXT NULL CHECK (preregistration_config_digest ~ '^sha256:[0-9a-f]{64}$'),
            implementation_commit TEXT NULL CHECK (implementation_commit ~ '^[0-9a-f]{40,64}$'),
            implementation_tree_digest TEXT NULL CHECK (implementation_tree_digest ~ '^[0-9a-f]{40,64}$'),
            dependency_lock_digest TEXT NULL CHECK (dependency_lock_digest ~ '^sha256:[0-9a-f]{64}$'),
            source_registry_digest TEXT NULL CHECK (source_registry_digest ~ '^sha256:[0-9a-f]{64}$'),
            registry_entry_digests JSONB NULL,
            drift_reasons JSONB NOT NULL,
            receipt_digest TEXT NOT NULL CHECK (receipt_digest ~ '^sha256:[0-9a-f]{64}$'),
            frozen_at TIMESTAMPTZ NOT NULL,
            verified_at TIMESTAMPTZ NULL,
            original_receipt_digest TEXT NULL CHECK (original_receipt_digest ~ '^sha256:[0-9a-f]{64}$'),
            receipt_json JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
            CHECK (
                (status = 'FROZEN' AND drift_reasons = '[]'::jsonb)
                OR (status = 'DRIFTED' AND jsonb_array_length(drift_reasons) > 0)
            )
        );

        CREATE TRIGGER frontier_append_only_candidate_freeze_receipts
        BEFORE UPDATE OR DELETE ON candidate_freeze_receipts
        FOR EACH ROW EXECUTE FUNCTION frontier_reject_canonical_mutation();
        CREATE TRIGGER frontier_append_only_candidate_freeze_receipts_truncate
        BEFORE TRUNCATE ON candidate_freeze_receipts
        FOR EACH STATEMENT EXECUTE FUNCTION frontier_reject_canonical_mutation();

        CREATE INDEX candidate_freeze_receipts_candidate_idx
            ON candidate_freeze_receipts(candidate_id, frozen_at DESC);
        CREATE INDEX candidate_freeze_receipts_status_idx
            ON candidate_freeze_receipts(status, frozen_at DESC);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS candidate_freeze_receipts;")
