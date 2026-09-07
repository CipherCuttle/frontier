# ruff: noqa: E402
from __future__ import annotations

import os
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest

psycopg = pytest.importorskip("psycopg")

from frontier.adapters.acquisition.config import load_source_registry
from frontier.adapters.acquisition.normalizers import normalize_hn_frontpage
from frontier.adapters.postgres import PostgresEvidenceStore
from frontier.adapters.postgres.frozen_registry_intelligence import (
    PostgresFrozenRegistryBaselineIntelligenceRepository,
)
from frontier.domain.collection import CollectionReason, CollectionRun
from frontier.domain.digests import sha256_digest
from frontier.domain.health import HealthValue, SourceHealthObservation
from frontier.domain.relation import ObservationRelation, RelationAuthority, RelationType
from frontier.domain.source import AcquisitionClass, SignalRole, SourceContract, SourceTransport

DB_URL = os.getenv("FRONTIER_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="FRONTIER_TEST_DATABASE_URL not set")
REPO_ROOT = Path(__file__).resolve().parents[2]


def _insert_candidate(
    evidence: PostgresEvidenceStore,
    candidate: object,
    *,
    source_id: str,
):
    durable_candidate = replace(candidate, source_id=source_id)
    run = CollectionRun(
        run_id=uuid4(),
        source_id=source_id,
        reason=CollectionReason.SCHEDULED,
        started_at=durable_candidate.retrieved_at,
    )
    evidence.start_collection_run(run)
    observation, inserted = evidence.append_observation(durable_candidate, run.run_id)
    assert inserted
    return observation


def test_frozen_registry_replay_ignores_mutable_db_source_state() -> None:
    assert DB_URL is not None
    registry = load_source_registry(REPO_ROOT)
    frozen_source_id = "hn.frontpage"
    frozen_source = registry.require(frozen_source_id).contract
    expected_roles = tuple(role.value for role in frozen_source.signal_roles)
    extra_source_id = "fixture.confirmatory.contaminant"
    extra_source = SourceContract(
        source_id=extra_source_id,
        display_name="Confirmatory contaminant fixture",
        acquisition_class=AcquisitionClass.A_AUTHORITATIVE_STRUCTURED,
        signal_roles=(SignalRole.PRIMARY_EMISSION,),
        transport=SourceTransport.FIXTURE,
    )

    retrieved_at = datetime(2026, 9, 7, 20, 0, tzinfo=UTC)
    body = b"""<rss version="2.0"><channel>
      <item><title>Frozen alpha</title><link>https://example.com/frozen-alpha</link>
        <comments>https://news.ycombinator.com/item?id=88001</comments></item>
      <item><title>Frozen beta</title><link>https://example.com/frozen-beta</link>
        <comments>https://news.ycombinator.com/item?id=88002</comments></item>
      <item><title>Contaminant</title><link>https://example.com/contaminant</link>
        <comments>https://news.ycombinator.com/item?id=88003</comments></item>
    </channel></rss>"""
    batch = normalize_hn_frontpage(
        body,
        retrieved_at=retrieved_at,
        fetch_digest=sha256_digest(body),
    )
    assert len(batch.candidates) == 3

    with psycopg.connect(DB_URL) as conn:
        evidence = PostgresEvidenceStore(conn)
        evidence.upsert_source(frozen_source)
        evidence.upsert_source(extra_source)
        frozen_a = _insert_candidate(
            evidence, batch.candidates[0], source_id=frozen_source_id
        )
        frozen_b = _insert_candidate(
            evidence, batch.candidates[1], source_id=frozen_source_id
        )
        contaminant = _insert_candidate(
            evidence, batch.candidates[2], source_id=extra_source_id
        )
        as_of = max(
            frozen_a.observed_at,
            frozen_b.observed_at,
            contaminant.observed_at,
        ) + timedelta(seconds=1)

        for source_id in (frozen_source_id, extra_source_id):
            evidence.add_source_health(
                SourceHealthObservation(
                    source_id=source_id,
                    as_of=as_of,
                    transport=HealthValue.OK,
                    freshness=HealthValue.OK,
                    completeness=HealthValue.OK,
                    schema=HealthValue.OK,
                    details={},
                )
            )

        evidence.add_relation(
            ObservationRelation(
                relation_type=RelationType.CORRECTS,
                from_observation_id=frozen_b.observation_id,
                target_observation_id=frozen_a.observation_id,
                authority=RelationAuthority.EXPLICIT,
                evidence={"fixture": "frozen-to-frozen"},
            )
        )
        evidence.add_relation(
            ObservationRelation(
                relation_type=RelationType.CORRECTS,
                from_observation_id=contaminant.observation_id,
                target_observation_id=frozen_a.observation_id,
                authority=RelationAuthority.EXPLICIT,
                evidence={"fixture": "extra-to-frozen"},
            )
        )

        # Hostile mutable-DB drift after collection: the frozen source is now
        # disabled and its DB roles are wrong, while an extra source remains
        # enabled. Confirmatory replay must ignore all three mutations.
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE sources SET enabled = FALSE, signal_roles = %s WHERE source_id = %s",
                ([SignalRole.PRIMARY_EMISSION.value], frozen_source_id),
            )
        conn.commit()

        repository = PostgresFrozenRegistryBaselineIntelligenceRepository(conn, registry)
        assert repository.confirmatory_source_registry_version == registry.source_registry_version
        assert repository.list_enabled_source_ids() == sorted(registry.sources)

        observations = repository.list_baseline_observations_as_of(as_of)
        by_id = {item.observation_id: item for item in observations}
        assert frozen_a.observation_id in by_id
        assert frozen_b.observation_id in by_id
        assert contaminant.observation_id not in by_id
        assert by_id[frozen_a.observation_id].grouping.signal_roles == expected_roles
        assert by_id[frozen_b.observation_id].grouping.signal_roles == expected_roles

        health = repository.list_latest_health_as_of(as_of)
        health_ids = {item.source_id for item in health}
        assert frozen_source_id in health_ids
        assert extra_source_id not in health_ids

        relations = repository.list_grouping_relations_as_of(as_of)
        relation_pairs = {
            (item.from_observation_id, item.target_observation_id) for item in relations
        }
        assert (frozen_b.observation_id, frozen_a.observation_id) in relation_pairs
        assert (contaminant.observation_id, frozen_a.observation_id) not in relation_pairs
