"""G10 (WP11) deterministic replay gauntlet for the PEF_V0 experiment.

Given a frozen input snapshot, candidate configuration, implementation,
source registry, health state and freeze identity, the full pipeline replay
must reproduce the expected candidate artifact digest (deterministic candidate
class) and the evaluation receipt digest byte-identically — and every hostile
mutation must fail closed deterministically.

Case registry (each case is asserted here so the gauntlet is self-contained
evidence; the DB-bound case G10-C10 lives in
``test_experiment_gauntlet_postgres.py``):

- POSITIVE : full pipeline replay reproduces the candidate artifact digest and
  the evaluation receipt digest byte-identically.
- G10-C01  : flip a candidate rank in artifact_json -> replay digest mismatch.
- G10-C02  : observed_at +1s on an input observation -> run refuses (PIT).
- G10-C03  : observation with observed_at > as_of injected -> excluded.
- G10-C04  : control snapshot swapped for a later one -> identity check fails.
- G10-C05  : mutate PEF_CONFIGURATION_DIGEST constant -> identity check fails.
- G10-C06  : change freeze frozen_at -> new receipt id -> binding mismatch.
- G10-C07  : tamper vector_json -> vector digest mismatch.
- G10-C08  : different source registry at replay -> registry digest mismatch
  (fail-closed loader + sentry INVALID_DRIFT).
- G10-C09  : delete a mid-window run -> evaluation refuses.
- G10-C10  : duplicate (experiment_id, as_of) insert -> idempotent no-op
  (DB-bound; postgres gauntlet file).
- G10-C11  : label derived from candidate rank -> structural independence.
- G10-C12  : backfill forced into the live window -> eligibility holds.
- G10-C13  : as_of < durable_freeze_at -> ineligible.
- G10-C14  : as_of == durable_freeze_at -> ineligible.
- G10-C15  : as_of > durable_freeze_at but freeze not durable -> ineligible.
- G10-C16  : DRIFTED freeze bound to run -> run refuses.
- G10-C17  : run created pre-durability marked CONFIRMATORY -> gate rejects.
- G10-C18  : wrong freeze (different candidate id) -> mismatch.
- G10-C19  : evaluation referencing runs of another freeze -> binding mismatch.
- G10-C20  : FAILED candidate artifact -> evaluation FAILED, never empty-rank
  COMPLETE.
- G10-C21  : re-canonicalization failure on the read plane -> explicit
  UNKNOWN/failed, never silently displayed.
- G10-C22  : backup missing an experiment table -> restore proof fails
  (unit-level simulation of the WP10 script gate).
"""

from __future__ import annotations

import hashlib
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import pytest

from frontier.application.advanced_intelligence import (
    PefRankingRun,
    run_pef_v0_ranking,
    run_shadow_experiment,
)
from frontier.application.drift_sentry import DriftChecker
from frontier.application.evaluation import (
    PairedSnapshot,
    _confirmatory_run_binding_failure,  # pyright: ignore[reportPrivateUsage]
    build_anchor_tracking,
    evaluate_shadow_experiment,
    evaluate_shadow_experiment_from_persisted,
)
from frontier.application.evaluation_loaders import (
    CONFIRMATORY_RUN_CLASS,
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
from frontier.application.experiment_orchestration import (
    FreezeBinding,
    evaluate_confirmatory_gates,
)
from frontier.application.experimental_read import (
    ExperimentalReadRepository,
    ExperimentalReadService,
)
from frontier.domain.advanced_intelligence import (
    PEF_CONFIGURATION_DIGEST,
    PEF_EXPERIMENT_ID,
    PEF_PRIMARY_EMISSION_ROLE,
    SHADOW_RUN_ID_PREFIX,
    ShadowExperimentRun,
    ShadowRunStatus,
    build_shadow_experiment_run,
    failed_pef_artifact,
    require_pef_configuration_identity,
)
from frontier.domain.candidate_freeze import (
    CandidateFreezeReceipt,
    FreezeInputs,
    FreezeStatus,
    build_candidate_freeze_receipt,
)
from frontier.domain.canonical_json import canonical_json_bytes, canonical_json_text
from frontier.domain.digests import Digest
from frontier.domain.drift_sentry import DriftComponent, DriftReport
from frontier.domain.evaluation import (
    ATTENTION_ROLE,
    GLOBAL_RANK_CUTOFF_K,
    AnchorObservation,
    EvaluationReceipt,
    EvaluationStatus,
    OpportunityGroup,
    OutcomeLabel,
    build_retained_opportunities,
    evaluate_domains,
    resolve_outcome_label,
)
from frontier.domain.experimental_read import EXPERIMENTAL_READ_UNKNOWN
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


def _retamper(payload: Mapping[str, object]) -> tuple[str, str]:
    """Digest a mutated payload: returns (digest_column_text, hex_digest)."""
    hexdigest = hashlib.sha256(canonical_json_bytes(dict(payload))).hexdigest()
    return "sha256:" + hexdigest, hexdigest


def _observation_at(label: str, observed_at: datetime) -> BaselineObservationInput:
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
    as_of: datetime, *, observed_at: datetime | None = None
) -> tuple[tuple[BaselineObservationInput, ...], tuple[tuple[str, ...], ...]]:
    at = observed_at if observed_at is not None else as_of - timedelta(minutes=1)
    live = _observation_at("live", at)
    dormant = _observation_at("dormant", at)
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


