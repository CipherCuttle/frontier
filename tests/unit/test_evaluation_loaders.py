"""Unit tests for persisted-artifact evaluation loaders (WP4, G2).

Covers the fail-closed rejection matrix, digest-recomputation tamper
detection, happy-path PairedSnapshot identity equality, and the mandatory
sprint-authority boundary tests A-F.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta

import pytest

from frontier.application.advanced_intelligence import PefRankingRun, run_pef_v0_ranking
from frontier.application.evaluation import (
    PairedSnapshot,
    _confirmatory_run_binding_failure,  # pyright: ignore[reportPrivateUsage]
    evaluate_shadow_experiment_from_persisted,
)
from frontier.application.evaluation_loaders import (
    CONFIRMATORY_RUN_CLASS,
    DEV_RUN_CLASS,
    PersistedArtifactRow,
    PersistedBaselineSnapshotRow,
    PersistedEvaluationError,
    PersistedFeatureVectorRow,
    PersistedFreezeReceiptRow,
    PersistedProjectionReceiptRow,
    PersistedRunRef,
    PersistedRunRow,
    load_paired_snapshot,
)
from frontier.application.opportunity_outcome import RANKING_WINDOW_SECONDS
from frontier.domain.advanced_intelligence import (
    SHADOW_RUN_ID_PREFIX,
    ShadowExperimentRun,
    ShadowRunStatus,
    build_shadow_experiment_run,
)
from frontier.domain.candidate_freeze import (
    CandidateFreezeReceipt,
    FreezeInputs,
    FreezeStatus,
    build_candidate_freeze_receipt,
)
from frontier.domain.canonical_json import canonical_json_bytes
from frontier.domain.digests import Digest
from frontier.domain.evaluation import EvaluationReceipt, EvaluationStatus
from frontier.domain.grouping import EpisodeGroup, GroupingInput, GroupingProjection
from frontier.domain.health import HealthValue
from frontier.domain.intelligence import (
    BaselineHealthInput,
    BaselineObservationInput,
    BaselineSnapshot,
    build_baseline_receipt,
    build_baseline_snapshot,
)
from frontier.domain.receipt import ProjectionReceipt

FROZEN_AT = datetime(2026, 9, 1, 0, 0, tzinfo=UTC)
DURABLE_AT = FROZEN_AT + timedelta(seconds=120)
AS_OF = DURABLE_AT + timedelta(seconds=300)
REGISTRY = Digest("sha256:" + "1" * 64)


def _hex_digest(payload: Mapping[str, object]) -> str:
    return hashlib.sha256(canonical_json_bytes(dict(payload))).hexdigest()


def _observation(label: str, observed_at: datetime) -> BaselineObservationInput:
    return BaselineObservationInput(
        grouping=GroupingInput(
            observation_id="obs_" + hashlib.sha256(label.encode()).hexdigest(),
            source_id="pypi.updates",
            source_item_key=label,
            kind="DOCUMENT",
            observed_at=observed_at,
            canonical_url=f"https://example.test/{label}",
            title=f"Fixture {label} episode title",
            text=None,
            signal_roles=("PRIMARY_EMISSION",),
        ),
        first_reason="SCHEDULED",
        recovered_after_gap=False,
    )


def _paired_inputs(
    as_of: datetime,
) -> tuple[tuple[BaselineObservationInput, ...], tuple[tuple[str, ...], ...]]:
    live = _observation("live", as_of - timedelta(minutes=1))
    dormant = _observation("dormant", as_of - timedelta(minutes=1))
    return (live, dormant), ((live.observation_id,), (dormant.observation_id,))


def _projection(
    observations: tuple[BaselineObservationInput, ...],
    *,
    grouped: tuple[tuple[str, ...], ...],
    as_of: datetime,
) -> GroupingProjection:
    grouped_ids = {observation_id for group in grouped for observation_id in group}
    return GroupingProjection(
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


def _health(as_of: datetime) -> BaselineHealthInput:
    return BaselineHealthInput(
        source_id="pypi.updates",
        as_of=as_of - timedelta(minutes=1),
        transport=HealthValue.OK,
        freshness=HealthValue.OK,
        completeness=HealthValue.OK,
        schema=HealthValue.OK,
    )


def _control(as_of: datetime) -> tuple[BaselineSnapshot, ProjectionReceipt]:
    observations, grouped = _paired_inputs(as_of)
    projection = _projection(observations, grouped=grouped, as_of=as_of)
    snapshot = build_baseline_snapshot(
        observations,
        grouping_projection=projection,
        enabled_source_ids=("pypi.updates",),
        health=(_health(as_of),),
        as_of=as_of,
    )
    receipt = build_baseline_receipt(
        snapshot,
        observations=observations,
        grouping_projection=projection,
        enabled_source_ids=("pypi.updates",),
        health=(_health(as_of),),
        generated_at=as_of,
        source_registry_version=REGISTRY,
    )
    return snapshot, receipt


def _freeze(*, frozen: bool = True) -> CandidateFreezeReceipt:
    return _freeze_with_prereg(Digest("sha256:" + "2" * 64), frozen=frozen)


def _freeze_with_prereg(
    preregistration_digest: Digest, *, frozen: bool = True
) -> CandidateFreezeReceipt:
    inputs = FreezeInputs(
        preregistration_digest=preregistration_digest,
        preregistration_config_digest=(
            Digest("sha256:e2627f62deac24e5f1b09960687761ebbcc61b3fd0c8fec07fec0006dcff7dc1")
            if frozen
            else None
        ),
        implementation_commit="a" * 64 if frozen else None,
        implementation_tree_digest="b" * 64 if frozen else None,
        dependency_lock_digest=Digest("sha256:" + "3" * 64) if frozen else None,
        source_registry_digest=REGISTRY if frozen else None,
        registry_entry_digests=() if frozen else None,
    )
    return build_candidate_freeze_receipt(inputs, frozen_at=FROZEN_AT)


@dataclass
class _Paired:
    snapshot: BaselineSnapshot
    control_receipt: ProjectionReceipt
    candidate: PefRankingRun
    run: ShadowExperimentRun


def _paired(as_of: datetime, *, freeze_id: str | None) -> _Paired:
    snapshot, receipt = _control(as_of)
    candidate = run_pef_v0_ranking(
        _paired_inputs(as_of)[0],
        control_snapshot=snapshot,
        control_receipt=receipt,
        generated_at=as_of,
        source_registry_version=REGISTRY,
    )
    run = build_shadow_experiment_run(
        control_snapshot=snapshot,
        control_receipt=receipt,
        candidate_artifact=candidate.artifact,
        candidate_receipt=candidate.receipt,
        as_of=snapshot.as_of,
        generated_at=as_of,
        candidate_freeze_receipt_id=freeze_id,
    )
    return _Paired(snapshot, receipt, candidate, run)


class FakeStore:
    """In-memory double of :class:`EvaluationArtifactStore` for unit tests."""

    def __init__(self) -> None:
        self.runs: dict[str, PersistedRunRow] = {}
        self.artifacts: dict[str, PersistedArtifactRow] = {}
        self.snapshots: dict[str, PersistedBaselineSnapshotRow] = {}
        self.receipts: dict[str, PersistedProjectionReceiptRow] = {}
        self.freeze_receipts: dict[str, PersistedFreezeReceiptRow] = {}
        self.feature_rows: dict[str, tuple[PersistedFeatureVectorRow, ...]] = {}

    def fetch_run_row(self, run_id: str) -> PersistedRunRow | None:
        return self.runs.get(run_id)

    def fetch_candidate_artifact_row(self, artifact_id: str) -> PersistedArtifactRow | None:
        return self.artifacts.get(artifact_id)

    def fetch_baseline_snapshot_row(self, snapshot_id: str) -> PersistedBaselineSnapshotRow | None:
        return self.snapshots.get(snapshot_id)

    def fetch_projection_receipt_row(self, receipt_id: str) -> PersistedProjectionReceiptRow | None:
        return self.receipts.get(receipt_id)

    def fetch_freeze_receipt_row(self, receipt_id: str) -> PersistedFreezeReceiptRow | None:
        return self.freeze_receipts.get(receipt_id)

    def fetch_feature_batch_rows(self, batch_id: str) -> tuple[PersistedFeatureVectorRow, ...]:
        return self.feature_rows.get(batch_id, ())


def _receipt_row(receipt: ProjectionReceipt) -> PersistedProjectionReceiptRow:
    return PersistedProjectionReceiptRow(
        receipt_id=receipt.receipt_id,
        projection_name=receipt.projection_name,
        projection_version=receipt.projection_version,
        schema_version=receipt.schema_version,
        algorithm_version=receipt.algorithm_version,
        ranking_policy_version=receipt.ranking_policy_version,
        configuration_digest=str(receipt.configuration_digest),
        source_registry_version=str(receipt.source_registry_version),
        output_digest=str(receipt.output_digest),
        status=receipt.status.value,
    )


def _seed(store: FakeStore, paired: _Paired, *, run_class: str = CONFIRMATORY_RUN_CLASS) -> None:
    run = paired.run
    artifact = paired.candidate.artifact
    store.runs[run.run_id] = PersistedRunRow(
        run_id=run.run_id,
        run_digest=str(run.run_digest),
        run_class=run_class,
        status=run.status.value,
        run_json=dict(run.to_canonical()),
    )
    store.artifacts[artifact.artifact_id] = PersistedArtifactRow(
        artifact_id=artifact.artifact_id,
        output_digest=str(artifact.output_digest),
        status=artifact.status.value,
        receipt_id=paired.candidate.receipt.receipt_id,
        artifact_json=dict(artifact.to_canonical()),
    )
    store.snapshots[paired.snapshot.snapshot_id] = PersistedBaselineSnapshotRow(
        snapshot_id=paired.snapshot.snapshot_id,
        output_digest=str(paired.control_receipt.output_digest),
        receipt_id=paired.control_receipt.receipt_id,
        snapshot_json=dict(paired.snapshot.to_canonical()),
    )
    store.receipts[paired.control_receipt.receipt_id] = _receipt_row(paired.control_receipt)
    store.receipts[paired.candidate.receipt.receipt_id] = _receipt_row(paired.candidate.receipt)


def _seed_freeze(
    store: FakeStore, freeze: CandidateFreezeReceipt, *, durable: datetime | None = DURABLE_AT
) -> None:
    store.freeze_receipts[freeze.receipt_id] = PersistedFreezeReceiptRow(
        receipt_id=freeze.receipt_id,
        receipt_digest=str(freeze.receipt_digest),
        status=freeze.status.value,
        durable_freeze_at=durable,
        receipt_json=dict(freeze.to_canonical()),
    )


def _default_store() -> tuple[FakeStore, _Paired, CandidateFreezeReceipt]:
    freeze = _freeze()
    paired = _paired(AS_OF, freeze_id=freeze.receipt_id)
    store = FakeStore()
    _seed(store, paired)
    _seed_freeze(store, freeze)
    return store, paired, freeze


def _retamper(payload: Mapping[str, object]) -> tuple[str, str]:
    """Digest a mutated payload: returns (digest_column_text, hex_digest)."""
    hexdigest = _hex_digest(payload)
    return "sha256:" + hexdigest, hexdigest


def _rebind_run(
    store: FakeStore, paired: _Paired, mutate: Callable[[dict[str, object]], None]
) -> str:
    """Coherently retamper the run payload so digest checks still pass."""
    payload: dict[str, object] = dict(paired.run.to_canonical())
    mutate(payload)
    digest, hexdigest = _retamper(payload)
    new_id = SHADOW_RUN_ID_PREFIX + hexdigest
    old = store.runs[paired.run.run_id]
    store.runs[new_id] = PersistedRunRow(
        run_id=new_id,
        run_digest=digest,
        run_class=old.run_class,
        status=old.status,
        run_json=payload,
    )
    return new_id


def _retamper_candidate(
    store: FakeStore, paired: _Paired, mutate: Callable[[dict[str, object]], None]
) -> str:
    """Retamper the candidate artifact AND the run binding coherently."""
    payload: dict[str, object] = dict(paired.candidate.artifact.to_canonical())
    mutate(payload)
    artifact_digest, artifact_hex = _retamper(payload)
    new_artifact_id = "artifact_" + artifact_hex
    store.artifacts[new_artifact_id] = PersistedArtifactRow(
        artifact_id=new_artifact_id,
        output_digest=artifact_digest,
        status="RAN",
        receipt_id=paired.candidate.receipt.receipt_id,
        artifact_json=payload,
    )

    candidate_receipt_id = paired.candidate.receipt.receipt_id
    store.receipts[candidate_receipt_id] = replace(
        store.receipts[candidate_receipt_id], output_digest=artifact_digest
    )

    def rebind(run_payload: dict[str, object]) -> None:
        run_payload["candidate_artifact_id"] = new_artifact_id
        run_payload["candidate_output_digest"] = artifact_digest

    return _rebind_run(store, paired, rebind)


def _feature_rows(
    paired: _Paired, *, batch_id: str = "batch_" + "9" * 60
) -> tuple[PersistedFeatureVectorRow, ...]:
    batch_digest = "sha256:" + "9" * 64
    vectors: list[PersistedFeatureVectorRow] = []
    for index, episode in enumerate(paired.snapshot.episodes):
        payload: dict[str, object] = {
            "episode_id": episode.episode_id,
            "index": index,
            "schema_version": "feature-vector-v0",
        }
        vectors.append(
            PersistedFeatureVectorRow(
                vector_id=f"vector_{index:064x}",
                batch_id=batch_id,
                batch_digest=batch_digest,
                episode_id=episode.episode_id,
                control_snapshot_id=paired.run.control_snapshot_id,
                episode_universe_digest=str(paired.run.episode_universe_digest),
                as_of=paired.run.as_of,
                vector_digest="sha256:" + _hex_digest(payload),
                vector_json=payload,
            )
        )
    return tuple(vectors)


# ---------------------------------------------------------------------------
# Happy path and identity equality.
# ---------------------------------------------------------------------------


class TestHappyPath:
    def test_happy_path_paired_snapshot_identity_equals_hand_built(self) -> None:
        store, paired, _ = _default_store()
        loaded = load_paired_snapshot(store, paired.run.run_id, as_of=AS_OF)
        expected = PairedSnapshot(
            run=paired.run,
            candidate_rank_by_episode={
                episode.episode_id: episode.rank for episode in paired.candidate.artifact.episodes
            },
            episode_memberships={
                episode.episode_id: episode.observation_ids for episode in paired.snapshot.episodes
            },
        )
        assert loaded.snapshot == expected
        assert loaded.run == paired.run
        assert loaded.run_class == CONFIRMATORY_RUN_CLASS

    def test_loader_resolves_the_digest_verified_freeze_receipt(self) -> None:
        store, paired, freeze = _default_store()
        loaded = load_paired_snapshot(store, paired.run.run_id, as_of=AS_OF)
        assert loaded.freeze_receipt == freeze
        assert loaded.freeze_receipt.receipt_id == paired.run.candidate_freeze_receipt_id

    def test_loaded_run_digest_is_recomputed_not_trusted(self) -> None:
        store, paired, _ = _default_store()
        loaded = load_paired_snapshot(store, paired.run.run_id, as_of=AS_OF)
        recomputed = "sha256:" + _hex_digest(store.runs[paired.run.run_id].run_json)
        assert loaded.run.run_digest.value == recomputed

    def test_window_identity_accepts_boundaries_inside_the_preregistered_window(self) -> None:
        store, paired, _ = _default_store()
        loaded = load_paired_snapshot(
            store, paired.run.run_id, as_of=AS_OF, window_start=AS_OF - timedelta(hours=1)
        )
        assert loaded.run.as_of == AS_OF

    def test_window_identity_spans_the_preregistered_window(self) -> None:
        store, paired, _ = _default_store()
        window_start = datetime.fromtimestamp(
            int(AS_OF.timestamp()) - RANKING_WINDOW_SECONDS + 1, tz=UTC
        )
        loaded = load_paired_snapshot(
            store, paired.run.run_id, as_of=AS_OF, window_start=window_start
        )
        assert loaded.run.as_of == AS_OF

    def test_feature_vectors_with_consistent_digests_pass(self) -> None:
        store, paired, _ = _default_store()
        store.feature_rows["batch_ok"] = _feature_rows(paired, batch_id="batch_ok")
        loaded = load_paired_snapshot(
            store, paired.run.run_id, as_of=AS_OF, feature_batch_id="batch_ok"
        )
        assert loaded.run.status is ShadowRunStatus.RAN


# ---------------------------------------------------------------------------
# Rejection matrix (fail-closed).
# ---------------------------------------------------------------------------


class TestRejections:
    def test_missing_run_row(self) -> None:
        store, _, _ = _default_store()
        with pytest.raises(PersistedEvaluationError, match="missing shadow experiment run row"):
            load_paired_snapshot(store, "shadowrun_" + "d" * 64, as_of=AS_OF)

    def test_missing_candidate_artifact(self) -> None:
        store, paired, _ = _default_store()
        del store.artifacts[paired.candidate.artifact.artifact_id]
        with pytest.raises(PersistedEvaluationError, match="missing candidate ranking artifact"):
            load_paired_snapshot(store, paired.run.run_id, as_of=AS_OF)

    def test_wrong_candidate_id(self) -> None:
        store, paired, _ = _default_store()
        forged_id = _rebind_run(
            store, paired, lambda payload: payload.update(candidate_id="prospective-other-v0")
        )
        with pytest.raises(PersistedEvaluationError, match="candidate id mismatch"):
            load_paired_snapshot(store, forged_id, as_of=AS_OF)

    def test_wrong_control_snapshot_binding(self) -> None:
        store, paired, _ = _default_store()
        snapshot_row = store.snapshots[paired.snapshot.snapshot_id]
        store.snapshots[paired.snapshot.snapshot_id] = replace(
            snapshot_row, receipt_id=paired.candidate.receipt.receipt_id
        )
        with pytest.raises(PersistedEvaluationError, match="control snapshot binding mismatch"):
            load_paired_snapshot(store, paired.run.run_id, as_of=AS_OF)

    def test_missing_control_snapshot(self) -> None:
        store, paired, _ = _default_store()
        del store.snapshots[paired.snapshot.snapshot_id]
        with pytest.raises(PersistedEvaluationError, match="missing control baseline snapshot"):
            load_paired_snapshot(store, paired.run.run_id, as_of=AS_OF)

    def test_wrong_as_of(self) -> None:
        store, paired, _ = _default_store()
        with pytest.raises(PersistedEvaluationError, match="as_of mismatch"):
            load_paired_snapshot(store, paired.run.run_id, as_of=AS_OF + timedelta(seconds=300))

    def test_wrong_source_registry(self) -> None:
        store, paired, _ = _default_store()

        def mutate(payload: dict[str, object]) -> None:
            payload["source_registry_version"] = str(Digest("sha256:" + "e" * 64))

        forged_run_id = _retamper_candidate(store, paired, mutate)
        with pytest.raises(PersistedEvaluationError, match="source registry"):
            load_paired_snapshot(store, forged_run_id, as_of=AS_OF)

    def test_unresolvable_freeze_receipt(self) -> None:
        store, paired, _ = _default_store()
        assert paired.run.candidate_freeze_receipt_id is not None
        del store.freeze_receipts[paired.run.candidate_freeze_receipt_id]
        with pytest.raises(PersistedEvaluationError, match="unresolvable"):
            load_paired_snapshot(store, paired.run.run_id, as_of=AS_OF)

    def test_wrong_freeze_receipt_digest_column(self) -> None:
        store, paired, _ = _default_store()
        assert paired.run.candidate_freeze_receipt_id is not None
        receipt_id = paired.run.candidate_freeze_receipt_id
        store.freeze_receipts[receipt_id] = replace(
            store.freeze_receipts[receipt_id], receipt_digest="sha256:" + "f" * 64
        )
        with pytest.raises(PersistedEvaluationError, match="digest column does not bind"):
            load_paired_snapshot(store, paired.run.run_id, as_of=AS_OF)

    def test_tampered_freeze_receipt_payload(self) -> None:
        store, paired, _ = _default_store()
        assert paired.run.candidate_freeze_receipt_id is not None
        receipt_id = paired.run.candidate_freeze_receipt_id
        row = store.freeze_receipts[receipt_id]
        payload = dict(row.receipt_json)
        payload["implementation_commit"] = "c" * 64
        digest, _ = _retamper(payload)
        store.freeze_receipts[receipt_id] = replace(
            row, receipt_digest=digest, receipt_json=payload
        )
        with pytest.raises(PersistedEvaluationError, match="re-derive the run's bound receipt id"):
            load_paired_snapshot(store, paired.run.run_id, as_of=AS_OF)

    def test_drifted_freeze_receipt(self) -> None:
        store, paired, _ = _default_store()
        drifted = _freeze(frozen=False)
        assert drifted.status is not FreezeStatus.FROZEN
        _seed_freeze(store, drifted)
        forged_run_id = _rebind_run(
            store,
            paired,
            lambda payload: payload.update(candidate_freeze_receipt_id=drifted.receipt_id),
        )
        with pytest.raises(PersistedEvaluationError, match="DRIFTED"):
            load_paired_snapshot(store, forged_run_id, as_of=AS_OF)

    def test_non_complete_artifact_row_status(self) -> None:
        store, paired, _ = _default_store()
        artifact_id = paired.candidate.artifact.artifact_id
        store.artifacts[artifact_id] = replace(store.artifacts[artifact_id], status="FAILED")
        with pytest.raises(PersistedEvaluationError, match="COMPLETE"):
            load_paired_snapshot(store, paired.run.run_id, as_of=AS_OF)

    def test_non_complete_artifact_receipt_status(self) -> None:
        store, paired, _ = _default_store()
        receipt_id = paired.candidate.receipt.receipt_id
        store.receipts[receipt_id] = replace(store.receipts[receipt_id], status="FAILED")
        with pytest.raises(PersistedEvaluationError, match="receipt status is not COMPLETE"):
            load_paired_snapshot(store, paired.run.run_id, as_of=AS_OF)

    def test_candidate_control_universe_mismatch(self) -> None:
        store, paired, _ = _default_store()

        def mutate(payload: dict[str, object]) -> None:
            episodes = payload["episodes"]
            assert isinstance(episodes, list)
            episodes[0]["observation_ids"] = ["obs_evil"]

        forged_run_id = _retamper_candidate(store, paired, mutate)
        with pytest.raises(PersistedEvaluationError, match="universe mismatch"):
            load_paired_snapshot(store, forged_run_id, as_of=AS_OF)

    def test_dev_run_on_confirmatory_path(self) -> None:
        store, paired, _ = _default_store()
        store.runs[paired.run.run_id] = replace(
            store.runs[paired.run.run_id], run_class=DEV_RUN_CLASS
        )
        with pytest.raises(PersistedEvaluationError, match="confirmatory"):
            load_paired_snapshot(store, paired.run.run_id, as_of=AS_OF, confirmatory=True)

    def test_unknown_run_class(self) -> None:
        store, paired, _ = _default_store()
        store.runs[paired.run.run_id] = replace(store.runs[paired.run.run_id], run_class="UAT")
        with pytest.raises(PersistedEvaluationError, match="run_class"):
            load_paired_snapshot(store, paired.run.run_id, as_of=AS_OF)

    def test_run_boundary_outside_bound_window(self) -> None:
        store, paired, _ = _default_store()
        with pytest.raises(PersistedEvaluationError, match="evaluation window"):
            load_paired_snapshot(
                store, paired.run.run_id, as_of=AS_OF, window_start=AS_OF + timedelta(seconds=1)
            )

    def test_feature_vector_tampering(self) -> None:
        store, paired, _ = _default_store()
        rows = list(_feature_rows(paired, batch_id="batch_t"))
        rows[0] = replace(rows[0], vector_digest="sha256:" + "8" * 64)
        store.feature_rows["batch_t"] = tuple(rows)
        with pytest.raises(PersistedEvaluationError, match="re-digest its stored digest"):
            load_paired_snapshot(store, paired.run.run_id, as_of=AS_OF, feature_batch_id="batch_t")

    def test_feature_batch_binding_mismatch(self) -> None:
        store, paired, _ = _default_store()
        rows = list(_feature_rows(paired, batch_id="batch_b"))
        rows[0] = replace(rows[0], control_snapshot_id="snapshot_" + "0" * 64)
        store.feature_rows["batch_b"] = tuple(rows)
        with pytest.raises(PersistedEvaluationError, match="control snapshot"):
            load_paired_snapshot(store, paired.run.run_id, as_of=AS_OF, feature_batch_id="batch_b")

    def test_feature_batch_universe_mismatch(self) -> None:
        store, paired, _ = _default_store()
        rows = list(_feature_rows(paired, batch_id="batch_u"))
        rows[0] = replace(rows[0], episode_universe_digest=str(Digest("sha256:" + "7" * 64)))
        store.feature_rows["batch_u"] = tuple(rows)
        with pytest.raises(PersistedEvaluationError, match="universe digest mismatch"):
            load_paired_snapshot(store, paired.run.run_id, as_of=AS_OF, feature_batch_id="batch_u")

    def test_feature_batch_missing(self) -> None:
        store, paired, _ = _default_store()
        with pytest.raises(PersistedEvaluationError, match="missing or empty"):
            load_paired_snapshot(store, paired.run.run_id, as_of=AS_OF, feature_batch_id="nope")


# ---------------------------------------------------------------------------
# Digest recomputation catches tampering.
# ---------------------------------------------------------------------------


class TestTamperDetection:
    def test_tampered_run_json_rank_byte_rejected(self) -> None:
        store, paired, _ = _default_store()
        row = store.runs[paired.run.run_id]
        payload = dict(row.run_json)
        ranking = payload["control_ranking"]
        assert isinstance(ranking, list)
        ranking[0]["rank"] = 99
        store.runs[paired.run.run_id] = replace(row, run_json=payload)
        with pytest.raises(PersistedEvaluationError, match="digest column does not bind"):
            load_paired_snapshot(store, paired.run.run_id, as_of=AS_OF)

    def test_tampered_artifact_json_rank_byte_rejected(self) -> None:
        store, paired, _ = _default_store()
        artifact_row = store.artifacts[paired.candidate.artifact.artifact_id]
        payload = dict(artifact_row.artifact_json)
        episodes = payload["episodes"]
        assert isinstance(episodes, list)
        episodes[0]["rank"] = 999
        store.artifacts[paired.candidate.artifact.artifact_id] = replace(
            artifact_row, artifact_json=payload
        )
        with pytest.raises(PersistedEvaluationError, match="candidate output digest"):
            load_paired_snapshot(store, paired.run.run_id, as_of=AS_OF)

    def test_tampered_snapshot_json_rejected(self) -> None:
        store, paired, _ = _default_store()
        snapshot_row = store.snapshots[paired.snapshot.snapshot_id]
        payload = dict(snapshot_row.snapshot_json)
        episodes = payload["episodes"]
        assert isinstance(episodes, list)
        episodes[0]["rank"] = 42
        store.snapshots[paired.snapshot.snapshot_id] = replace(snapshot_row, snapshot_json=payload)
        with pytest.raises(PersistedEvaluationError, match=r"re-derive|digest column"):
            load_paired_snapshot(store, paired.run.run_id, as_of=AS_OF)


# ---------------------------------------------------------------------------
# Boundary tests A-F (sprint authority).
# ---------------------------------------------------------------------------


class RecordingRepo:
    def __init__(self) -> None:
        self.receipts: list[EvaluationReceipt] = []

    def record_receipt(self, receipt: EvaluationReceipt) -> None:
        self.receipts.append(receipt)


def _evaluate(
    store: FakeStore,
    paired: _Paired,
    *,
    extra: tuple[_Paired, ...] = (),
    confirmatory: bool = False,
    durable_freeze_at: datetime | None = None,
    repo: RecordingRepo | None = None,
):
    refs = [PersistedRunRef(paired.run.run_id, paired.run.as_of)]
    refs += [PersistedRunRef(item.run.run_id, item.run.as_of) for item in extra]
    horizon = max(item.run.as_of for item in (paired, *extra)) + timedelta(hours=1)
    return evaluate_shadow_experiment_from_persisted(
        store=store,
        runs=tuple(refs),
        opportunity_groups=(),
        evaluation_horizon=horizon,
        generated_at=horizon,
        confirmatory=confirmatory,
        canonical_context=confirmatory,
        durable_freeze_at=durable_freeze_at,
        receipt_repository=repo,
    )


class TestBoundaryAuthority:
    def _confirmatory_store(self, *, as_of: datetime) -> tuple[FakeStore, _Paired]:
        freeze = _freeze()
        paired = _paired(as_of, freeze_id=freeze.receipt_id)
        store = FakeStore()
        _seed(store, paired)
        _seed_freeze(store, freeze)
        return store, paired

    def test_a_dev_run_cannot_produce_complete_confirmatory_evaluation(self) -> None:
        # Loader: a DEV run is rejected outright on the confirmatory path.
        store, paired, _ = _default_store()
        store.runs[paired.run.run_id] = replace(
            store.runs[paired.run.run_id], run_class=DEV_RUN_CLASS
        )
        with pytest.raises(PersistedEvaluationError, match="confirmatory"):
            load_paired_snapshot(store, paired.run.run_id, as_of=AS_OF, confirmatory=True)
        # A DEV-run diagnostic evaluation can never be COMPLETE either.
        repo = RecordingRepo()
        receipt = _evaluate(store, paired, repo=repo)
        assert repo.receipts
        assert receipt.status is not EvaluationStatus.COMPLETE
        assert receipt.confirmatory_evidence is False

    def test_a_confirmatory_evaluation_requires_canonical_context(self) -> None:
        store, paired = self._confirmatory_store(as_of=AS_OF)
        with pytest.raises(ValueError, match="canonical DB context"):
            evaluate_shadow_experiment_from_persisted(
                store=store,
                runs=(PersistedRunRef(paired.run.run_id, paired.run.as_of),),
                opportunity_groups=(),
                evaluation_horizon=paired.run.as_of + timedelta(hours=1),
                generated_at=paired.run.as_of + timedelta(hours=1),
                confirmatory=True,
                canonical_context=False,
                durable_freeze_at=DURABLE_AT,
            )

    def test_b_run_bound_to_another_freeze_invalidates_to_drift(self) -> None:
        freeze_one = _freeze()
        freeze_two = _freeze_with_prereg(Digest("sha256:" + "5" * 64))
        assert freeze_two.receipt_id != freeze_one.receipt_id
        run_one = _paired(AS_OF, freeze_id=freeze_one.receipt_id)
        run_two = _paired(AS_OF + timedelta(seconds=300), freeze_id=freeze_two.receipt_id)
        store = FakeStore()
        _seed(store, run_one)
        _seed_freeze(store, freeze_one)
        _seed(store, run_two)
        _seed_freeze(store, freeze_two)
        loaded_one = load_paired_snapshot(
            store, run_one.run.run_id, as_of=run_one.run.as_of, confirmatory=True
        )
        loaded_two = load_paired_snapshot(
            store, run_two.run.run_id, as_of=run_two.run.as_of, confirmatory=True
        )
        failure = _confirmatory_run_binding_failure(
            (loaded_one.run, loaded_two.run),
            loaded_one.freeze_receipt,
            durable_freeze_at=DURABLE_AT,
        )
        assert failure is not None
        assert "does not bind the evaluated candidate freeze receipt" in failure
        # Through the persisted evaluator this surfaces as an INVALID_DRIFT
        # receipt when the sample is adequate; with an empty opportunity set
        # the epistemic gate stays explicit and confirmatory_evidence is False.
        receipt = _evaluate(
            store,
            run_one,
            extra=(run_two,),
            confirmatory=True,
            durable_freeze_at=DURABLE_AT,
        )
        assert receipt.confirmatory_evidence is False

    def test_c_as_of_before_durable_freeze_is_ineligible(self) -> None:
        store, paired = self._confirmatory_store(as_of=DURABLE_AT - timedelta(seconds=300))
        loaded = load_paired_snapshot(
            store, paired.run.run_id, as_of=paired.run.as_of, confirmatory=True
        )
        failure = _confirmatory_run_binding_failure(
            (loaded.run,), loaded.freeze_receipt, durable_freeze_at=DURABLE_AT
        )
        assert failure is not None
        assert "not strictly after durable candidate freeze" in failure
        receipt = _evaluate(store, paired, confirmatory=True, durable_freeze_at=DURABLE_AT)
        assert receipt.confirmatory_evidence is False
        assert receipt.status is not EvaluationStatus.COMPLETE

    def test_d_as_of_equal_to_durable_freeze_is_ineligible_strict_greater_than(self) -> None:
        store, paired = self._confirmatory_store(as_of=DURABLE_AT)
        loaded = load_paired_snapshot(store, paired.run.run_id, as_of=DURABLE_AT, confirmatory=True)
        failure = _confirmatory_run_binding_failure(
            (loaded.run,), loaded.freeze_receipt, durable_freeze_at=DURABLE_AT
        )
        assert failure is not None
        assert "not strictly after durable candidate freeze" in failure
        receipt = _evaluate(store, paired, confirmatory=True, durable_freeze_at=DURABLE_AT)
        assert receipt.confirmatory_evidence is False
        assert receipt.status is not EvaluationStatus.COMPLETE

    def test_e_post_durable_binding_with_exact_freeze_is_eligible(self) -> None:
        store, paired = self._confirmatory_store(as_of=AS_OF)
        loaded = load_paired_snapshot(store, paired.run.run_id, as_of=AS_OF, confirmatory=True)
        assert (
            _confirmatory_run_binding_failure(
                (loaded.run,), loaded.freeze_receipt, durable_freeze_at=DURABLE_AT
            )
            is None
        )
        receipt = _evaluate(store, paired, confirmatory=True, durable_freeze_at=DURABLE_AT)
        assert receipt.status is not EvaluationStatus.INVALID_DRIFT

    def test_f_canonical_durability_is_not_retroactive(self) -> None:
        freeze = _freeze()
        paired = _paired(AS_OF, freeze_id=freeze.receipt_id)
        store = FakeStore()
        _seed(store, paired)
        # Before durability: no main-merge evidence at all.
        _seed_freeze(store, freeze, durable=None)
        loaded = load_paired_snapshot(store, paired.run.run_id, as_of=AS_OF, confirmatory=True)
        missing = _confirmatory_run_binding_failure(
            (loaded.run,), loaded.freeze_receipt, durable_freeze_at=None
        )
        assert missing is not None
        assert "main-merge timestamp is required" in missing
        # Stamping durability LATER never retroactively makes the earlier
        # boundary confirmatory (strict > durability).
        late_durable_at = paired.run.as_of + timedelta(seconds=300)
        _seed_freeze(store, freeze, durable=late_durable_at)
        stamped = _confirmatory_run_binding_failure(
            (loaded.run,), loaded.freeze_receipt, durable_freeze_at=late_durable_at
        )
        assert stamped is not None
        assert "not strictly after durable candidate freeze" in stamped


# ---------------------------------------------------------------------------
# Persisted evaluator wiring (idempotency).
# ---------------------------------------------------------------------------


class TestPersistedEvaluator:
    def test_evaluation_receipt_is_persisted_and_idempotent(self) -> None:
        store, paired, _ = _default_store()
        repo = RecordingRepo()
        first = _evaluate(store, paired, repo=repo)
        second = _evaluate(store, paired, repo=repo)
        assert first.evaluation_id == second.evaluation_id
        assert len(repo.receipts) == 2
        assert repo.receipts[0] == repo.receipts[1]
        assert first.status is EvaluationStatus.INSUFFICIENT_SAMPLE

    def test_duplicate_run_refs_rejected(self) -> None:
        store, paired, _ = _default_store()
        with pytest.raises(ValueError, match="duplicate persisted run ids"):
            evaluate_shadow_experiment_from_persisted(
                store=store,
                runs=(
                    PersistedRunRef(paired.run.run_id, paired.run.as_of),
                    PersistedRunRef(paired.run.run_id, paired.run.as_of),
                ),
                opportunity_groups=(),
                evaluation_horizon=paired.run.as_of + timedelta(hours=1),
                generated_at=paired.run.as_of + timedelta(hours=1),
            )

    def test_empty_run_request_rejected(self) -> None:
        store, _, _ = _default_store()
        with pytest.raises(ValueError, match="at least one persisted run"):
            evaluate_shadow_experiment_from_persisted(
                store=store,
                runs=(),
                opportunity_groups=(),
                evaluation_horizon=AS_OF + timedelta(hours=1),
                generated_at=AS_OF + timedelta(hours=1),
            )
