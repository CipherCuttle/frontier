"""Add append-only Git publication authority for candidate freezes.

Revision ID: 0013_freeze_publication_authority
Revises: 0012_opportunity_memberships
"""

from alembic import op

revision = "0013_freeze_publication"
down_revision = "0012_opportunity_memberships"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(r"""
    CREATE TABLE candidate_freeze_publications (
        receipt_id TEXT PRIMARY KEY REFERENCES candidate_freeze_receipts(receipt_id),
        schema_version TEXT NOT NULL CHECK (schema_version = 'candidate-freeze-publication-v0'),
        freeze_receipt_digest TEXT NOT NULL CHECK (freeze_receipt_digest ~ '^sha256:[0-9a-f]{64}$'),
        implementation_commit TEXT NOT NULL CHECK (implementation_commit ~ '^[0-9a-f]{40,64}$'),
        implementation_tree_digest TEXT NOT NULL CHECK (implementation_tree_digest ~ '^[0-9a-f]{40,64}$'),
        publication_commit TEXT NOT NULL CHECK (publication_commit ~ '^[0-9a-f]{40,64}$'),
        publication_committer_at TIMESTAMPTZ NOT NULL,
        publication_digest TEXT NOT NULL CHECK (publication_digest ~ '^sha256:[0-9a-f]{64}$'),
        publication_json JSONB NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
    );
    CREATE FUNCTION frontier_validate_freeze_publication() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE r candidate_freeze_receipts%ROWTYPE;
    BEGIN
      SELECT * INTO r FROM candidate_freeze_receipts WHERE receipt_id = NEW.receipt_id;
      IF NOT FOUND THEN RAISE EXCEPTION 'freeze publication receipt does not exist'; END IF;
      IF r.status <> 'FROZEN' THEN RAISE EXCEPTION 'freeze publication requires FROZEN receipt'; END IF;
      IF r.durable_freeze_at IS NULL THEN RAISE EXCEPTION 'freeze publication requires canonical DB durability'; END IF;
      IF NEW.freeze_receipt_digest <> r.receipt_digest OR NEW.implementation_commit <> r.implementation_commit OR NEW.implementation_tree_digest <> r.implementation_tree_digest THEN
        RAISE EXCEPTION 'freeze publication identity does not match receipt';
      END IF;
      IF NEW.publication_committer_at < r.durable_freeze_at OR NEW.publication_committer_at < r.frozen_at THEN
        RAISE EXCEPTION 'freeze publication timestamp precedes durable receipt';
      END IF;
      RETURN NEW;
    END; $$;
    CREATE TRIGGER frontier_validate_freeze_publication_insert BEFORE INSERT ON candidate_freeze_publications
      FOR EACH ROW EXECUTE FUNCTION frontier_validate_freeze_publication();
    CREATE TRIGGER frontier_append_only_freeze_publications BEFORE UPDATE OR DELETE ON candidate_freeze_publications
      FOR EACH ROW EXECUTE FUNCTION frontier_reject_canonical_mutation();
    CREATE TRIGGER frontier_append_only_freeze_publications_truncate BEFORE TRUNCATE ON candidate_freeze_publications
      FOR EACH STATEMENT EXECUTE FUNCTION frontier_reject_canonical_mutation();
    """)


def downgrade() -> None:
    op.execute(r"""
    DROP TRIGGER IF EXISTS frontier_append_only_freeze_publications_truncate ON candidate_freeze_publications;
    DROP TRIGGER IF EXISTS frontier_append_only_freeze_publications ON candidate_freeze_publications;
    DROP TRIGGER IF EXISTS frontier_validate_freeze_publication_insert ON candidate_freeze_publications;
    DROP FUNCTION IF EXISTS frontier_validate_freeze_publication();
    DROP TABLE IF EXISTS candidate_freeze_publications;
    """)