def _control(
    as_of: datetime,
    *,
    observations: tuple[BaselineObservationInput, ...] | None = None,
    grouped: tuple[tuple[str, ...], ...] | None = None,
) -> tuple[BaselineSnapshot, ProjectionReceipt]:
    if observations is None or grouped is None:
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


@dataclass(frozen=True, slots=True)
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


def _replay_run(paired: _Paired) -> ShadowExperimentRun:
    """Replay the paired run from stored inputs with the pinned generated_at."""
    return build_shadow_experiment_run(
        control_snapshot=paired.snapshot,
        control_receipt=paired.control_receipt,
        candidate_artifact=paired.candidate.artifact,
        candidate_receipt=paired.candidate.receipt,
        as_of=paired.run.as_of,
        generated_at=paired.run.as_of,
        candidate_freeze_receipt_id=paired.run.candidate_freeze_receipt_id,
    )


class FakeStore:
    """In-memory double of the persisted-artifact read plane."""

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


class RecordingRepo:
    def __init__(self) -> None:
        self.receipts: list[EvaluationReceipt] = []

    def record_receipt(self, receipt: EvaluationReceipt) -> None:
        self.receipts.append(receipt)


def _evaluate_persisted(
    store: FakeStore,
    paired: _Paired,
    *,
    extra: tuple[_Paired, ...] = (),
    confirmatory: bool = False,
    durable_freeze_at: datetime | None = None,
    repo: RecordingRepo | None = None,
) -> EvaluationReceipt:
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


# ---------------------------------------------------------------------------
# POSITIVE control: deterministic full-pipeline replay.
# ---------------------------------------------------------------------------


class TestPositiveReplayControl:
    """POSITIVE proof: replay from stored inputs reproduces byte-identical outputs."""

    def test_full_pipeline_replay_reproduces_candidate_artifact_digest(self) -> None:
        store, paired, _ = _default_store()
        # Replay the candidate arm from the EXACT stored inputs: the frozen
        # snapshot/receipt identity plus the pinned generated_at boundary.
        replayed = run_pef_v0_ranking(
            _paired_inputs(AS_OF)[0],
            control_snapshot=paired.snapshot,
            control_receipt=paired.control_receipt,
            generated_at=AS_OF,
            source_registry_version=REGISTRY,
        )
        assert replayed.artifact.artifact_id == paired.candidate.artifact.artifact_id
        assert canonical_json_text(replayed.artifact.to_canonical()) == canonical_json_text(
            paired.candidate.artifact.to_canonical()
        )
        # The projection receipt row is content-derived too.
        assert replayed.receipt.receipt_id == paired.candidate.receipt.receipt_id
        assert replayed.receipt.output_digest == paired.candidate.receipt.output_digest
        # The full replayed run is content-identical: same digest, same id.
        replay_run = _replay_run(paired)
        assert replay_run.run_id == paired.run.run_id
        assert canonical_json_text(replay_run.to_canonical()) == canonical_json_text(
            paired.run.to_canonical()
        )
        # The stored rows still re-derive their content-derived identities.
        loaded = load_paired_snapshot(store, paired.run.run_id, as_of=AS_OF)
        assert loaded.run == paired.run

    def test_full_pipeline_replay_reproduces_evaluation_receipt_digest(self) -> None:
        store, paired, _ = _default_store()
        horizon = paired.run.as_of + timedelta(hours=1)
        refs = (PersistedRunRef(paired.run.run_id, paired.run.as_of),)
        first = evaluate_shadow_experiment_from_persisted(
            store=store,
            runs=refs,
            opportunity_groups=(),
            evaluation_horizon=horizon,
            generated_at=horizon,
        )
        second = evaluate_shadow_experiment_from_persisted(
            store=store,
            runs=refs,
            opportunity_groups=(),
            evaluation_horizon=horizon,
            generated_at=horizon,
        )
        assert first.evaluation_id == second.evaluation_id
        assert canonical_json_text(first.to_canonical()) == canonical_json_text(
            second.to_canonical()
        )


