"""Create FRONTIER PR-01 evidence substrate.

Revision ID: 0001_evidence_substrate
Revises: None
"""

from alembic import op

revision = "0001_evidence_substrate"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        r"""
        CREATE TABLE sources (
            source_id TEXT PRIMARY KEY CHECK (source_id ~ '^[a-z0-9][a-z0-9._-]{1,63}$'),
            contract_schema_version TEXT NOT NULL,
            display_name TEXT NOT NULL CHECK (length(display_name) > 0),
            acquisition_class TEXT NOT NULL CHECK (acquisition_class IN (
                'A_AUTHORITATIVE_STRUCTURED','B_OPEN_AGGREGATION',
                'C_PERMITTED_EXTRACTION','D_FRAGILE_UI_EXTRACTION'
            )),
            signal_roles TEXT[] NOT NULL,
            transport TEXT NOT NULL CHECK (transport IN (
                'RSS','ATOM','JSON_HTTP','REST','BULK_FILE','HTML','BROWSER','FIXTURE'
            )),
            enabled BOOLEAN NOT NULL,
            contract_json JSONB NOT NULL,
            contract_digest TEXT NOT NULL CHECK (contract_digest ~ '^sha256:[0-9a-f]{64}$'),
            created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
        );

        CREATE TABLE collection_runs (
            run_id UUID PRIMARY KEY,
            source_id TEXT NOT NULL REFERENCES sources(source_id),
            reason TEXT NOT NULL CHECK (reason IN ('SCHEDULED','DISCOVERY','ACTIVE_ENRICHMENT','BACKFILL')),
            trigger_id TEXT NULL,
            recovered_after_gap BOOLEAN NOT NULL DEFAULT FALSE,
            started_at TIMESTAMPTZ NOT NULL,
            completed_at TIMESTAMPTZ NULL,
            status TEXT NOT NULL CHECK (status IN ('RUNNING','SUCCESS','PARTIAL','FAILED')),
            records_received BIGINT NOT NULL DEFAULT 0 CHECK (records_received >= 0),
            records_accepted BIGINT NOT NULL DEFAULT 0 CHECK (records_accepted >= 0),
            records_rejected BIGINT NOT NULL DEFAULT 0 CHECK (records_rejected >= 0),
            duplicates BIGINT NOT NULL DEFAULT 0 CHECK (duplicates >= 0),
            failure_code TEXT NULL,
            CHECK (reason <> 'ACTIVE_ENRICHMENT' OR trigger_id IS NOT NULL)
        );

        CREATE TABLE observations (
            observation_id TEXT PRIMARY KEY CHECK (observation_id ~ '^obs_[0-9a-f]{64}$'),
            schema_version TEXT NOT NULL,
            canonicalization_version TEXT NOT NULL,
            source_id TEXT NOT NULL REFERENCES sources(source_id),
            source_item_key TEXT NOT NULL CHECK (octet_length(source_item_key) BETWEEN 1 AND 4096),
            kind TEXT NOT NULL CHECK (kind IN ('DOCUMENT','ARTIFACT','METRIC')),
            payload_json JSONB NOT NULL,
            source_published_at TIMESTAMPTZ NULL,
            effective_at TIMESTAMPTZ NULL,
            observed_at TIMESTAMPTZ NOT NULL,
            retrieved_at TIMESTAMPTZ NOT NULL,
            content_digest TEXT NOT NULL CHECK (content_digest ~ '^sha256:[0-9a-f]{64}$'),
            fetch_digest TEXT NOT NULL CHECK (fetch_digest ~ '^sha256:[0-9a-f]{64}$'),
            created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
        );

        CREATE TABLE collection_run_observations (
            run_id UUID NOT NULL REFERENCES collection_runs(run_id) ON DELETE RESTRICT,
            observation_id TEXT NOT NULL REFERENCES observations(observation_id) ON DELETE RESTRICT,
            occurrence_status TEXT NOT NULL CHECK (occurrence_status IN ('INSERTED','DUPLICATE')),
            recorded_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
            PRIMARY KEY (run_id, observation_id)
        );

        CREATE TABLE observation_relations (
            relation_id TEXT PRIMARY KEY CHECK (relation_id ~ '^rel_[0-9a-f]{64}$'),
            relation_type TEXT NOT NULL CHECK (relation_type IN ('CORRECTS','RETRACTS','REFERENCES')),
            from_observation_id TEXT NOT NULL REFERENCES observations(observation_id) ON DELETE RESTRICT,
            target_observation_id TEXT NULL REFERENCES observations(observation_id) ON DELETE RESTRICT,
            target_external_ref TEXT NULL,
            authority TEXT NOT NULL CHECK (authority IN ('EXPLICIT','INFERRED')),
            algorithm_version TEXT NULL,
            confidence TEXT NULL,
            evidence_json JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
            CHECK ((target_observation_id IS NULL) <> (target_external_ref IS NULL)),
            CHECK (authority <> 'INFERRED' OR algorithm_version IS NOT NULL)
        );

        CREATE TABLE source_health_observations (
            health_observation_id TEXT PRIMARY KEY CHECK (health_observation_id ~ '^health_[0-9a-f]{64}$'),
            source_id TEXT NOT NULL REFERENCES sources(source_id),
            as_of TIMESTAMPTZ NOT NULL,
            transport_health TEXT NOT NULL CHECK (transport_health IN ('OK','DEGRADED','FAILED','UNKNOWN')),
            freshness_health TEXT NOT NULL CHECK (freshness_health IN ('OK','DEGRADED','FAILED','UNKNOWN')),
            completeness_health TEXT NOT NULL CHECK (completeness_health IN ('OK','DEGRADED','FAILED','UNKNOWN')),
            schema_health TEXT NOT NULL CHECK (schema_health IN ('OK','DEGRADED','FAILED','UNKNOWN')),
            details_json JSONB NOT NULL,
            collection_run_id UUID NULL REFERENCES collection_runs(run_id),
            created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
        );

        CREATE TABLE projection_receipts (
            receipt_id TEXT PRIMARY KEY CHECK (receipt_id ~ '^receipt_[0-9a-f]{64}$'),
            receipt_schema_version TEXT NOT NULL,
            projection_name TEXT NOT NULL,
            projection_version TEXT NOT NULL,
            schema_version TEXT NOT NULL,
            algorithm_version TEXT NULL,
            ranking_policy_version TEXT NULL,
            configuration_digest TEXT NOT NULL CHECK (configuration_digest ~ '^sha256:[0-9a-f]{64}$'),
            source_registry_version TEXT NOT NULL CHECK (source_registry_version ~ '^sha256:[0-9a-f]{64}$'),
            as_of TIMESTAMPTZ NOT NULL,
            generated_at TIMESTAMPTZ NOT NULL,
            input_digest TEXT NOT NULL CHECK (input_digest ~ '^sha256:[0-9a-f]{64}$'),
            output_digest TEXT NOT NULL CHECK (output_digest ~ '^sha256:[0-9a-f]{64}$'),
            status TEXT NOT NULL CHECK (status IN ('COMPLETE','FAILED')),
            created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
        );

        CREATE INDEX observations_source_observed_idx ON observations(source_id, observed_at);
        CREATE INDEX observations_observed_idx ON observations(observed_at);
        CREATE INDEX observations_source_item_idx ON observations(source_id, source_item_key);
        CREATE INDEX collection_runs_source_started_idx ON collection_runs(source_id, started_at);
        CREATE INDEX source_health_source_asof_idx ON source_health_observations(source_id, as_of);
        CREATE INDEX relations_from_idx ON observation_relations(from_observation_id);
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TABLE IF EXISTS projection_receipts;
        DROP TABLE IF EXISTS source_health_observations;
        DROP TABLE IF EXISTS observation_relations;
        DROP TABLE IF EXISTS collection_run_observations;
        DROP TABLE IF EXISTS observations;
        DROP TABLE IF EXISTS collection_runs;
        DROP TABLE IF EXISTS sources;
        """
    )
