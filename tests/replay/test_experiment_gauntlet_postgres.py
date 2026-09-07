# ruff: noqa: E402
"""G10 (WP11) DB-bound replay gauntlet against real PostgreSQL.

Hostile mutations that need the canonical DB are asserted here with the
SKIP-pattern PG integration used by every prior WP; the pure in-memory cases
stay unit-fast in ``test_experiment_gauntlet.py``. DB-bound coverage:

- G10-POSITIVE-DB : the full pipeline replay from persisted inputs reproduces
  the candidate artifact digest and the evaluation receipt digest
  byte-identically (positive control through the real repositories).
- G10-C09-DB      : deleting a mid-window run is refused by the append-only
  trigger; the stored evidence stays intact and still evaluates.
- G10-C10         : a duplicate (experiment_id, as_of) insert is an idempotent
  no-op — re-persisting the identical run and re-recording the identical
  attempt never creates duplicate rows.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import LiteralString, cast

import pytest

psycopg = pytest.importorskip("psycopg")

from psycopg import Connection

from frontier.adapters.postgres.advanced_intelligence import (
    PostgresCandidateFreezeRepository,
    PostgresEvaluationRepository,
    PostgresPefArtifactRepository,
)
from frontier.adapters.postgres.evaluation_store import (
    PostgresEvaluationArtifactStore,
)
from frontier.adapters.postgres.experiment_attempts import (
    PostgresExperimentAttemptRepository,
    PostgresShadowRunPersister,
)
from frontier.adapters.postgres.intelligence import (
    PostgresBaselineIntelligenceRepository,
)
from frontier.application.advanced_intelligence import PefRankingRun, run_pef_v0_ranking
from frontier.application.evaluation import evaluate_shadow_experiment_from_persisted
from frontier.application.evaluation_loaders import PersistedRunRef, load_paired_snapshot
from frontier.domain.advanced_intelligence import (
    PEF_EXPERIMENT_ID,
    ShadowExperimentRun,
    build_shadow_experiment_run,
)
from frontier.domain.candidate_freeze import (
    CandidateFreezeReceipt,
    FreezeInputs,
    build_candidate_freeze_receipt,
)
from frontier.domain.digests import Digest
from frontier.domain.grouping import EpisodeGroup, GroupingInput, GroupingProjection
from frontier.domain.health import HealthValue
from frontier.domain.intelligence import (
    BaselineHealthInput,
    BaselineObservationInput,
    BaselineSnapshot,
    build_baseline_receipt,
    build_baseline_snapshot,
)
from frontier.domain.opportunity import ExperimentAttemptStatus, ExperimentRunAttempt
from frontier.domain.receipt import ProjectionReceipt

DB_URL = os.getenv("FRONTIER_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="FRONTIER_TEST_DATABASE_URL not set")

# Session-unique 300s-aligned boundary so repeated sessions never collide.
_SESSION_OFFSET = (int(uuid.uuid4().hex[:8], 16) % 24_000) * 300
BOUNDARY = datetime.fromtimestamp(
    (int(datetime.now(tz=UTC).timestamp()) // 300) * 300 - _SESSION_OFFSET, tz=UTC
)
FROZEN_AT = BOUNDARY - timedelta(days=30)
REGISTRY = Digest("sha256:" + "1" * 64)

ConnectionT = Connection[tuple[object, ...]]


@pytest.fixture()
def conn() -> Iterator[ConnectionT]:
    assert DB_URL is not None
    connection = psycopg.connect(DB_URL)
    try:
        yield connection
    finally:
        connection.rollback()
        connection.close()


@dataclass(frozen=True, slots=True)
class _World:
    """One deterministic paired world plus the inputs it can replay from."""

    observations: tuple[BaselineObservationInput, ...]
    snapshot: BaselineSnapshot
    receipt: ProjectionReceipt
    candidate: PefRankingRun
    freeze: CandidateFreezeReceipt
    run: ShadowExperimentRun


def _observations(as_of: datetime) -> tuple[BaselineObservationInput, ...]:
    live = BaselineObservationInput(
        grouping=GroupingInput(
            observation_id="obs_" + uuid.uuid4().hex,
            source_id="pypi.updates",
            source_item_key=f"live-{uuid.uuid4().hex}",
            kind="DOCUMENT",
            observed_at=as_of - timedelta(minutes=1),
            canonical_url=f"https://example.test/live-{uuid.uuid4().hex}",
            title="Gauntlet replay live episode",
            text=None,
            signal_roles=("PRIMARY_EMISSION",),
        ),
        first_reason="SCHEDULED",
        recovered_after_gap=False,
    )
    dormant = replace(
        live,
        grouping=replace(
            live.grouping,
            observation_id="obs_" + uuid.uuid4().hex,
            source_item_key=f"dormant-{uuid.uuid4().hex}",
            canonical_url=f"https://example.test/dormant-{uuid.uuid4().hex}",
        ),
    )
    return (live, dormant)


def _build_world(observations: tuple[BaselineObservationInput, ...], *, as_of: datetime) -> _World:
    """Deterministic paired world: identical inputs always yield identical ids."""
    grouped = ((observations[0].observation_id,), (observations[1].observation_id,))
    grouped_ids = {observation_id for group in grouped for observation_id in group}
    projection = GroupingProjection(
        as_of=as_of,
        groups=tuple(
            EpisodeGroup(group_id=f"grp_{index:064x}", observation_ids=tuple(sorted(group)))
            for index, group in enumerate(grouped, start=1)
        ),
        ambiguous_pairs=(),
        ungrouped_observation_ids=tuple(
            sorted(
                item.observation_id
                for item in observations
                if item.observation_id not in grouped_ids
            )
        ),
    )
    health = BaselineHealthInput(
        source_id="pypi.updates",
        as_of=as_of - timedelta(minutes=1),
        transport=HealthValue.OK,
        freshness=HealthValue.OK,
        completeness=HealthValue.OK,
        schema=HealthValue.OK,
    )
    snapshot = build_baseline_snapshot(
        observations,
        grouping_projection=projection,
        enabled_source_ids=("pypi.updates",),
        health=(health,),
        as_of=as_of,
    )
    receipt = build_baseline_receipt(
        snapshot,
        observations=observations,
        grouping_projection=projection,
        enabled_source_ids=("pypi.updates",),
        health=(health,),
        generated_at=as_of,
        source_registry_version=REGISTRY,
    )
    candidate = run_pef_v0_ranking(
        observations,
        control_snapshot=snapshot,
        control_receipt=receipt,
        generated_at=as_of,
        source_registry_version=REGISTRY,
    )
    freeze = build_candidate_freeze_receipt(
        FreezeInputs(
            preregistration_digest=Digest("sha256:" + "2" * 64),
            preregistration_config_digest=Digest(
                "sha256:e2627f62deac24e5f1b09960687761ebbcc61b3fd0c8fec07fec0006dcff7dc1"
            ),
            implementation_commit="a" * 64,
            implementation_tree_digest="b" * 64,
            dependency_lock_digest=Digest("sha256:" + "3" * 64),
            source_registry_digest=REGISTRY,
            registry_entry_digests=(),
        ),
        frozen_at=FROZEN_AT,
    )
    run = build_shadow_experiment_run(
        control_snapshot=snapshot,
        control_receipt=receipt,
        candidate_artifact=candidate.artifact,
        candidate_receipt=candidate.receipt,
        as_of=snapshot.as_of,
        generated_at=as_of,
        candidate_freeze_receipt_id=freeze.receipt_id,
    )
    return _World(
        observations=observations,
        snapshot=snapshot,
        receipt=receipt,
        candidate=candidate,
        freeze=freeze,
        run=run,
    )


def _persist(conn: ConnectionT, world: _World, *, run_class: str = "DEV") -> None:
    """Persist the whole world through the append-only repositories (idempotent)."""
    PostgresBaselineIntelligenceRepository(conn).publish_complete_snapshot(
        world.snapshot, world.receipt
    )
    PostgresPefArtifactRepository(conn).publish_complete_artifact(
        world.candidate.artifact, world.candidate.receipt
    )
    PostgresCandidateFreezeRepository(conn).record_receipt(world.freeze)
    PostgresShadowRunPersister(conn).persist(world.run, run_class=run_class)


def _row_count(conn: ConnectionT, sql: LiteralString, *params: object) -> int:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        row = cur.fetchone()
    assert row is not None
    return int(cast(int, row[0]))


class TestPositiveReplayDb:
    def test_gauntlet_positive_db_replay_reproduces_byte_identical_artifacts(
        self, conn: ConnectionT
    ) -> None:
        """POSITIVE control through the real repositories."""
        observations = _observations(BOUNDARY)
        world = _build_world(observations, as_of=BOUNDARY)
        _persist(conn, world)
        # Full replay from the SAME frozen inputs, generated_at pinned.
        replayed = _build_world(observations, as_of=BOUNDARY)
        assert replayed.run.run_id == world.run.run_id
        assert replayed.candidate.artifact.artifact_id == world.candidate.artifact.artifact_id
        assert replayed.receipt.receipt_id == world.receipt.receipt_id
        # Re-persisting the replayed world is an idempotent no-op: identical
        # content-derived identities never create duplicate rows.
        _persist(conn, replayed)
        assert (
            _row_count(
                conn,
                "SELECT count(*) FROM shadow_experiment_runs WHERE run_id = %s",
                world.run.run_id,
            )
            == 1
        )
        assert (
            _row_count(
                conn,
                "SELECT count(*) FROM pef_ranking_artifacts WHERE artifact_id = %s",
                world.candidate.artifact.artifact_id,
            )
            == 1
        )
        assert (
            _row_count(
                conn,
                "SELECT count(*) FROM candidate_freeze_receipts WHERE receipt_id = %s",
                world.freeze.receipt_id,
            )
            == 1
        )
        # Evaluation replay reproduces the receipt digest byte-identically.
        store = PostgresEvaluationArtifactStore(conn)
        loaded = load_paired_snapshot(store, world.run.run_id, as_of=BOUNDARY)
        assert loaded.run == world.run
        horizon = BOUNDARY + timedelta(hours=1)
        refs = (PersistedRunRef(world.run.run_id, BOUNDARY),)
        first = evaluate_shadow_experiment_from_persisted(
            store=store,
            runs=refs,
            opportunity_groups=(),
            evaluation_horizon=horizon,
            generated_at=horizon,
            receipt_repository=PostgresEvaluationRepository(conn),
        )
        second = evaluate_shadow_experiment_from_persisted(
            store=store,
            runs=refs,
            opportunity_groups=(),
            evaluation_horizon=horizon,
            generated_at=horizon,
            receipt_repository=PostgresEvaluationRepository(conn),
        )
        assert first.evaluation_id == second.evaluation_id
        assert (
            _row_count(
                conn,
                "SELECT count(*) FROM evaluation_receipts WHERE evaluation_id = %s",
                first.evaluation_id,
            )
            == 1
        )


class TestHostileMutationDb:
    def test_g10_c09_db_delete_mid_window_run_is_refused_by_trigger(
        self, conn: ConnectionT
    ) -> None:
        world = _build_world(_observations(BOUNDARY), as_of=BOUNDARY)
        _persist(conn, world)
        # The append-only substrate refuses ANY deletion of stored evidence.
        with pytest.raises(psycopg.errors.Error), conn.cursor() as cur:
            cur.execute("DELETE FROM shadow_experiment_runs WHERE run_id = %s", (world.run.run_id,))
        conn.rollback()
        assert (
            _row_count(
                conn,
                "SELECT count(*) FROM shadow_experiment_runs WHERE run_id = %s",
                world.run.run_id,
            )
            == 1
        )
        # The intact store still evaluates: deletion cannot erase the window.
        store = PostgresEvaluationArtifactStore(conn)
        loaded = load_paired_snapshot(store, world.run.run_id, as_of=BOUNDARY)
        assert loaded.run == world.run

    def test_g10_c10_duplicate_experiment_as_of_insert_is_idempotent_noop(
        self, conn: ConnectionT
    ) -> None:
        # Session-unique boundary: tests commit through the repos' transaction
        # blocks, so every DB-bound gauntlet case claims its own 300s-aligned
        # boundary to keep the as_of-scoped uniqueness assertion exact.
        unique_boundary = BOUNDARY + timedelta(seconds=300 * 7)
        world = _build_world(_observations(unique_boundary), as_of=unique_boundary)
        _persist(conn, world)
        # Duplicate (experiment_id, as_of) run persistence: content-derived
        # identity makes the re-insert a no-op — exactly one row survives.
        _persist(conn, world)
        assert (
            _row_count(
                conn,
                "SELECT count(*) FROM shadow_experiment_runs WHERE run_id = %s",
                world.run.run_id,
            )
            == 1
        )
        assert (
            _row_count(
                conn,
                "SELECT count(*) FROM shadow_experiment_runs WHERE as_of = %s",
                (unique_boundary,),
            )
            == 1
        )
        # The attempts lease table is UNIQUE (experiment_id, as_of, attempt_no):
        # re-recording the identical PENDING attempt is a no-op, not a dup.
        attempts = PostgresExperimentAttemptRepository(conn)
        pending = ExperimentRunAttempt(
            experiment_id=PEF_EXPERIMENT_ID,
            as_of=unique_boundary,
            attempt_no=1,
            status=ExperimentAttemptStatus.PENDING,
        )
        assert attempts.record_attempt(pending) is True
        assert attempts.record_attempt(pending) is False
        assert (
            _row_count(
                conn,
                "SELECT count(*) FROM experiment_run_attempts "
                "WHERE experiment_id = %s AND as_of = %s AND attempt_no = %s",
                PEF_EXPERIMENT_ID,
                unique_boundary,
                1,
            )
            == 1
        )
