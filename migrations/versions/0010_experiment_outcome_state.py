"""Add experiment outcome state foundations (WP1: opportunity/outcome, run attempts).

Revision ID: 0010_experiment_outcome_state
Revises: 0009_experimental_analysis
"""

from alembic import op

revision = "0010_experiment_outcome_state"
down_revision = "0009_experimental_analysis"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        r"""
        -- Orchestrator decision (a): explicit durable_freeze_at on candidate
        -- freeze receipts. durable_freeze_at is set at insert into the canonical
        -- authority and equals clock_timestamp() of the committing transaction;
        -- it is distinct from the receipt creation time (frozen_at) and the two
        -- are never collapsed. NULL means the freeze is not durable: a
        -- non-durable freeze can NEVER gate a confirmatory run. Legacy rows
        -- have no durability truth and stay NULL.
        ALTER TABLE candidate_freeze_receipts
            ADD COLUMN durable_freeze_at TIMESTAMPTZ NULL;

        COMMENT ON COLUMN candidate_freeze_receipts.durable_freeze_at IS
            'canonical-DB durability timestamp: clock_timestamp() of the '
            'insert transaction; NULL means NOT durable (cannot gate '
            'confirmatory runs); never collapse with frozen_at';

        -- durable_freeze_at is stamped inside the same insert transaction into
        -- the canonical authority, so it must be set by a BEFORE INSERT trigger
        -- rather than by a post-hoc UPDATE (the table is append-only and its
        -- canonical-mutation trigger must remain intact).
        CREATE FUNCTION frontier_set_durable_freeze_at()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF NEW.durable_freeze_at IS NULL THEN
                NEW.durable_freeze_at := clock_timestamp();
            END IF;
            RETURN NEW;
        END;
        $$;

        CREATE TRIGGER frontier_set_durable_freeze_at_insert
        BEFORE INSERT ON candidate_freeze_receipts
        FOR EACH ROW EXECUTE FUNCTION frontier_set_durable_freeze_at();

        -- Orchestrator decision (b): explicit run class on shadow experiment
        -- runs. Safe-by-default: existing and unstamped rows are DEV.
        ALTER TABLE shadow_experiment_runs
            ADD COLUMN run_class TEXT NOT NULL DEFAULT 'DEV'
            CHECK (run_class IN ('DEV', 'CONFIRMATORY'));

        -- Opportunity anchors: content-derived identity from the preregistration
        -- opportunity rules (experiments/advanced_intelligence/pef_v0/
        -- preregistration.json, "opportunity"): a prospectively eligible
        -- canonical PRIMARY_EMISSION observation from a frozen V0 anchor source
        -- whose observed_at is inside the ranking window. Stable anchor identity
        -- is the observation_id; resolution_at = anchor.observed_at + 86400s;
        -- episode membership evolves and never regroups observations.
        CREATE TABLE opportunity_anchors (
            anchor_id TEXT PRIMARY KEY
                CHECK (anchor_id ~ '^opanchor_[0-9a-f]{64}$'),
            schema_version TEXT NOT NULL,
            observation_id TEXT NOT NULL REFERENCES observations(observation_id),
            source_id TEXT NOT NULL REFERENCES sources(source_id),
            as_of TIMESTAMPTZ NOT NULL,
            observed_at TIMESTAMPTZ NOT NULL,
            resolution_at TIMESTAMPTZ NOT NULL,
            domain_stratum TEXT NOT NULL CHECK (domain_stratum IN (
                'SOFTWARE_PACKAGES', 'AI_MODELS', 'SECURITY_VULNERABILITIES',
                'UNQUALIFIED_MIXED', 'UNQUALIFIED'
            )),
            episode_id_at_resolution TEXT NULL,
            control_snapshot_id TEXT NULL
                CHECK (control_snapshot_id IS NULL OR control_snapshot_id ~ '^snapshot_[0-9a-f]{64}$'),
            control_receipt_id TEXT NULL
                CHECK (control_receipt_id IS NULL OR control_receipt_id ~ '^receipt_[0-9a-f]{64}$'),
            anchor_digest TEXT NOT NULL CHECK (anchor_digest ~ '^sha256:[0-9a-f]{64}$'),
            anchor_json JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
            CHECK (resolution_at > observed_at),
            CHECK (observed_at <= as_of)
        );

        -- Outcome resolutions: append-only adjudication of a retained anchor.
        -- The row is written once the outcome is adjudicated (RESOLVED /
        -- EXCLUDED / UNKNOWN); an anchor without a resolution row is PENDING by
        -- projection. UNKNOWN stays UNKNOWN. Fail-closed blinding discipline: a
        -- RESOLVED label requires an explicit BLINDED adjudication.
        CREATE TABLE outcome_resolutions (
            anchor_id TEXT PRIMARY KEY REFERENCES opportunity_anchors(anchor_id),
            schema_version TEXT NOT NULL,
            resolution_state TEXT NOT NULL CHECK (resolution_state IN (
                'PENDING', 'RESOLVED', 'EXCLUDED', 'UNKNOWN'
            )),
            label TEXT NULL CHECK (label IN (
                'POSITIVE', 'NEGATIVE', 'UNRESOLVED_COVERAGE'
            )),
            blinding_state TEXT NOT NULL CHECK (blinding_state IN ('BLINDED', 'OPEN')),
            decided_at TIMESTAMPTZ NULL,
            evidence_digest TEXT NULL CHECK (evidence_digest IS NULL OR evidence_digest ~ '^sha256:[0-9a-f]{64}$'),
            lane_health_digest TEXT NULL CHECK (lane_health_digest IS NULL OR lane_health_digest ~ '^sha256:[0-9a-f]{64}$'),
            resolution_digest TEXT NOT NULL CHECK (resolution_digest ~ '^sha256:[0-9a-f]{64}$'),
            resolution_json JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
            CHECK (
                (
                    resolution_state = 'PENDING'
                    AND label IS NULL
                    AND decided_at IS NULL
                )
                OR (
                    resolution_state = 'RESOLVED'
                    AND label IN ('POSITIVE', 'NEGATIVE')
                    AND decided_at IS NOT NULL
                    AND blinding_state = 'BLINDED'
                    AND evidence_digest IS NOT NULL
                )
                OR (
                    resolution_state = 'UNKNOWN'
                    AND label = 'UNRESOLVED_COVERAGE'
                    AND decided_at IS NOT NULL
                    AND evidence_digest IS NOT NULL
                )
                OR (
                    resolution_state = 'EXCLUDED'
                    AND label IS NULL
                    AND decided_at IS NOT NULL
                )
            )
        );

        -- Append-only opportunity transition log: the projection is folded from
        -- this log; there is no silent deletion, correction, or rewrite of
        -- opportunity state.
        CREATE TABLE opportunity_transitions (
            transition_id TEXT PRIMARY KEY
                CHECK (transition_id ~ '^optrans_[0-9a-f]{64}$'),
            anchor_id TEXT NOT NULL REFERENCES opportunity_anchors(anchor_id),
            from_state TEXT NULL CHECK (from_state IS NULL OR from_state IN (
                'PENDING', 'RESOLVED', 'EXCLUDED', 'UNKNOWN'
            )),
            to_state TEXT NOT NULL CHECK (to_state IN (
                'PENDING', 'RESOLVED', 'EXCLUDED', 'UNKNOWN'
            )),
            reason TEXT NOT NULL CHECK (length(reason) > 0),
            occurred_at TIMESTAMPTZ NOT NULL,
            event_digest TEXT NOT NULL CHECK (event_digest ~ '^sha256:[0-9a-f]{64}$'),
            created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
            CHECK (
                (from_state IS NULL AND to_state = 'PENDING')
                OR (from_state IS NOT NULL AND to_state <> 'PENDING')
            )
        );

        CREATE TRIGGER frontier_append_only_opportunity_anchors
        BEFORE UPDATE OR DELETE ON opportunity_anchors
        FOR EACH ROW EXECUTE FUNCTION frontier_reject_canonical_mutation();
        CREATE TRIGGER frontier_append_only_opportunity_anchors_truncate
        BEFORE TRUNCATE ON opportunity_anchors
        FOR EACH STATEMENT EXECUTE FUNCTION frontier_reject_canonical_mutation();

        CREATE TRIGGER frontier_append_only_outcome_resolutions
        BEFORE UPDATE OR DELETE ON outcome_resolutions
        FOR EACH ROW EXECUTE FUNCTION frontier_reject_canonical_mutation();
        CREATE TRIGGER frontier_append_only_outcome_resolutions_truncate
        BEFORE TRUNCATE ON outcome_resolutions
        FOR EACH STATEMENT EXECUTE FUNCTION frontier_reject_canonical_mutation();

        CREATE TRIGGER frontier_append_only_opportunity_transitions
        BEFORE UPDATE OR DELETE ON opportunity_transitions
        FOR EACH ROW EXECUTE FUNCTION frontier_reject_canonical_mutation();
        CREATE TRIGGER frontier_append_only_opportunity_transitions_truncate
        BEFORE TRUNCATE ON opportunity_transitions
        FOR EACH STATEMENT EXECUTE FUNCTION frontier_reject_canonical_mutation();

        -- Experiment run attempts: mutable operational lease table for boundary
        -- execution. Design: a boundary (experiment_id, as_of) may be retried
        -- after EXPIRED, so uniqueness binds (experiment_id, as_of, attempt_no)
        -- and the attempt lifecycle state is mutable; there is exactly one
        -- active (non-terminal) attempt per attempt_no.
        CREATE TABLE experiment_run_attempts (
            attempt_id TEXT PRIMARY KEY
                CHECK (attempt_id ~ '^opattempt_[0-9a-f]{64}$'),
            experiment_id TEXT NOT NULL,
            as_of TIMESTAMPTZ NOT NULL,
            attempt_no INTEGER NOT NULL CHECK (attempt_no >= 1),
            status TEXT NOT NULL CHECK (status IN (
                'PENDING', 'RUNNING', 'DONE', 'FAILED', 'EXPIRED', 'SKIPPED'
            )),
            attempt_digest TEXT NOT NULL CHECK (attempt_digest ~ '^sha256:[0-9a-f]{64}$'),
            lease_owner TEXT NULL,
            lease_expires_at TIMESTAMPTZ NULL,
            heartbeat_at TIMESTAMPTZ NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
            UNIQUE (experiment_id, as_of, attempt_no),
            CHECK (status <> 'RUNNING' OR (lease_owner IS NOT NULL AND lease_expires_at IS NOT NULL)),
            CHECK (status = 'RUNNING' OR lease_owner IS NULL)
        );

        -- Worker heartbeats: mutable operational liveness table (no append-only
        -- trigger; heartbeats are operationally rewritten, never authority).
        CREATE TABLE worker_heartbeats (
            worker_id TEXT PRIMARY KEY CHECK (length(worker_id) BETWEEN 1 AND 128),
            role TEXT NOT NULL CHECK (length(role) > 0),
            beat_at TIMESTAMPTZ NOT NULL,
            metrics JSONB NOT NULL
        );

        CREATE INDEX opportunity_anchors_domain_resolution_idx
            ON opportunity_anchors(domain_stratum, resolution_at);
        CREATE INDEX opportunity_anchors_observation_idx
            ON opportunity_anchors(observation_id);
        CREATE INDEX opportunity_transitions_anchor_idx
            ON opportunity_transitions(anchor_id, occurred_at, transition_id);
        CREATE INDEX experiment_run_attempts_boundary_idx
            ON experiment_run_attempts(experiment_id, as_of, attempt_no DESC);
        """
    )


