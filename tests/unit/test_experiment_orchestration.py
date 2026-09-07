from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from hashlib import sha256
from uuid import uuid4

import pytest

from frontier.adapters.acquisition.config import RegisteredSource, SourceRegistry
from frontier.application.acquisition import AcquisitionResult
from frontier.application.acquisition_state import SourceFetchState
from frontier.application.advanced_intelligence import run_shadow_experiment
from frontier.application.experiment_orchestration import (
    RUN_CLASS_CONFIRMATORY,
    RUN_CLASS_DEV,
    ConfirmatoryDecision,
    ExperimentAttemptRepository,
    ExperimentCycleAction,
    ExperimentOrchestrator,
    FreezeBinding,
    ShadowRunPersistence,
    derive_experiment_boundary,
    evaluate_confirmatory_gates,
)
from frontier.application.worker import AcquisitionWorker
from frontier.domain.advanced_intelligence import (
    PEF_EXPERIMENT_ID,
    ShadowExperimentRun,
    ShadowRunStatus,
    build_pef_receipt,
    build_shadow_experiment_run,
    failed_pef_artifact,
)
from frontier.domain.candidate_freeze import CandidateFreezeReceipt, FreezeStatus
from frontier.domain.collection import CollectionRunStatus
from frontier.domain.digests import Digest
from frontier.domain.grouping import GroupingInput, GroupingRelationInput
from frontier.domain.health import HealthValue
from frontier.domain.intelligence import (
    BaselineHealthInput,
    BaselineObservationInput,
    BaselineSnapshot,
)
from frontier.domain.opportunity import ExperimentAttemptStatus, ExperimentRunAttempt
from frontier.domain.receipt import ProjectionReceipt
from frontier.domain.source import AcquisitionClass, SignalRole, SourceContract, SourceTransport

BOUNDARY = datetime(2026, 9, 5, 12, 5, tzinfo=UTC)
REGISTRY = Digest("sha256:" + "1" * 64)
WORKER = "orchestrator-test-worker"


def _obs_id(label: str) -> str:
    return "obs_" + sha256(label.encode()).hexdigest()


