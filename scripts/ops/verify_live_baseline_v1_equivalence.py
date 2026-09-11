"""Read-only proof that V1 grouping reproduces the canonical V0 baseline snapshot.

This does NOT claim V0 grouping-receipt/input-digest equivalence: the V0 receipt
binds the exhaustive grouping artifact, including ambiguous_pairs. The proof is
narrower and stronger where it matters for serving output: use V1 membership,
adapt only that membership into the frozen baseline builder, and require the
entire canonical baseline snapshot (including episode IDs/ranks/metrics/health)
to equal the already-published production snapshot at the same PIT boundary.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, cast

import psycopg

from frontier.adapters.postgres.intelligence import PostgresBaselineIntelligenceRepository
from frontier.domain.canonical_json import canonical_json_bytes
from frontier.domain.digests import sha256_digest
from frontier.domain.grouping import GroupingProjection
from frontier.domain.grouping_v1 import build_compact_grouping_projection
from frontier.domain.intelligence import build_baseline_snapshot

MAX_LIVE_BASELINE_SECONDS = 300.0


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
            SELECT b.as_of, b.snapshot_id, b.snapshot_json, b.output_digest,
                   b.receipt_id
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
        published_snapshot_id = cast(str, row[1])
        published_json = row[2]
        published_output_digest = cast(str, row[3])
        published_receipt_id = cast(str, row[4])
        if not isinstance(published_json, dict):
            raise RuntimeError("published baseline snapshot_json is malformed")

        repository = PostgresBaselineIntelligenceRepository(connection)
        observations = tuple(repository.list_baseline_observations_as_of(as_of))
        relations = tuple(repository.list_grouping_relations_as_of(as_of))
        enabled_source_ids = tuple(repository.list_enabled_source_ids())
        health = tuple(repository.list_latest_health_as_of(as_of))

        grouping_started = time.perf_counter()
        compact = build_compact_grouping_projection(
            (item.grouping for item in observations),
            relations=relations,
            as_of=as_of,
        )
        grouping_seconds = time.perf_counter() - grouping_started

        # Baseline V0 only consumes membership from GroupingProjection. Keep its
        # frozen V0 schema/algorithm defaults so episode identity remains frozen.
        # Do not use this synthetic projection to claim V0 grouping receipt parity.
        membership_adapter = GroupingProjection(
            as_of=as_of,
            groups=compact.groups,
            ambiguous_pairs=(),
            ungrouped_observation_ids=compact.ungrouped_observation_ids,
        )

        baseline_started = time.perf_counter()
        rebuilt = build_baseline_snapshot(
            observations,
            grouping_projection=membership_adapter,
            enabled_source_ids=enabled_source_ids,
            health=health,
            as_of=as_of,
        )
        baseline_scoring_seconds = time.perf_counter() - baseline_started

    rebuilt_canonical = rebuilt.to_canonical()
    canonical_equal = rebuilt_canonical == cast(dict[str, Any], published_json)
    snapshot_id_equal = rebuilt.snapshot_id == published_snapshot_id
    rebuilt_output_digest = str(sha256_digest(canonical_json_bytes(rebuilt_canonical)))
    output_digest_equal = rebuilt_output_digest == published_output_digest
    total_seconds = grouping_seconds + baseline_scoring_seconds

    result = {
        "as_of": as_of.isoformat().replace("+00:00", "Z"),
        "baseline_receipt_id": published_receipt_id,
        "baseline_scoring_seconds": baseline_scoring_seconds,
        "canonical_snapshot_equal": canonical_equal,
        "eligible_observation_count": compact.eligible_observation_count,
        "episode_count": len(rebuilt.episodes),
        "grouping_seconds": grouping_seconds,
        "output_digest_equal": output_digest_equal,
        "published_snapshot_id": published_snapshot_id,
        "read_only": True,
        "rebuilt_snapshot_id": rebuilt.snapshot_id,
        "receipt_equivalence_claimed": False,
        "snapshot_id_equal": snapshot_id_equal,
        "total_seconds": total_seconds,
        "within_300s_live_envelope": total_seconds <= MAX_LIVE_BASELINE_SECONDS,
    }
    print(json.dumps(result, sort_keys=True))

    if not (canonical_equal and snapshot_id_equal and output_digest_equal):
        return 2
    if total_seconds > MAX_LIVE_BASELINE_SECONDS:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