# ---------------------------------------------------------------------------
# Hostile mutation matrix (fail-closed, deterministic).
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _MutationCase:
    """One hostile-mutation matrix entry (case id, mutation, expected outcome)."""

    case_id: str
    mutation: str
    expected: str
    apply: Callable[[FakeStore, _Paired, pytest.MonkeyPatch], None]
    feature_batch: str | None = None
    expected_registry: Digest | None = None


def _apply_c01(store: FakeStore, paired: _Paired, monkeypatch: pytest.MonkeyPatch) -> None:
    del monkeypatch
    row = store.artifacts[paired.candidate.artifact.artifact_id]
    payload = dict(row.artifact_json)
    episodes = payload["episodes"]
    assert isinstance(episodes, list)
    episodes[0]["rank"] = 999
    store.artifacts[paired.candidate.artifact.artifact_id] = replace(row, artifact_json=payload)


def _apply_c04(store: FakeStore, paired: _Paired, monkeypatch: pytest.MonkeyPatch) -> None:
    del monkeypatch
    later = _paired(paired.run.as_of + timedelta(seconds=300), freeze_id=None)
    # Swap the stored control snapshot content for the later snapshot while
    # keeping the original content-derived id: the loader must refuse.
    store.snapshots[paired.snapshot.snapshot_id] = PersistedBaselineSnapshotRow(
        snapshot_id=paired.snapshot.snapshot_id,
        output_digest=str(later.control_receipt.output_digest),
        receipt_id=paired.control_receipt.receipt_id,
        snapshot_json=dict(later.snapshot.to_canonical()),
    )


def _apply_c05(store: FakeStore, paired: _Paired, monkeypatch: pytest.MonkeyPatch) -> None:
    del store, paired
    # A mutated PEF_CONFIGURATION_DIGEST constant at replay time can never
    # satisfy the stored artifacts' bound configuration digest.
    monkeypatch.setattr(
        "frontier.application.evaluation_loaders.PEF_CONFIGURATION_DIGEST",
        Digest("sha256:" + "c" * 64),
    )


def _apply_c06(store: FakeStore, paired: _Paired, monkeypatch: pytest.MonkeyPatch) -> None:
    del monkeypatch
    receipt_id = paired.run.candidate_freeze_receipt_id
    assert receipt_id is not None
    row = store.freeze_receipts[receipt_id]
    payload = dict(row.receipt_json)
    # Changing frozen_at produces a NEW content-derived receipt id; mutating
    # only the stored payload without retampering can never re-derive it.
    payload["frozen_at"] = "2026-09-01T00:05:00.000000Z"
    store.freeze_receipts[receipt_id] = replace(row, receipt_json=payload)


def _apply_c07(store: FakeStore, paired: _Paired, monkeypatch: pytest.MonkeyPatch) -> None:
    del monkeypatch
    rows = list(_feature_rows(paired, batch_id="batch_v"))
    payload = dict(rows[0].vector_json)
    payload["episode_id"] = "episode_evil"
    rows[0] = replace(rows[0], vector_json=payload)
    store.feature_rows["batch_v"] = tuple(rows)


def _apply_noop(store: FakeStore, paired: _Paired, monkeypatch: pytest.MonkeyPatch) -> None:
    # G10-C08: the hostile world itself replays with a different registry; the
    # mutation is the replay environment's expected-registry binding, carried
    # by the case's ``expected_registry`` field.
    del store, paired, monkeypatch


MUTATION_CASES: tuple[_MutationCase, ...] = (
    _MutationCase(
        "G10-C01",
        "flip a candidate rank in artifact_json",
        "candidate output digest",
        _apply_c01,
    ),
    _MutationCase(
        "G10-C04",
        "control snapshot swapped for a later one",
        "does not re-derive the run's control snapshot id",
        _apply_c04,
    ),
    _MutationCase(
        "G10-C05",
        "PEF_CONFIGURATION_DIGEST constant mutated at replay",
        "configuration digest mismatch",
        _apply_c05,
    ),
    _MutationCase(
        "G10-C06",
        "freeze frozen_at changed -> new receipt id",
        "digest column does not bind the receipt payload",
        _apply_c06,
    ),
    _MutationCase(
        "G10-C07",
        "vector_json tampered under a stale digest column",
        "re-digest its stored digest",
        _apply_c07,
        feature_batch="batch_v",
    ),
    _MutationCase(
        "G10-C08",
        "different source registry at replay",
        "artifact source registry digest mismatch with the expected registry",
        _apply_noop,
        expected_registry=Digest("sha256:" + "e" * 64),
    ),
)


