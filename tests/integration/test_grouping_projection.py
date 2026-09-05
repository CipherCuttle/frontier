# ruff: noqa: E402
from __future__ import annotations

import os
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

psycopg = pytest.importorskip("psycopg")

from frontier.adapters.acquisition.normalizers import normalize_hn_frontpage
from frontier.adapters.postgres import PostgresEvidenceStore
from frontier.adapters.postgres.grouping import PostgresGroupingRepository
from frontier.application.grouping import run_grouping_projection
from frontier.domain.collection import CollectionReason, CollectionRun
from frontier.domain.digests import Digest, sha256_digest
from frontier.domain.source import AcquisitionClass, SignalRole, SourceContract, SourceTransport

DB_URL = os.getenv("FRONTIER_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="FRONTIER_TEST_DATABASE_URL not set")


def test_postgres_grouping_reads_canonical_evidence_and_persists_receipt() -> None:
    assert DB_URL is not None
    retrieved_at = datetime(2026, 9, 5, 10, tzinfo=UTC)
    body = b"""<rss version="2.0"><channel>
      <item><title>First discussion</title><link>https://example.com/release</link>
        <comments>https://news.ycombinator.com/item?id=88001</comments></item>
      <item><title>Completely different discussion title</title>
        <link>https://example.com/release</link>
        <comments>https://news.ycombinator.com/item?id=88002</comments></item>
    </channel></rss>"""
    batch = normalize_hn_frontpage(
        body,
        retrieved_at=retrieved_at,
        fetch_digest=sha256_digest(body),
    )
    source_id = "fixture.grouping.attention"
    candidates = tuple(replace(candidate, source_id=source_id) for candidate in batch.candidates)

    source = SourceContract(
        source_id=source_id,
        display_name="Grouping attention fixture",
        acquisition_class=AcquisitionClass.A_AUTHORITATIVE_STRUCTURED,
        signal_roles=(SignalRole.ATTENTION,),
        transport=SourceTransport.FIXTURE,
    )

    with psycopg.connect(DB_URL) as conn:
        evidence = PostgresEvidenceStore(conn)
        evidence.upsert_source(source)
        observations = []
        for candidate in candidates:
            run = CollectionRun(
                run_id=uuid4(),
                source_id=source_id,
                reason=CollectionReason.SCHEDULED,
                started_at=candidate.retrieved_at,
            )
            evidence.start_collection_run(run)
            observation, inserted = evidence.append_observation(candidate, run.run_id)
            assert inserted
            observations.append(observation)

        as_of = max(observation.observed_at for observation in observations) + timedelta(seconds=1)
        grouping = PostgresGroupingRepository(conn)
        inputs = grouping.list_grouping_inputs_as_of(as_of)
        fixture_inputs = [item for item in inputs if item.source_id == source_id]
        assert len(fixture_inputs) == 2
        assert all(item.signal_roles == ("ATTENTION",) for item in fixture_inputs)

        result = run_grouping_projection(
            grouping,
            as_of=as_of,
            generated_at=as_of + timedelta(seconds=1),
            source_registry_version=Digest(
                "sha256:498b4afff3b5a0dcbfb448514a08a3e85adf7f8f2dd5d0863aebbcb353c361f8"
            ),
        )
        fixture_ids = {observation.observation_id for observation in observations}
        assert any(fixture_ids <= set(group.observation_ids) for group in result.projection.groups)

        with conn.cursor() as cur:
            cur.execute(
                "SELECT status, algorithm_version FROM projection_receipts WHERE receipt_id = %s",
                (result.receipt.receipt_id,),
            )
            row = cur.fetchone()
        assert row == ("COMPLETE", "guarded-hybrid-v0")
