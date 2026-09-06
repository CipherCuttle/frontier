"""Add append-only preregistered evaluation receipts (slice D).

Revision ID: 0007_evaluation_receipts
Revises: 0006_candidate_freeze_receipts
"""

from alembic import op

revision = "0007_evaluation_receipts"
down_revision = "0006_candidate_freeze_receipts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        r"""
        CREATE TABLE evaluation_receipts (
            evaluation_id TEXT PRIMARY KEY CHECK (evaluation_id ~ '^evaluation_[0-9a-f]{64}$'),
            schema_version TEXT NOT NULL,
            experiment_id TEXT NOT NULL,
            candidate_id TEXT NOT NULL,
            evaluation_algorithm_version TEXT NOT NULL,
            candidate_configuration_digest TEXT NOT NULL
                CHECK (candidate_configuration_digest ~ '^sha256:[0-9a-f]{64}$'),
            evaluation_configuration_digest TEXT NOT NULL
                CHECK (evaluation_configuration_digest ~ '^sha256:[0-9a-f]{64}$'),
            authority_state TEXT NOT NULL CHECK (authority_state IN ('EXPERIMENTAL_EVALUATION')),
            status TEXT NOT NULL
                CHECK (status IN ('COMPLETE','INSUFFICIENT_SAMPLE','FAILED','INVALID_DRIFT')),
            as_of TIMESTAMPTZ NOT NULL,
            generated_at TIMESTAMPTZ NOT NULL,
            candidate_freeze_receipt_id TEXT NOT NULL
                CHECK (candidate_freeze_receipt_id ~ '^freezereceipt_[0-9a-f]{64}$'),
            freeze_receipt_digest TEXT NOT NULL CHECK (freeze_receipt_digest ~ '^sha256:[0-9a-f]{64}$'),
            freeze_status TEXT NOT NULL CHECK (freeze_status IN ('FROZEN','DRIFTED')),
            preregistration_digest TEXT NOT NULL CHECK (preregistration_digest ~ '^sha256:[0-9a-f]{64}$'),
            receipt_digest TEXT NOT NULL CHECK (receipt_digest ~ '^sha256:[0-9a-f]{64}$'),
            shadow_run_ids JSONB NOT NULL,
            receipt_json JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
        );

        CREATE TRIGGER frontier_append_only_evaluation_receipts
        BEFORE UPDATE OR DELETE ON evaluation_receipts
        FOR EACH ROW EXECUTE FUNCTION frontier_reject_canonical_mutation();
        CREATE TRIGGER frontier_append_only_evaluation_receipts_truncate
        BEFORE TRUNCATE ON evaluation_receipts
        FOR EACH STATEMENT EXECUTE FUNCTION frontier_reject_canonical_mutation();

        CREATE INDEX evaluation_receipts_status_idx
            ON evaluation_receipts(status, as_of DESC);
        CREATE INDEX evaluation_receipts_candidate_idx
            ON evaluation_receipts(candidate_id, as_of DESC);
        CREATE INDEX evaluation_receipts_freeze_idx
            ON evaluation_receipts(candidate_freeze_receipt_id, as_of DESC);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS evaluation_receipts;")