def _observation(label: str, observed_at: datetime) -> BaselineObservationInput:
    return BaselineObservationInput(
        grouping=GroupingInput(
            observation_id=_obs_id(label),
            source_id="fixture.primary",
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


def _observations() -> tuple[BaselineObservationInput, ...]:
    return (
        _observation("alpha", BOUNDARY - timedelta(seconds=60)),
        _observation("beta", BOUNDARY - timedelta(seconds=30)),
    )


def _health(as_of: datetime) -> BaselineHealthInput:
    return BaselineHealthInput(
        source_id="fixture.primary",
        as_of=as_of,
        transport=HealthValue.OK,
        freshness=HealthValue.OK,
        completeness=HealthValue.OK,
        schema=HealthValue.OK,
    )


class FakeBaselineRepository:
    """In-memory BaselineIntelligenceRepository double."""

    def __init__(
        self,
        observations: tuple[BaselineObservationInput, ...],
        *,
        confirmatory_source_registry_version: Digest | None = None,
    ) -> None:
        self.observations = observations
        self.published: list[tuple[BaselineSnapshot, object]] = []
        self.confirmatory_source_registry_version = confirmatory_source_registry_version

    def list_baseline_observations_as_of(self, as_of: datetime) -> list[BaselineObservationInput]:
        return list(self.observations)

    def list_grouping_relations_as_of(self, as_of: datetime) -> list[GroupingRelationInput]:
        return []

    def list_enabled_source_ids(self) -> list[str]:
        return ["fixture.primary"]

    def list_latest_health_as_of(self, as_of: datetime) -> list[BaselineHealthInput]:
        return [_health(as_of)]

    def publish_complete_snapshot(
        self, snapshot: BaselineSnapshot, receipt: ProjectionReceipt
    ) -> None:
        self.published.append((snapshot, receipt))


class FakeAttemptRepository(ExperimentAttemptRepository):
    def __init__(self) -> None:
        self.attempts: dict[str, ExperimentRunAttempt] = {}

    def all_attempts(self) -> list[ExperimentRunAttempt]:
        return list(self.attempts.values())

    def latest_attempt(self, experiment_id: str, as_of: datetime) -> ExperimentRunAttempt | None:
        candidates = [
            attempt
            for attempt in self.attempts.values()
            if attempt.experiment_id == experiment_id and attempt.as_of == as_of
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda attempt: attempt.attempt_no)

    def record_attempt(self, attempt: ExperimentRunAttempt) -> bool:
        if attempt.attempt_id in self.attempts:
            return False
        self.attempts[attempt.attempt_id] = attempt
        return True

    def set_attempt(self, attempt: ExperimentRunAttempt) -> None:
        self.attempts[attempt.attempt_id] = attempt

    def claim(
        self,
        attempt_id: str,
        *,
        owner: str,
        lease_expires_at: datetime,
        now: datetime,
    ) -> bool:
        attempt = self.attempts.get(attempt_id)
        if attempt is None:
            return False
        adoptable = attempt.status is ExperimentAttemptStatus.PENDING or (
            attempt.status is ExperimentAttemptStatus.RUNNING
            and attempt.lease_owner == owner
            and attempt.lease_expires_at is not None
            and attempt.lease_expires_at > now
        )
        if not adoptable:
            return False
        self.set_attempt(
            ExperimentRunAttempt(
                experiment_id=attempt.experiment_id,
                as_of=attempt.as_of,
                attempt_no=attempt.attempt_no,
                status=ExperimentAttemptStatus.RUNNING,
                detail=attempt.detail,
                lease_owner=owner,
                lease_expires_at=lease_expires_at,
                heartbeat_at=now,
                schema_version=attempt.schema_version,
            )
        )
        return True

    def heartbeat(self, attempt_id: str, *, owner: str, at: datetime) -> bool:
        attempt = self.attempts.get(attempt_id)
        if (
            attempt is None
            or attempt.status is not ExperimentAttemptStatus.RUNNING
            or attempt.lease_owner != owner
            or attempt.lease_expires_at is None
            or attempt.lease_expires_at <= at
        ):
            return False
        self.set_attempt(replace(attempt, heartbeat_at=at))
        return True

    def finish(
        self,
        attempt_id: str,
        *,
        owner: str,
        status: ExperimentAttemptStatus,
        detail: str | None,
        at: datetime,
    ) -> bool:
        attempt = self.attempts.get(attempt_id)
        if (
            attempt is None
            or attempt.status is not ExperimentAttemptStatus.RUNNING
            or attempt.lease_owner != owner
        ):
            return False
        self.set_attempt(
            ExperimentRunAttempt(
                experiment_id=attempt.experiment_id,
                as_of=attempt.as_of,
                attempt_no=attempt.attempt_no,
                status=status,
                detail=detail,
                heartbeat_at=attempt.heartbeat_at,
                schema_version=attempt.schema_version,
            )
        )
        return True

    def expire_stale(
        self, *, now: datetime, detail: str = "lease expired"
    ) -> tuple[ExperimentRunAttempt, ...]:
        expired: list[ExperimentRunAttempt] = []
        for attempt in self.attempts.values():
            if (
                attempt.status is ExperimentAttemptStatus.RUNNING
                and attempt.lease_expires_at is not None
                and attempt.lease_expires_at <= now
            ):
                self.set_attempt(
                    ExperimentRunAttempt(
                        experiment_id=attempt.experiment_id,
                        as_of=attempt.as_of,
                        attempt_no=attempt.attempt_no,
                        status=ExperimentAttemptStatus.EXPIRED,
                        detail=detail,
                        lease_expires_at=attempt.lease_expires_at,
                        heartbeat_at=attempt.heartbeat_at,
                        schema_version=attempt.schema_version,
                    )
                )
                expired.append(self.attempts[attempt.attempt_id])
        return tuple(expired)


class FakeShadowRunPersistence(ShadowRunPersistence):
    def __init__(self) -> None:
        self.persisted: list[tuple[str, str, ShadowRunStatus]] = []
        self.retained: dict[str, tuple[str, str, str]] = {}

    def persist(self, run: ShadowExperimentRun, *, run_class: str) -> str:
        self.persisted.append((run.run_id, run_class, run.status))
        self.retained[run.as_of.isoformat()] = (run.run_id, run_class, run.status.value)
        return run.run_id

    def latest_run_id_and_class_for_as_of(self, as_of: datetime) -> tuple[str, str, str] | None:
        return self.retained.get(as_of.isoformat())


class RecordingRunner:
    """Wraps the real engine and records the freeze receipt it received."""

    def __init__(
        self, delegate: Callable[..., ShadowExperimentRun] = run_shadow_experiment
    ) -> None:
        self._delegate = delegate
        self.calls: list[CandidateFreezeReceipt | None] = []

    def __call__(
        self,
        observations: tuple[BaselineObservationInput, ...],
        *,
        control_snapshot: BaselineSnapshot,
        control_receipt: object,
        generated_at: datetime,
        source_registry_version: Digest,
        candidate_freeze_receipt: CandidateFreezeReceipt | None,
    ) -> ShadowExperimentRun:
        self.calls.append(candidate_freeze_receipt)
        return self._delegate(
            observations,
            control_snapshot=control_snapshot,
            control_receipt=control_receipt,
            generated_at=generated_at,
            source_registry_version=source_registry_version,
            candidate_freeze_receipt=candidate_freeze_receipt,
        )


def _frozen_receipt(*, frozen_at: datetime) -> CandidateFreezeReceipt:
    return CandidateFreezeReceipt(
        frozen_at=frozen_at,
        status=FreezeStatus.FROZEN,
        drift_reasons=(),
        preregistration_digest=Digest("sha256:" + "a" * 64),
        preregistration_config_digest=Digest("sha256:" + "b" * 64),
        implementation_commit="c" * 40,
        implementation_tree_digest="d" * 64,
        dependency_lock_digest=Digest("sha256:" + "e" * 64),
        source_registry_digest=Digest("sha256:" + "f" * 64),
        registry_entry_digests=(),
    )


class StubBindingResolver:
    def __init__(self, binding: FreezeBinding | None) -> None:
        self.binding = binding
        self.calls = 0

    def latest_binding(self) -> FreezeBinding | None:
        self.calls += 1
        return self.binding


def _orchestrator(
    *,
    attempts: FakeAttemptRepository,
    persistence: FakeShadowRunPersistence,
    observations: tuple[BaselineObservationInput, ...] | None = None,
    clock: datetime = BOUNDARY,
    run_class: str = RUN_CLASS_DEV,
    canonical_context: bool = False,
    binding: StubBindingResolver | None = None,
    runner: RecordingRunner | None = None,
) -> tuple[ExperimentOrchestrator, FakeBaselineRepository]:
    baseline = FakeBaselineRepository(
        observations if observations is not None else _observations(),
        confirmatory_source_registry_version=(
            REGISTRY if run_class == RUN_CLASS_CONFIRMATORY else None
        ),
    )
    orchestrator = ExperimentOrchestrator(
        attempts=attempts,
        baseline_repository=baseline,
        persistence=persistence,
        source_registry_version=REGISTRY,
        freeze_binding=binding,
        shadow_runner=runner,
        run_class=run_class,
        canonical_context=canonical_context,
        worker_id=WORKER,
        clock=lambda: clock,
    )
    return orchestrator, baseline


def test_confirmatory_construction_requires_frozen_registry_bound_baseline() -> None:
    broad_baseline = FakeBaselineRepository(_observations())
    with pytest.raises(
        ValueError,
        match="CONFIRMATORY requires a baseline repository bound to the frozen source registry",
    ):
        ExperimentOrchestrator(
            attempts=FakeAttemptRepository(),
            baseline_repository=broad_baseline,
            persistence=FakeShadowRunPersistence(),
            source_registry_version=REGISTRY,
            run_class=RUN_CLASS_CONFIRMATORY,
            canonical_context=True,
        )

    wrong_registry_baseline = FakeBaselineRepository(
        _observations(),
        confirmatory_source_registry_version=Digest("sha256:" + "9" * 64),
    )
    with pytest.raises(
        ValueError,
        match="CONFIRMATORY requires a baseline repository bound to the frozen source registry",
    ):
        ExperimentOrchestrator(
            attempts=FakeAttemptRepository(),
            baseline_repository=wrong_registry_baseline,
            persistence=FakeShadowRunPersistence(),
            source_registry_version=REGISTRY,
            run_class=RUN_CLASS_CONFIRMATORY,
            canonical_context=True,
        )


def test_derive_experiment_boundary_is_epoch_multiple_of_cadence() -> None:
    assert derive_experiment_boundary(datetime(2026, 9, 5, 20, 7, 41, tzinfo=UTC)) == datetime(
        2026, 9, 5, 20, 5, tzinfo=UTC
    )
    exact = BOUNDARY
    assert int(exact.timestamp()) % 300 == 0
    assert derive_experiment_boundary(exact) == exact
    assert derive_experiment_boundary(datetime(2026, 9, 5, 12, 4, 59, tzinfo=UTC)) == datetime(
        2026, 9, 5, 12, 0, tzinfo=UTC
    )
    plus_two = datetime(2026, 9, 5, 14, 7, 30, tzinfo=timezone(timedelta(hours=2)))
    assert derive_experiment_boundary(plus_two) == datetime(2026, 9, 5, 12, 5, tzinfo=UTC)
    with pytest.raises(ValueError):
        derive_experiment_boundary(datetime(2026, 9, 5, 12, 5))
    with pytest.raises(ValueError):
        derive_experiment_boundary(exact, cadence_seconds=0)


def test_first_cycle_runs_lifecycle_and_persists_once() -> None:
    attempts = FakeAttemptRepository()
    persistence = FakeShadowRunPersistence()
    orchestrator, baseline = _orchestrator(attempts=attempts, persistence=persistence)
    result = orchestrator.run_cycle()
    assert result.action is ExperimentCycleAction.RAN
    assert result.run_id is not None
    latest = attempts.latest_attempt(PEF_EXPERIMENT_ID, BOUNDARY)
    assert latest is not None
    assert latest.status is ExperimentAttemptStatus.DONE
    assert latest.detail is not None
    assert latest.detail.startswith(f"run_id={result.run_id}")
    assert len(attempts.all_attempts()) == 1
    assert len(persistence.persisted) == 1
    assert persistence.persisted[0][1] == RUN_CLASS_DEV
    assert persistence.persisted[0][2] is ShadowRunStatus.RAN
    assert len(baseline.published) == 1
    # Re-delivery of the same boundary is suppressed, not re-executed.
    second = orchestrator.run_cycle(now=BOUNDARY)
    assert second.action is ExperimentCycleAction.ALREADY_COMPLETE
    assert len(persistence.persisted) == 1
    assert len(attempts.all_attempts()) == 1


def test_attempt_lifecycle_records_pending_running_done_and_heartbeats() -> None:
    attempts = FakeAttemptRepository()
    persistence = FakeShadowRunPersistence()
    orchestrator, _ = _orchestrator(attempts=attempts, persistence=persistence)
    orchestrator.run_cycle()
    latest = attempts.latest_attempt(PEF_EXPERIMENT_ID, BOUNDARY)
    assert latest is not None and latest.status is ExperimentAttemptStatus.DONE
    assert latest.attempt_no == 1
    assert latest.detail is not None and latest.detail.startswith("run_id=")
    # A heartbeat was written during the run at the orchestrator clock time.
    assert latest.heartbeat_at == BOUNDARY
    assert len(persistence.persisted) == 1


def test_duplicate_delivery_is_suppressed() -> None:
    attempts = FakeAttemptRepository()
    persistence = FakeShadowRunPersistence()
    orchestrator, _ = _orchestrator(attempts=attempts, persistence=persistence)
    first = orchestrator.run_cycle()
    second = orchestrator.run_cycle(now=BOUNDARY + timedelta(seconds=299))
    # Both cycles fall in the same 300s window: one attempt, one run row.
    assert first.action is ExperimentCycleAction.RAN
    assert second.action is ExperimentCycleAction.ALREADY_COMPLETE
    assert second.attempt is not None
    assert second.attempt.attempt_no == 1
    assert len(persistence.persisted) == 1


def test_retry_after_expired_lease_increments_attempt_no() -> None:
    attempts = FakeAttemptRepository()
    persistence = FakeShadowRunPersistence()
    orchestrator, _ = _orchestrator(attempts=attempts, persistence=persistence)
    # Seed attempt_no=1 as EXPIRED with an explicit reason (no run yet).
    attempt = ExperimentRunAttempt(
        experiment_id=PEF_EXPERIMENT_ID,
        as_of=BOUNDARY,
        attempt_no=1,
        status=ExperimentAttemptStatus.PENDING,
    )
    attempts.record_attempt(attempt)
    attempts.claim(
        attempt.attempt_id,
        owner="crashed-worker",
        lease_expires_at=BOUNDARY - timedelta(seconds=1),
        now=BOUNDARY - timedelta(seconds=30),
    )
    attempts.expire_stale(now=BOUNDARY)
    latest = attempts.latest_attempt(PEF_EXPERIMENT_ID, BOUNDARY)
    assert latest is not None and latest.status is ExperimentAttemptStatus.EXPIRED
    assert latest.detail == "lease expired"
    retry = orchestrator.run_cycle(now=BOUNDARY)
    assert retry.action is ExperimentCycleAction.RAN
    latest = attempts.latest_attempt(PEF_EXPERIMENT_ID, BOUNDARY)
    assert latest is not None and latest.attempt_no == 2
    assert len(persistence.persisted) == 1


def test_stale_running_attempt_is_expired_not_lost() -> None:
    attempts = FakeAttemptRepository()
    persistence = FakeShadowRunPersistence()
    orchestrator, _ = _orchestrator(attempts=attempts, persistence=persistence)
    # Simulate a crashed worker: claim the attempt, then let the lease lapse.
    attempts.expire_stale(now=BOUNDARY)  # no attempts yet
    attempt = ExperimentRunAttempt(
        experiment_id=PEF_EXPERIMENT_ID,
        as_of=BOUNDARY,
        attempt_no=1,
        status=ExperimentAttemptStatus.PENDING,
    )
    attempts.record_attempt(attempt)
    attempts.claim(
        attempt.attempt_id,
        owner="crashed-worker",
        lease_expires_at=BOUNDARY - timedelta(seconds=1),
        now=BOUNDARY - timedelta(seconds=30),
    )
    result = orchestrator.run_cycle(now=BOUNDARY)
    assert result.action is ExperimentCycleAction.RAN
    history = sorted(attempts.all_attempts(), key=lambda item: item.attempt_no)
    assert [item.status for item in history] == [
        ExperimentAttemptStatus.EXPIRED,
        ExperimentAttemptStatus.DONE,
    ]
    assert history[0].detail == "lease expired"


def test_attempt_owned_by_other_worker_is_deferred() -> None:
    attempts = FakeAttemptRepository()
    persistence = FakeShadowRunPersistence()
    orchestrator, _ = _orchestrator(attempts=attempts, persistence=persistence)
    attempt = ExperimentRunAttempt(
        experiment_id=PEF_EXPERIMENT_ID,
        as_of=BOUNDARY,
        attempt_no=1,
        status=ExperimentAttemptStatus.PENDING,
    )
    attempts.record_attempt(attempt)
    attempts.claim(
        attempt.attempt_id,
        owner="other-worker",
        lease_expires_at=BOUNDARY + timedelta(seconds=60),
        now=BOUNDARY - timedelta(seconds=1),
    )
    result = orchestrator.run_cycle(now=BOUNDARY)
    assert result.action is ExperimentCycleAction.DEFERRED_ACTIVE_OWNER
    assert len(persistence.persisted) == 0


def test_existing_ran_run_short_circuits_retry_without_new_run_row() -> None:
    attempts = FakeAttemptRepository()
    persistence = FakeShadowRunPersistence()
    orchestrator, _ = _orchestrator(attempts=attempts, persistence=persistence)
    first = orchestrator.run_cycle(now=BOUNDARY)
    assert first.run_id is not None
    # Crash+restart: the completed attempt row is lost/rolled back to RUNNING
    # with an expired lease, but the run row is already persisted.
    latest = attempts.latest_attempt(PEF_EXPERIMENT_ID, BOUNDARY)
    assert latest is not None
    attempts.set_attempt(
        ExperimentRunAttempt(
            experiment_id=latest.experiment_id,
            as_of=latest.as_of,
            attempt_no=latest.attempt_no,
            status=ExperimentAttemptStatus.RUNNING,
            lease_owner="crashed-worker",
            lease_expires_at=BOUNDARY - timedelta(seconds=1),
            schema_version=latest.schema_version,
        )
    )
    persistence.retained[BOUNDARY.isoformat()] = (
        first.run_id,
        RUN_CLASS_DEV,
        "RAN",
    )
    result = orchestrator.run_cycle(now=BOUNDARY)
    assert result.action is ExperimentCycleAction.ALREADY_COMPLETE
    assert len(persistence.persisted) == 1
    recovered = attempts.latest_attempt(PEF_EXPERIMENT_ID, BOUNDARY)
    assert recovered is not None
    assert recovered.status is ExperimentAttemptStatus.DONE


@pytest.mark.parametrize(
    ("binding", "canonical_context", "expected_reason"),
    [
        (None, True, "no candidate freeze receipt is bound"),
        ("DRIFTED", True, "bound candidate freeze receipt is DRIFTED, not FROZEN"),
        ("NOT_DURABLE", True, "bound freeze receipt has durable_freeze_at NULL (not durable)"),
        ("EARLIER", True, "Git publication precedes canonical DB durability"),
        ("EQUAL", True, "Git publication precedes canonical DB durability"),
        ("LATER", False, "run is not executing in the canonical DB context"),
    ],
)
def test_confirmatory_gate_matrix_skips_every_failing_gate(
    binding: str | None, canonical_context: bool, expected_reason: str
) -> None:
    if binding is None:
        resolved: FreezeBinding | None = None
    else:
        receipt = _frozen_receipt(frozen_at=BOUNDARY - timedelta(seconds=600))
        if binding == "DRIFTED":
            receipt = replace(receipt, status=FreezeStatus.DRIFTED, drift_reasons=("drift",))
        durable: datetime | None = BOUNDARY - timedelta(seconds=300)
        if binding == "NOT_DURABLE":
            durable = None
        elif binding == "EARLIER":
            durable = BOUNDARY + timedelta(seconds=300)
        elif binding == "EQUAL":
            durable = BOUNDARY
        resolved = FreezeBinding(
            receipt=receipt,
            durable_freeze_at=durable,
            publication_commit=(None if binding == "NOT_DURABLE" else "9" * 40),
            publication_committer_at=(
                None
                if binding == "NOT_DURABLE"
                else (
                    BOUNDARY - timedelta(seconds=300)
                    if binding == "LATER"
                    else BOUNDARY - timedelta(seconds=301)
                )
            ),
        )
    attempts = FakeAttemptRepository()
    persistence = FakeShadowRunPersistence()
    runner = RecordingRunner()
    orchestrator, _ = _orchestrator(
        attempts=attempts,
        persistence=persistence,
        run_class=RUN_CLASS_CONFIRMATORY,
        canonical_context=canonical_context,
        binding=StubBindingResolver(resolved),
        runner=runner,
    )
    result = orchestrator.run_cycle(now=BOUNDARY)
    assert result.action is ExperimentCycleAction.SKIPPED_CONFIRMATORY_GATES
    assert result.detail == expected_reason
    latest = attempts.latest_attempt(PEF_EXPERIMENT_ID, BOUNDARY)
    assert latest is not None and latest.status is ExperimentAttemptStatus.SKIPPED
    assert len(runner.calls) == 0
    assert len(persistence.persisted) == 0


def test_confirmatory_gates_allow_strictly_after_durable_frozen_in_canonical_context() -> None:
    receipt = _frozen_receipt(frozen_at=BOUNDARY - timedelta(seconds=600))
    binding = StubBindingResolver(
        FreezeBinding(
            receipt=receipt,
            durable_freeze_at=BOUNDARY - timedelta(seconds=600),
            publication_commit="9" * 40,
            publication_committer_at=BOUNDARY - timedelta(seconds=301),
        )
    )
    attempts = FakeAttemptRepository()
    persistence = FakeShadowRunPersistence()
    runner = RecordingRunner()
    orchestrator, _ = _orchestrator(
        attempts=attempts,
        persistence=persistence,
        run_class=RUN_CLASS_CONFIRMATORY,
        canonical_context=True,
        binding=binding,
        runner=runner,
    )
    result = orchestrator.run_cycle(now=BOUNDARY)
    assert result.action is ExperimentCycleAction.RAN
    assert runner.calls == [receipt]
    assert persistence.persisted[0][1] == RUN_CLASS_CONFIRMATORY
    latest = attempts.latest_attempt(PEF_EXPERIMENT_ID, BOUNDARY)
    assert latest is not None and latest.status is ExperimentAttemptStatus.DONE


def test_dev_run_never_binds_freeze_receipt_or_marks_confirmatory() -> None:
    receipt = _frozen_receipt(frozen_at=BOUNDARY - timedelta(seconds=300))
    binding = StubBindingResolver(
        FreezeBinding(
            receipt=receipt,
            durable_freeze_at=BOUNDARY - timedelta(seconds=600),
            publication_commit="9" * 40,
            publication_committer_at=BOUNDARY - timedelta(seconds=301),
        )
    )
    attempts = FakeAttemptRepository()
    persistence = FakeShadowRunPersistence()
    runner = RecordingRunner()
    orchestrator, _ = _orchestrator(
        attempts=attempts,
        persistence=persistence,
        run_class=RUN_CLASS_DEV,
        canonical_context=True,
        binding=binding,
        runner=runner,
    )
    result = orchestrator.run_cycle(now=BOUNDARY)
    assert result.action is ExperimentCycleAction.RAN
    assert runner.calls == [None]
    assert persistence.persisted[0][1] == RUN_CLASS_DEV


def test_gate_evaluation_matrix_pure_function() -> None:
    receipt = _frozen_receipt(frozen_at=BOUNDARY - timedelta(seconds=300))
    good = FreezeBinding(
        receipt=receipt,
        durable_freeze_at=BOUNDARY - timedelta(seconds=600),
        publication_commit="9" * 40,
        publication_committer_at=BOUNDARY - timedelta(seconds=301),
    )
    assert evaluate_confirmatory_gates(
        good, as_of=BOUNDARY, canonical_context=True
    ) == ConfirmatoryDecision(True, "all confirmatory binding gates hold", receipt)
    assert (
        evaluate_confirmatory_gates(good, as_of=BOUNDARY, canonical_context=False).reason
        == "run is not executing in the canonical DB context"
    )


def test_failed_candidate_execution_stays_explicit_never_empty_ranking() -> None:
    attempts = FakeAttemptRepository()
    persistence = FakeShadowRunPersistence()
    baseline = FakeBaselineRepository(_observations())

    class FailingRunner:
        def __call__(
            self,
            observations: tuple[BaselineObservationInput, ...],
            *,
            control_snapshot: BaselineSnapshot,
            control_receipt: ProjectionReceipt,
            generated_at: datetime,
            source_registry_version: Digest,
            candidate_freeze_receipt: CandidateFreezeReceipt | None,
        ) -> ShadowExperimentRun:
            artifact = failed_pef_artifact(
                control_snapshot=control_snapshot,
                control_receipt=control_receipt,
                as_of=generated_at,
                generated_at=generated_at,
                source_registry_version=source_registry_version,
                failure_reason="candidate arm exploded",
            )
            candidate_receipt = build_pef_receipt(
                artifact, observations=observations, control_snapshot=control_snapshot
            )
            return build_shadow_experiment_run(
                control_snapshot=control_snapshot,
                control_receipt=control_receipt,
                candidate_artifact=artifact,
                candidate_receipt=candidate_receipt,
                as_of=generated_at,
                generated_at=generated_at,
                candidate_freeze_receipt_id=None,
            )

    orchestrator = ExperimentOrchestrator(
        attempts=attempts,
        baseline_repository=baseline,
        persistence=persistence,
        source_registry_version=REGISTRY,
        shadow_runner=FailingRunner(),
        worker_id=WORKER,
        clock=lambda: BOUNDARY,
    )
    result = orchestrator.run_cycle()
    assert result.action is ExperimentCycleAction.FAILED
    assert result.run_id is not None
    latest = attempts.latest_attempt(PEF_EXPERIMENT_ID, BOUNDARY)
    assert latest is not None and latest.status is ExperimentAttemptStatus.FAILED
    assert latest.detail is not None and "candidate arm exploded" in latest.detail
    # The FAILED run is persisted explicitly and never a "empty ranking" run.
    assert len(persistence.persisted) == 1
    assert persistence.persisted[0][2] is ShadowRunStatus.FAILED
    # Retry of the failed boundary re-executes deterministically: same run id,
    # no duplicate row, attempt stays explicitly FAILED.
    retry = orchestrator.run_cycle(now=BOUNDARY)
    assert retry.action is ExperimentCycleAction.FAILED
    assert retry.run_id == result.run_id
    assert len(persistence.persisted) == 2
    latest = attempts.latest_attempt(PEF_EXPERIMENT_ID, BOUNDARY)
    assert latest is not None and latest.attempt_no == 2


class MemoryWorkerRepository:
    def get_source_fetch_state(self, source_id: str) -> SourceFetchState | None:
        return None

    def upsert_source(self, source: SourceContract) -> None:
        return None


class NoopRunner:
    async def acquire(self, source_id: str) -> AcquisitionResult:
        return AcquisitionResult(
            run_id=uuid4(),
            source_id=source_id,
            status=CollectionRunStatus.SUCCESS,
            inserted=0,
            duplicates=0,
            rejected=0,
            observation_ids=(),
            failure_code=None,
        )


def _registered_source(source_id: str) -> RegisteredSource:
    return RegisteredSource(
        contract=SourceContract(
            source_id=source_id,
            display_name=source_id,
            acquisition_class=AcquisitionClass.A_AUTHORITATIVE_STRUCTURED,
            signal_roles=(SignalRole.PRIMARY_EMISSION,),
            transport=SourceTransport.REST,
        ),
        endpoint_url=f"https://{source_id}.example/api",
        fallback_urls=(),
        fallback_semantics=None,
        accepted_content_types=("application/json",),
        policy_profile="structured-public-v0",
        authentication="NONE",
        credential_ref=None,
        poll_interval_seconds=3600,
        finite_window=True,
        etag_support="UNKNOWN",
        last_modified_support="UNKNOWN",
        raw_contract={},
    )


def test_worker_run_once_invokes_experiment_orchestrator() -> None:
    registry = SourceRegistry(
        sources={"source.alpha": _registered_source("source.alpha")},
        source_registry_version=Digest("sha256:" + "2" * 64),
    )
    attempts = FakeAttemptRepository()
    persistence = FakeShadowRunPersistence()
    orchestrator, _ = _orchestrator(attempts=attempts, persistence=persistence)
    worker = AcquisitionWorker(
        registry=registry,
        repository=MemoryWorkerRepository(),
        service=NoopRunner(),
        experiment_orchestrator=orchestrator,
    )
    cycle = asyncio.run(worker.run_once())
    assert cycle.experiment is not None
    assert cycle.experiment.action is ExperimentCycleAction.RAN
    assert len(persistence.persisted) == 1
