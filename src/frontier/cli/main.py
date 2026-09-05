from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from uuid import uuid4

from frontier.adapters.fixture.normalizer import load_fixture_candidate
from frontier.domain.canonical_json import canonical_json_text
from frontier.domain.collection import CollectionReason, CollectionRun
from frontier.domain.observation import Observation
from frontier.domain.source import (
    AcquisitionClass,
    SignalRole,
    SourceContract,
    SourceTransport,
)


def _source() -> SourceContract:
    return SourceContract(
        source_id="fixture.hostile_document",
        display_name="Hostile document fixture",
        acquisition_class=AcquisitionClass.C_PERMITTED_EXTRACTION,
        signal_roles=(SignalRole.PRIMARY_EMISSION,),
        transport=SourceTransport.FIXTURE,
    )


def replay_fixture(path: Path) -> int:
    candidate, observed_at = load_fixture_candidate(path)
    observation = Observation(candidate=candidate, observed_at=observed_at)
    print(canonical_json_text(observation.to_canonical()))
    return 0


def ingest_fixture(path: Path, database_url: str) -> int:
    import psycopg

    from frontier.adapters.postgres import PostgresEvidenceStore

    candidate, _ = load_fixture_candidate(path)
    with psycopg.connect(database_url) as conn:
        store = PostgresEvidenceStore(conn)
        source = _source()
        store.upsert_source(source)
        run = CollectionRun(
            run_id=uuid4(),
            source_id=source.source_id,
            reason=CollectionReason.SCHEDULED,
            started_at=candidate.retrieved_at,
        )
        store.start_collection_run(run)
        observation, inserted = store.append_observation(candidate, run.run_id)
    print(json.dumps({"inserted": inserted, "observation_id": observation.observation_id}))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="frontier")
    sub = parser.add_subparsers(dest="command", required=True)
    replay = sub.add_parser("replay-fixture")
    replay.add_argument("fixture", type=Path)
    ingest = sub.add_parser("ingest-fixture")
    ingest.add_argument("fixture", type=Path)
    ingest.add_argument("--database-url", default=os.getenv("FRONTIER_TEST_DATABASE_URL"))
    args = parser.parse_args()
    if args.command == "replay-fixture":
        return replay_fixture(args.fixture)
    if not args.database_url:
        parser.error("--database-url or FRONTIER_TEST_DATABASE_URL is required")
    return ingest_fixture(args.fixture, args.database_url)


if __name__ == "__main__":
    raise SystemExit(main())