def downgrade() -> None:
    op.execute(
        r"""
        DROP TABLE IF EXISTS worker_heartbeats;
        DROP TABLE IF EXISTS experiment_run_attempts;
        DROP TRIGGER IF EXISTS frontier_append_only_opportunity_transitions_truncate ON opportunity_transitions;
        DROP TRIGGER IF EXISTS frontier_append_only_opportunity_transitions ON opportunity_transitions;
        DROP TRIGGER IF EXISTS frontier_append_only_outcome_resolutions_truncate ON outcome_resolutions;
        DROP TRIGGER IF EXISTS frontier_append_only_outcome_resolutions ON outcome_resolutions;
        DROP TRIGGER IF EXISTS frontier_append_only_opportunity_anchors_truncate ON opportunity_anchors;
        DROP TRIGGER IF EXISTS frontier_append_only_opportunity_anchors ON opportunity_anchors;
        DROP TABLE IF EXISTS opportunity_transitions;
        DROP TABLE IF EXISTS outcome_resolutions;
        DROP TABLE IF EXISTS opportunity_anchors;
        DROP TRIGGER IF EXISTS frontier_set_durable_freeze_at_insert ON candidate_freeze_receipts;
        DROP FUNCTION IF EXISTS frontier_set_durable_freeze_at();
        ALTER TABLE shadow_experiment_runs DROP COLUMN IF EXISTS run_class;
        ALTER TABLE candidate_freeze_receipts DROP COLUMN IF EXISTS durable_freeze_at;
        """
    )