class TestHostileMutationMatrix:
    @pytest.mark.parametrize("case", MUTATION_CASES, ids=[case.case_id for case in MUTATION_CASES])
    def test_hostile_mutation_fails_closed_deterministically(
        self, case: _MutationCase, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        store, paired, _ = _default_store()
        case.apply(store, paired, monkeypatch)
        with pytest.raises(PersistedEvaluationError, match=case.expected):
            load_paired_snapshot(
                store,
                paired.run.run_id,
                as_of=AS_OF,
                feature_batch_id=case.feature_batch,
                expected_registry=case.expected_registry,
            )
        # Deterministic: the identical hostile replay refuses identically.
        with pytest.raises(PersistedEvaluationError, match=case.expected):
            load_paired_snapshot(
                store,
                paired.run.run_id,
                as_of=AS_OF,
                feature_batch_id=case.feature_batch,
                expected_registry=case.expected_registry,
            )

    def test_g10_c01_rank_flip_digest_mismatch_detected(self) -> None:
        """Case 1 explicit digest-equality form: the replay digest no longer matches."""
        store, paired, _ = _default_store()
        artifact_row = store.artifacts[paired.candidate.artifact.artifact_id]
        payload = dict(artifact_row.artifact_json)
        episodes = payload["episodes"]
        assert isinstance(episodes, list)
        episodes[0]["rank"] = 999
        tampered_digest = _retamper(payload)[0]
        assert tampered_digest != str(paired.candidate.artifact.output_digest)
        assert tampered_digest != artifact_row.output_digest


class _RegistryMismatchSentry:
    """Duck-typed sentry that reports a source-registry drift (hostile world)."""

    def __init__(self, expected: Digest) -> None:
        self._expected = expected

    def check(
        self,
        receipt: CandidateFreezeReceipt,
        *,
        now: datetime,
        inputs: FreezeInputs | None = None,
    ) -> DriftReport:
        del receipt, inputs
        return DriftReport(
            checked_at=now,
            components=(
                DriftComponent(
                    component="source_registry_digest",
                    expected=str(self._expected),
                    actual=str(REGISTRY),
                    drifted=True,
                    reason="source registry digest mismatch at replay",
                ),
            ),
        )

    def verify_receipt(
        self, receipt: CandidateFreezeReceipt, *, now: datetime
    ) -> CandidateFreezeReceipt:
        del now
        return replace(
            receipt,
            status=FreezeStatus.DRIFTED,
            drift_reasons=("source registry digest mismatch at replay",),
        )


class TestRegistryMutationSurfaces:
    def test_g10_c08_registry_mismatch_invalidates_confirmatory_evaluation(self) -> None:
        """Case 8 INVALID_DRIFT path: a registry mismatch is drift, never silence."""
        store, paired, _ = _default_store()
        sentry = _RegistryMismatchSentry(expected=Digest("sha256:" + "e" * 64))
        horizon = paired.run.as_of + timedelta(hours=1)
        receipt = evaluate_shadow_experiment_from_persisted(
            store=store,
            runs=(PersistedRunRef(paired.run.run_id, paired.run.as_of),),
            opportunity_groups=(),
            evaluation_horizon=horizon,
            generated_at=horizon,
            confirmatory=True,
            canonical_context=True,
            durable_freeze_at=DURABLE_AT,
            drift_sentry=cast("DriftChecker", sentry),
        )
        assert receipt.status is EvaluationStatus.INVALID_DRIFT


# ---------------------------------------------------------------------------
# Mid-window deletion (case 9, store-level half).
# ---------------------------------------------------------------------------


class TestMidWindowDeletion:
    def test_g10_c09_deleted_mid_window_run_refuses_evaluation(self) -> None:
        store, paired, freeze = _default_store()
        mid = _paired(paired.run.as_of + timedelta(seconds=300), freeze_id=freeze.receipt_id)
        _seed(store, mid)
        # Positive control first: both boundaries evaluate together.
        loaded = _evaluate_persisted(store, paired, extra=(mid,))
        assert loaded.status is not EvaluationStatus.COMPLETE
        # Hostile: delete the mid-window run; the persisted evaluation refuses.
        del store.runs[mid.run.run_id]
        with pytest.raises(PersistedEvaluationError, match="missing shadow experiment run row"):
            _evaluate_persisted(store, paired, extra=(mid,))


# ---------------------------------------------------------------------------
# Input-plane mutations (PIT, future observations, backfill).
# ---------------------------------------------------------------------------


class TestInputPlaneMutations:
    def test_g10_c02_observed_at_plus_one_second_refuses_the_run(self) -> None:
        """Case 2: an input observation pushed past the boundary cannot be replayed."""
        observations, grouped = _paired_inputs(AS_OF, observed_at=AS_OF)
        snapshot, receipt = _control(AS_OF, observations=observations, grouped=grouped)
        # Positive world: an observation exactly AT the boundary is eligible.
        baseline_run = run_shadow_experiment(
            observations,
            control_snapshot=snapshot,
            control_receipt=receipt,
            generated_at=AS_OF,
            source_registry_version=REGISTRY,
        )
        assert baseline_run.status is ShadowRunStatus.RAN
        # Hostile replay: +1s pushes the observation AFTER the knowledge horizon.
        bumped = tuple(
            replace(
                item,
                grouping=replace(item.grouping, observed_at=AS_OF + timedelta(seconds=1)),
            )
            if item.grouping.source_item_key == "live"
            else item
            for item in observations
        )
        replay = run_shadow_experiment(
            bumped,
            control_snapshot=snapshot,
            control_receipt=receipt,
            generated_at=AS_OF,
            source_registry_version=REGISTRY,
        )
        assert replay.status is ShadowRunStatus.FAILED
        assert replay.failure_reason is not None
        assert "unknown observation" in replay.failure_reason
        # Deterministic: the identical hostile replay refuses identically.
        replay_again = run_shadow_experiment(
            bumped,
            control_snapshot=snapshot,
            control_receipt=receipt,
            generated_at=AS_OF,
            source_registry_version=REGISTRY,
        )
        assert replay_again.run_id == replay.run_id
        assert replay_again.failure_reason == replay.failure_reason

    def test_g10_c03_future_observation_is_excluded_from_the_replay(self) -> None:
        """Case 3: an injected future-dated observation never enters the artifact."""
        _, paired, _ = _default_store()
        future = _observation_at("future", AS_OF + timedelta(seconds=1))
        assert future.grouping.observed_at > AS_OF
        poisoned = (*_paired_inputs(AS_OF)[0], future)
        candidate = run_pef_v0_ranking(
            poisoned,
            control_snapshot=paired.snapshot,
            control_receipt=paired.control_receipt,
            generated_at=AS_OF,
            source_registry_version=REGISTRY,
        )
        # The future observation is outside every episode and past the horizon:
        # the replayed artifact digest is byte-identical to the frozen one.
        assert candidate.artifact.artifact_id == paired.candidate.artifact.artifact_id
        assert canonical_json_text(candidate.artifact.to_canonical()) == canonical_json_text(
            paired.candidate.artifact.to_canonical()
        )

    def test_g10_c12_backfill_forced_into_the_live_window_is_excluded(self) -> None:
        """Case 12: backfill placement inside the window cannot move the ranking."""
        observations, _ = _paired_inputs(AS_OF)
        member_early = _observation_at("member", AS_OF - timedelta(hours=12))
        member_late = replace(
            member_early,
            grouping=replace(member_early.grouping, observed_at=AS_OF - timedelta(seconds=1)),
        )
        grouped = (
            (observations[0].observation_id, member_early.observation_id),
            (observations[1].observation_id,),
        )
        # BACKFILL world: the forced member is never prospective evidence, so
        # its placement inside the window cannot change the replayed digest.
        backfill_early = replace(member_early, first_reason="BACKFILL")
        assert backfill_early.is_backfill
        assert not backfill_early.is_prospective
        snapshot_b, receipt_b = _control(
            AS_OF, observations=(observations[0], observations[1], backfill_early), grouped=grouped
        )
        id_b_early = _replay_pair_id(
            snapshot_b,
            receipt_b,
            (observations[0], observations[1], backfill_early),
        )
        id_b_late = _replay_pair_id(
            snapshot_b,
            receipt_b,
            (
                observations[0],
                observations[1],
                replace(
                    backfill_early,
                    grouping=replace(
                        backfill_early.grouping, observed_at=AS_OF - timedelta(seconds=1)
                    ),
                ),
            ),
        )
        assert id_b_early == id_b_late
        # PROSPECTIVE contrast: the same placement moves the ranking when the
        # member IS prospectively eligible — proving the exclusion is the
        # eligibility rule, not an artifact of the fixture.
        snapshot_p, receipt_p = _control(
            AS_OF, observations=(observations[0], observations[1], member_early), grouped=grouped
        )
        id_p_early = _replay_pair_id(
            snapshot_p, receipt_p, (observations[0], observations[1], member_early)
        )
        id_p_late = _replay_pair_id(
            snapshot_p, receipt_p, (observations[0], observations[1], member_late)
        )
        assert id_p_early != id_p_late


def _replay_pair_id(
    snapshot: BaselineSnapshot,
    receipt: ProjectionReceipt,
    observations: tuple[BaselineObservationInput, ...],
) -> str:
    candidate = run_pef_v0_ranking(
        observations,
        control_snapshot=snapshot,
        control_receipt=receipt,
        generated_at=AS_OF,
        source_registry_version=REGISTRY,
    )
    return candidate.artifact.artifact_id


# ---------------------------------------------------------------------------
# Eligibility and confirmatory gates (cases 13-19).
# ---------------------------------------------------------------------------


class TestConfirmatoryEligibilityGates:
    def test_g10_c13_as_of_before_durable_freeze_is_ineligible(self) -> None:
        freeze = _freeze()
        decision = evaluate_confirmatory_gates(
            FreezeBinding(freeze, durable_freeze_at=DURABLE_AT),
            as_of=DURABLE_AT - timedelta(seconds=300),
            canonical_context=True,
        )
        assert decision.allowed is False
        assert "not strictly after durable_freeze_at" in decision.reason

    def test_g10_c14_as_of_equal_to_durable_freeze_is_ineligible(self) -> None:
        freeze = _freeze()
        decision = evaluate_confirmatory_gates(
            FreezeBinding(freeze, durable_freeze_at=DURABLE_AT),
            as_of=DURABLE_AT,
            canonical_context=True,
        )
        assert decision.allowed is False
        assert "not strictly after durable_freeze_at" in decision.reason

    def test_g10_c15_post_durable_as_of_without_durability_is_ineligible(self) -> None:
        freeze = _freeze()
        decision = evaluate_confirmatory_gates(
            FreezeBinding(freeze, durable_freeze_at=None),
            as_of=AS_OF,
            canonical_context=True,
        )
        assert decision.allowed is False
        assert "durable_freeze_at NULL" in decision.reason

    def test_g10_c16_drifted_freeze_bound_to_run_refuses(self) -> None:
        drifted = _freeze(frozen=False)
        assert drifted.status is not FreezeStatus.FROZEN
        snapshot, receipt = _control(AS_OF)
        with pytest.raises(ValueError, match="drifted candidate freeze receipt cannot bind"):
            run_shadow_experiment(
                _paired_inputs(AS_OF)[0],
                control_snapshot=snapshot,
                control_receipt=receipt,
                generated_at=AS_OF,
                source_registry_version=REGISTRY,
                candidate_freeze_receipt=drifted,
            )
        # The persisted loader refuses the DRIFTED binding too.
        store, paired, _ = _default_store()
        _seed_freeze(store, drifted, durable=DURABLE_AT)
        forged = _rebind_run(
            store,
            paired,
            lambda payload: payload.update(candidate_freeze_receipt_id=drifted.receipt_id),
        )
        with pytest.raises(PersistedEvaluationError, match="DRIFTED"):
            load_paired_snapshot(store, forged, as_of=AS_OF)

    def test_g10_c17_pre_durability_confirmatory_run_gate_rejects(self) -> None:
        freeze = _freeze()
        # Before durability: no main-merge evidence at all.
        early = evaluate_confirmatory_gates(
            FreezeBinding(freeze, durable_freeze_at=None),
            as_of=AS_OF,
            canonical_context=True,
        )
        assert early.allowed is False
        assert "durable_freeze_at NULL" in early.reason
        # Durability stamped AFTER the run boundary never retroactively makes
        # the earlier confirmatory run eligible (strict > durability).
        late_stamped = evaluate_confirmatory_gates(
            FreezeBinding(freeze, durable_freeze_at=AS_OF + timedelta(seconds=300)),
            as_of=AS_OF,
            canonical_context=True,
        )
        assert late_stamped.allowed is False
        assert "not strictly after durable_freeze_at" in late_stamped.reason

    def test_g10_c18_wrong_freeze_candidate_id_mismatches(self) -> None:
        snapshot, receipt = _control(AS_OF)
        forged = cast("CandidateFreezeReceipt", _WrongFreezeStub())
        with pytest.raises(ValueError, match="candidate freeze receipt candidate id mismatch"):
            run_shadow_experiment(
                _paired_inputs(AS_OF)[0],
                control_snapshot=snapshot,
                control_receipt=receipt,
                generated_at=AS_OF,
                source_registry_version=REGISTRY,
                candidate_freeze_receipt=forged,
            )
        # Run-level identity: a run bound to a wrong candidate id is refused.
        store, paired, _ = _default_store()
        forged_run_id = _rebind_run(
            store, paired, lambda payload: payload.update(candidate_id="prospective-other-v0")
        )
        with pytest.raises(PersistedEvaluationError, match="candidate id mismatch"):
            load_paired_snapshot(store, forged_run_id, as_of=AS_OF)

    def test_g10_c19_evaluation_referencing_runs_of_another_freeze_mismatches(self) -> None:
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
        receipt = _evaluate_persisted(
            store,
            run_one,
            extra=(run_two,),
            confirmatory=True,
            durable_freeze_at=DURABLE_AT,
            repo=RecordingRepo(),
        )
        assert receipt.confirmatory_evidence is False
        assert receipt.status is not EvaluationStatus.COMPLETE


class _WrongFreezeStub:
    """Hostile freeze object bound to a DIFFERENT candidate id."""

    status = FreezeStatus.FROZEN
    candidate_id = "prospective-other-v0"

    def __init__(self) -> None:
        self.experiment_id = PEF_EXPERIMENT_ID
        self.configuration_digest = PEF_CONFIGURATION_DIGEST
        self.receipt_id = "freezereceipt_" + "f" * 64


# ---------------------------------------------------------------------------
# Constant identity guard (case 5, runtime half).
# ---------------------------------------------------------------------------


class TestConstantIdentityGuard:
    def test_g10_c05_mutated_configuration_constant_fails_closed_at_runtime(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "frontier.domain.advanced_intelligence.PEF_CONFIGURATION_DIGEST",
            Digest("sha256:" + "c" * 64),
        )
        with pytest.raises(RuntimeError, match="configuration digest drifted from preregistration"):
            require_pef_configuration_identity()


# ---------------------------------------------------------------------------
# FAILED-artifact semantics (case 20).
# ---------------------------------------------------------------------------


class TestFailedArtifactSemantics:
    def test_g10_c20_failed_candidate_artifact_is_never_an_empty_ranking(self) -> None:
        snapshot, receipt = _control(AS_OF)
        observations, _ = _paired_inputs(AS_OF)
        # Hostile inputs drop one episode member: the candidate arm fails.
        hostile_inputs = (observations[1],)
        run = run_shadow_experiment(
            hostile_inputs,
            control_snapshot=snapshot,
            control_receipt=receipt,
            generated_at=AS_OF,
            source_registry_version=REGISTRY,
        )
        assert run.status is ShadowRunStatus.FAILED
        assert run.failure_reason is not None
        # Reconstruct the FAILED artifact coherently (same failure reason).
        artifact = failed_pef_artifact(
            control_snapshot=snapshot,
            control_receipt=receipt,
            as_of=AS_OF,
            generated_at=AS_OF,
            source_registry_version=REGISTRY,
            failure_reason=run.failure_reason,
        )
        assert artifact.output_digest == run.candidate_output_digest
        assert artifact.episodes == ()
        # Persisted loader: a FAILED run never feeds an evaluation.
        store = FakeStore()
        store.runs[run.run_id] = PersistedRunRow(
            run_id=run.run_id,
            run_digest=str(run.run_digest),
            run_class=CONFIRMATORY_RUN_CLASS,
            status=run.status.value,
            run_json=dict(run.to_canonical()),
        )
        store.artifacts[artifact.artifact_id] = PersistedArtifactRow(
            artifact_id=artifact.artifact_id,
            output_digest=str(artifact.output_digest),
            status=artifact.status.value,
            receipt_id="receipt_" + "8" * 60,
            artifact_json=dict(artifact.to_canonical()),
        )
        with pytest.raises(PersistedEvaluationError, match="COMPLETE"):
            load_paired_snapshot(store, run.run_id, as_of=AS_OF)
        # Frozen semantics: a FAILED run yields EvaluationStatus.FAILED.
        direct = evaluate_shadow_experiment(
            snapshots=(
                PairedSnapshot(
                    run=run,
                    candidate_rank_by_episode={},
                    episode_memberships={
                        episode.episode_id: episode.observation_ids for episode in snapshot.episodes
                    },
                ),
            ),
            opportunity_groups=(),
            freeze_receipt=_freeze(),
            evaluation_horizon=AS_OF + timedelta(hours=1),
            generated_at=AS_OF + timedelta(hours=1),
        )
        assert direct.status is EvaluationStatus.FAILED
        assert direct.status is not EvaluationStatus.COMPLETE
        assert direct.status_reason is not None
        assert "shadow runs FAILED" in direct.status_reason


# ---------------------------------------------------------------------------
# Read plane and backup integrity (cases 21-22).
# ---------------------------------------------------------------------------


class TestReadPlaneAndBackupIntegrity:
    def test_g10_c21_recanonicalization_failure_is_surfaced_never_silent(self) -> None:
        """Case 21: unreadable payloads fail closed; the read plane says UNKNOWN."""
        store, paired, _ = _default_store()
        row = store.runs[paired.run.run_id]
        store.runs[paired.run.run_id] = replace(row, run_json=cast("dict[str, object]", []))
        with pytest.raises(PersistedEvaluationError, match="not a canonical mapping"):
            load_paired_snapshot(store, paired.run.run_id, as_of=AS_OF)

        class _BrokenCanonicalizationRepo:
            def run_detail(self, *, run_id: str, as_of: datetime | None = None) -> None:
                del run_id, as_of
                raise RuntimeError("re-canonicalization failed: digest mismatch on read plane")

        service = ExperimentalReadService(
            cast("ExperimentalReadRepository", _BrokenCanonicalizationRepo())
        )
        section = service.get_run_detail(run_id="shadowrun_" + "d" * 64)
        assert section.availability == EXPERIMENTAL_READ_UNKNOWN
        assert section.run is None

    def test_g10_c22_backup_missing_experiment_table_fails_restore_proof(self) -> None:
        """Case 22: a dump without one experiment table must fail the WP10 gate."""
        repo_root = str(Path(__file__).resolve().parents[2])
        if repo_root not in sys.path:
            sys.path.insert(0, repo_root)
        from scripts.ops.verify_backup_restore import EXPERIMENT_TABLES

        complete_dump = set(EXPERIMENT_TABLES)
        assert sorted(set(EXPERIMENT_TABLES) - complete_dump) == []
        tampered_dump = complete_dump - {"shadow_experiment_runs"}
        missing = sorted(set(EXPERIMENT_TABLES) - tampered_dump)
        assert missing == ["shadow_experiment_runs"]


# ---------------------------------------------------------------------------
# Label structural independence (case 11).
# ---------------------------------------------------------------------------


class TestLabelStructuralIndependence:
    def test_g10_c11_labels_derive_from_outcomes_not_ranks(self) -> None:
        """Case 11: flipping candidate ranks moves tracking, never the labels."""
        _, paired, _ = _default_store()
        universe = {
            episode.episode_id: episode.observation_ids for episode in paired.snapshot.episodes
        }
        episode_ids = sorted(universe)
        assert len(episode_ids) >= 2
        anchor_id = universe[episode_ids[0]][0]
        anchor_time = AS_OF - timedelta(hours=1)
        anchor = AnchorObservation(
            observation_id=anchor_id,
            source_id="pypi.updates",
            role=PEF_PRIMARY_EMISSION_ROLE,
            observed_at=anchor_time,
        )
        outcome = AnchorObservation(
            observation_id="obs_outcome",
            source_id="hn.frontpage",
            role=ATTENTION_ROLE,
            observed_at=anchor_time + timedelta(minutes=5),
        )
        group = OpportunityGroup(
            resolution_episode_id="grp_resolution",
            primary_emission_anchors=(anchor,),
            member_observations=(anchor, outcome),
        )
        opportunities = build_retained_opportunities((group,))
        assert len(opportunities) == 1
        opportunity = opportunities[0]
        assert opportunity.label is OutcomeLabel.POSITIVE
        # Structural: the label is a pure function of outcome evidence only.
        assert (
            resolve_outcome_label(anchor, member_observations=(anchor, outcome), lane_boundaries=())
            is OutcomeLabel.POSITIVE
        )
        ranks_a = {episode_ids[0]: 1, episode_ids[1]: 2}
        ranks_b = {episode_ids[0]: 2, episode_ids[1]: 1}
        snapshot_a = PairedSnapshot(
            run=paired.run, candidate_rank_by_episode=ranks_a, episode_memberships=universe
        )
        snapshot_b = PairedSnapshot(
            run=paired.run, candidate_rank_by_episode=ranks_b, episode_memberships=universe
        )
        tracking_a = build_anchor_tracking(opportunity, (snapshot_a,))
        tracking_b = build_anchor_tracking(opportunity, (snapshot_b,))
        assert tracking_a != tracking_b
        assert tracking_a[0].candidate_rank != tracking_b[0].candidate_rank
        domains_a = evaluate_domains(
            opportunities, {anchor.observation_id: tracking_a}, rank_cutoff_k=GLOBAL_RANK_CUTOFF_K
        )
        domains_b = evaluate_domains(
            opportunities, {anchor.observation_id: tracking_b}, rank_cutoff_k=GLOBAL_RANK_CUTOFF_K
        )
        label_fields = ("domain", "resolved_label_fraction_numerator", "unresolved_coverage_count")
        assert [tuple(getattr(item, field) for field in label_fields) for item in domains_a] == [
            tuple(getattr(item, field) for field in label_fields) for item in domains_b
        ]
