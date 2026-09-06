"""Add append-only opportunity membership history (WP3: prospective engine).

Revision ID: 0012_opportunity_memberships
Revises: 0011_experiment_attempt_detail
"""

from alembic import op

revision = "0012_opportunity_memberships"
down_revision = "0011_experiment_attempt_detail"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        r"""
        -- Opportunity membership history (WP3): append-only evidence of whether
        -- an opportunity anchor appeared in the eligible universe of a paired
        -- run's CANDIDATE and/or CONTROL arm at one boundary as_of. Membership
        -- is evidence, never a mutable flag: rows are content-derived
        -- (membership_id) and never updated or deleted. present rows carry the
        -- anchor's current grouping episode id and, when the arm ranked that
        -- episode, its 1-based global rank position; present = FALSE rows are
        -- the explicit negative evidence of absence at that boundary.
        CREATE TABLE opportunity_memberships (
            membership_id TEXT PRIMARY KEY
                CHECK (membership_id ~ '^opmember_[0-9a-f]{64}$'),
            anchor_id TEXT NOT NULL REFERENCES opportunity_anchors(anchor_id),
            schema_version TEXT NOT NULL,
            experiment_id TEXT NOT NULL CHECK (length(experiment_id) > 0),
            as_of TIMESTAMPTZ NOT NULL,
            arm TEXT NOT NULL CHECK (arm IN ('CANDIDATE', 'CONTROL')),
            present BOOLEAN NOT NULL,
            episode_id TEXT NULL CHECK (episode_id IS NULL OR length(episode_id) > 0),
            rank_position INTEGER NULL CHECK (rank_position IS NULL OR rank_position >= 1),
            membership_digest TEXT NOT NULL CHECK (membership_digest ~ '^sha256:[0-9a-f]{64}$'),
            membership_json JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
            CHECK (
                (present = FALSE AND episode_id IS NULL AND rank_position IS NULL)
                OR (present = TRUE AND episode_id IS NOT NULL)
            )
        );

        -- One membership fact per (anchor, experiment, boundary, arm): a
        -- digest-different re-derivation at the same identity is a conflict,
        -- never a rewrite.
        CREATE UNIQUE INDEX opportunity_memberships_boundary_arm_key
            ON opportunity_memberships(anchor_id, experiment_id, as_of, arm);
        CREATE INDEX opportunity_memberships_anchor_arm_idx
            ON opportunity_memberships(anchor_id, arm, as_of, membership_id);

        CREATE TRIGGER frontier_append_only_opportunity_memberships
        BEFORE UPDATE OR DELETE ON opportunity_memberships
        FOR EACH ROW EXECUTE FUNCTION frontier_reject_canonical_mutation();
        CREATE TRIGGER frontier_append_only_opportunity_memberships_truncate
        BEFORE TRUNCATE ON opportunity_memberships
        FOR EACH STATEMENT EXECUTE FUNCTION frontier_reject_canonical_mutation();
        """
    )


def downgrade() -> None:
    op.execute(
        r"""
        DROP TRIGGER IF EXISTS frontier_append_only_opportunity_memberships_truncate ON opportunity_memberships;
        DROP TRIGGER IF EXISTS frontier_append_only_opportunity_memberships ON opportunity_memberships;
        DROP TABLE IF EXISTS opportunity_memberships;
        """
    )
