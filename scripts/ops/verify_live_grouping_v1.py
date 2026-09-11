"""Read-only live-corpus equivalence and performance proof for grouping V1.

This script does not publish a projection or receipt. It reads the latest COMPLETE
canonical baseline snapshot, reconstructs the V0 membership partition from that
already-published artifact, evaluates the canonical grouping-scalable-v1
implementation over the exact same point-in-time evidence universe, and requires
membership equality.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Iterable
from typing import Any, cast

import psycopg

from frontier.adapters.postgres.grouping import PostgresGroupingRepository
from frontier.domain.grouping_v1 import (
    GROUPING_V1_ALGORITHM_VERSION,
    GROUPING_V1_PROJECTION_VERSION,
    build_compact_grouping_projection,
)

MAX_LIVE_GROUPING_SECONDS = 300.0


def _partition_from_v0_snapshot(snapshot_json: object) -> tuple[tuple[str, ...], ...]:
    if not isinstance(snapshot_json, dict):
        raise RuntimeError("baseline snapshot_json is not an object")
    payload = cast(dict[str, Any], snapshot_json)
    episodes = payload.get("episodes")
    if not isinstance(episodes, list):
        raise RuntimeError("baseline snapshot episodes are missing or malformed")

    partition: list[tuple[str, ...]] = []
    covered: set[str] = set()
    for episode in episodes:
        if not isinstance(episode, dict):
            raise RuntimeError("baseline episode is not an object")
        observation_ids = episode.get("observation_ids")
        if not isinstance(observation_ids, list) or not observation_ids:
            raise RuntimeError("baseline episode observation_ids are missing or malformed")
        if not all(isinstance(value, str) for value in observation_ids):
            raise RuntimeError("baseline episode observation_ids contain non-string values")
        members = tuple(sorted(cast(Iterable[str], observation_ids)))
        if len(members) != len(set(members)):
            raise RuntimeError("baseline episode contains duplicate observation ids")
        overlap = covered.intersection(members)
        if overlap:
            raise RuntimeError(f"baseline partition overlaps: {sorted(overlap)[:3]}")
        covered.update(members)
        partition.append(members)
    return tuple(sorted(partition))


def _partition_from_v1(projection: object) -> tuple[tuple[str, ...], ...]:
    groups = getattr(projection, "groups")
    ungrouped = getattr(projection, "ungrouped_observation_ids")
    partition = [tuple(group.observation_ids) for group in groups]
    partition.extend((observation_id,) for observation_id in ungrouped)
    return tuple(sorted(partition))


def main() -> int:
    database_url = os.environ.get("FRONTIER_DATABASE_URL_DIRECT")
    if not database_url:
        raise SystemExit("FRONTIER_DATABASE_URL_DIRECT is required")

    with psycopg.connect(database_url, autocommit=True) as connection:
        connection.execute("SET default_transaction_read_only = on")
        read_only = connection.execute("SHOW default_transaction_read_only").fetchone()
        if read_only is None or read_only[0] != "on":
            raise RuntimeError("failed to force read-only database session")

        row = connection.execute(
            """
            SELECT b.as_of, b.snapshot_id, b.snapshot_json, b.receipt_id
            FROM baseline_intelligence_snapshots b
            JOIN projection_receipts r ON r.receipt_id = b.receipt_id
            WHERE r.status = 'COMPLETE'
              AND r.projection_name = 'baseline-intelligence'
            ORDER BY b.as_of DESC, b.snapshot_id DESC
            LIMIT 1
            """
        ).fetchone()
        if row is None:
            raise RuntimeError("no COMPLETE baseline snapshot exists")

        as_of = row[0]
        snapshot_id = cast(str, row[1])
        snapshot_json = row[2]
        receipt_id = cast(str, row[3])

        repository = PostgresGroupingRepository(connection)
        inputs = tuple(repository.list_grouping_inputs_as_of(as_of))
        relations = tuple(repository.list_grouping_relations_as_of(as_of))

        started = time.perf_counter()
        projection = build_compact_grouping_projection(
            inputs,
            relations=relations,
            as_of=as_of,
        )
        elapsed_seconds = time.perf_counter() - started

    v0_partition = _partition_from_v0_snapshot(snapshot_json)
    v1_partition = _partition_from_v1(projection)
    membership_equal = v0_partition == v1_partition
    exhaustive_pair_count = len(inputs) * (len(inputs) - 1) // 2
    candidate_ratio = (
        projection.candidate_pair_count / exhaustive_pair_count if exhaustive_pair_count else 0.0
    )

    result = {
        "as_of": as_of.isoformat().replace("+00:00", "Z"),
        "baseline_receipt_id": receipt_id,
        "baseline_snapshot_id": snapshot_id,
        "candidate_pair_count": projection.candidate_pair_count,
        "candidate_ratio_vs_exhaustive": candidate_ratio,
        "eligible_observation_count": projection.eligible_observation_count,
        "elapsed_seconds": elapsed_seconds,
        "exhaustive_pair_count": exhaustive_pair_count,
        "group_pair_count": projection.group_pair_count,
        "membership_equal": membership_equal,
        "read_only": True,
        "v0_partition_count": len(v0_partition),
        "v1_algorithm_version": GROUPING_V1_ALGORITHM_VERSION,
        "v1_partition_count": len(v1_partition),
        "v1_projection_version": GROUPING_V1_PROJECTION_VERSION,
        "within_300s_live_envelope": elapsed_seconds <= MAX_LIVE_GROUPING_SECONDS,
    }
    print(json.dumps(result, sort_keys=True))

    if not membership_equal:
        v0_only = sorted(set(v0_partition) - set(v1_partition))
        v1_only = sorted(set(v1_partition) - set(v0_partition))
        print(
            json.dumps(
                {
                    "error": "LIVE_GROUPING_V1_MEMBERSHIP_MISMATCH",
                    "v0_only_sample": v0_only[:3],
                    "v1_only_sample": v1_only[:3],
                },
                sort_keys=True,
            )
        )
        return 2
    if elapsed_seconds > MAX_LIVE_GROUPING_SECONDS:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
