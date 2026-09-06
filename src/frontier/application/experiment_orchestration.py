"""Prospective experiment orchestration (WP2, G1).

The orchestrator derives the next due PEF_V0 experiment boundary
deterministically from the preregistration cadence
(``experiments/advanced_intelligence/pef_v0/preregistration.json``:
``snapshot_schedule.cadence_seconds = 300`` aligned to UTC UNIX
epoch-multiple-of-300 seconds) and drives the ``experiment_run_attempts``
lease lifecycle around the existing paired shadow-experiment engine. There
is no second scheduler state model and no in-memory schedule state: boundary
due-ness is a pure function of the clock, and execution state lives only in
the mutable attempts table. Acquisition due-ness stays in
``source_fetch_state``.

Paired-integrity discipline (R1/R6/R8): both arms are built from one fetch of
the eligible universe — the same ``as_of``, observations, grouping relations,
enabled sources, and source-health horizon — and the candidate reuses the
published control snapshot. ``generated_at`` is pinned to the boundary, so a
retry of the same boundary reproduces the identical control receipt, run
digest and content-derived run id: re-execution after a crash persists no
duplicate row. A failed candidate arm never becomes an empty ranking: the
attempt is FAILED with the run's explicit failure reason.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Protocol

from frontier.application.advanced_intelligence import run_shadow_experiment
from frontier.application.drift_sentry import DriftChecker
from frontier.application.intelligence import (
    BaselineIntelligenceRepository,
    run_baseline_intelligence,
)
from frontier.domain.advanced_intelligence import (
    PEF_EXPERIMENT_ID,
    ShadowExperimentRun,
    ShadowRunStatus,
)
from frontier.domain.candidate_freeze import CandidateFreezeReceipt, FreezeStatus
from frontier.domain.digests import Digest
from frontier.domain.drift_sentry import DriftStatus
from frontier.domain.intelligence import BaselineObservationInput, BaselineSnapshot
from frontier.domain.opportunity import ExperimentAttemptStatus, ExperimentRunAttempt
from frontier.domain.receipt import ProjectionReceipt

EXPERIMENT_BOUNDARY_CADENCE_SECONDS = 300
RUN_CLASS_DEV = "DEV"
RUN_CLASS_CONFIRMATORY = "CONFIRMATORY"
RUN_CLASSES: tuple[str, ...] = (RUN_CLASS_DEV, RUN_CLASS_CONFIRMATORY)

LEASE_EXPIRED_DETAIL = "lease expired"

Clock = Callable[[], datetime]


def derive_experiment_boundary(
    now: datetime, *, cadence_seconds: int = EXPERIMENT_BOUNDARY_CADENCE_SECONDS
) -> datetime:
    """Derive the experiment boundary for ``now`` deterministically.

    The boundary is the largest UTC instant that is an integer multiple of the
    preregistration cadence (300 s) and less than or equal to ``now``. A
    boundary at ``now`` exactly is due now. No schedule state is retained.
    """
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("boundary derivation requires a timezone-aware clock")
    if cadence_seconds <= 0:
        raise ValueError("cadence_seconds must be positive")
    epoch_seconds = int(now.timestamp())
    aligned = epoch_seconds - (epoch_seconds % cadence_seconds)
    return datetime.fromtimestamp(aligned, tz=UTC)


@dataclass(frozen=True, slots=True)
class FreezeBinding:
    """A resolvable candidate freeze binding read from the canonical DB.

    ``durable_freeze_at`` is the canonical-DB durability stamp (NULL means the
    freeze is not durable and can never gate a confirmatory run).
    """

    receipt: CandidateFreezeReceipt
    durable_freeze_at: datetime | None


@dataclass(frozen=True, slots=True)
class ConfirmatoryDecision:
    """Outcome of the four confirmatory binding-correctness gates."""

    allowed: bool
    reason: str
    receipt: CandidateFreezeReceipt | None = None


def evaluate_confirmatory_gates(
    binding: FreezeBinding | None,
    *,
    as_of: datetime,
    canonical_context: bool,
) -> ConfirmatoryDecision:
    """Evaluate the confirmatory binding-correctness gates (fail-closed).

    Gates: (a) a freeze receipt is bound and resolvable to a FROZEN row,
    (b) ``durable_freeze_at`` is NOT NULL, (c) the run ``as_of`` is strictly
    after ``durable_freeze_at``, (d) the run executes in the canonical DB
    context. Any failing gate denies the confirmatory run. A DEV run never
    reaches this evaluation, and confirmatory status is never inferred merely
    because a receipt exists somewhere. Sentry-drift recomputation (WP5) runs
    AFTER these gates in the orchestrator/evaluator confirmatory paths.
    """
    if binding is None:
        return ConfirmatoryDecision(False, "no candidate freeze receipt is bound")
    if binding.receipt.status is not FreezeStatus.FROZEN:
        return ConfirmatoryDecision(
            False,
            f"bound candidate freeze receipt is {binding.receipt.status.value}, not FROZEN",
        )
    if binding.durable_freeze_at is None:
        return ConfirmatoryDecision(
            False,
            "bound freeze receipt has durable_freeze_at NULL (not durable)",
        )
    if not as_of > binding.durable_freeze_at:
        return ConfirmatoryDecision(
            False,
            "run as_of is not strictly after durable_freeze_at",
        )
    if not canonical_context:
        return ConfirmatoryDecision(
            False,
            "run is not executing in the canonical DB context",
        )
    return ConfirmatoryDecision(True, "all confirmatory binding gates hold", binding.receipt)


class ExperimentAttemptRepository(Protocol):
    """Mutable operational gateway for experiment run attempts."""

    def latest_attempt(
        self, experiment_id: str, as_of: datetime
    ) -> ExperimentRunAttempt | None: ...
    def record_attempt(self, attempt: ExperimentRunAttempt) -> bool: ...
    def claim(
        self,
        attempt_id: str,
        *,
        owner: str,
        lease_expires_at: datetime,
        now: datetime,
    ) -> bool: ...
    def heartbeat(self, attempt_id: str, *, owner: str, at: datetime) -> bool: ...
    def finish(
        self,
        attempt_id: str,
        *,
        owner: str,
        status: ExperimentAttemptStatus,
        detail: str | None,
        at: datetime,
    ) -> bool: ...
    def expire_stale(
        self, *, now: datetime, detail: str = LEASE_EXPIRED_DETAIL
    ) -> tuple[ExperimentRunAttempt, ...]: ...


class ShadowRunPersistence(Protocol):
    """Idempotent append-only persistence for completed paired shadow runs."""

    def persist(self, run: ShadowExperimentRun, *, run_class: str) -> str: ...
    def latest_run_id_and_class_for_as_of(self, as_of: datetime) -> tuple[str, str, str] | None: ...


class FreezeBindingResolver(Protocol):
    def latest_binding(self) -> FreezeBinding | None: ...


class ShadowExperimentRunner(Protocol):
    def __call__(
        self,
        observations: tuple[BaselineObservationInput, ...],
        *,
        control_snapshot: BaselineSnapshot,
        control_receipt: ProjectionReceipt,
        generated_at: datetime,
        source_registry_version: Digest,
        candidate_freeze_receipt: CandidateFreezeReceipt | None,
    ) -> ShadowExperimentRun: ...


class ExperimentCycleAction(StrEnum):
    """Explicit outcome of one orchestrator cycle."""

    RAN = "RAN"
    FAILED = "FAILED"
    SKIPPED_CONFIRMATORY_GATES = "SKIPPED_CONFIRMATORY_GATES"
    ALREADY_COMPLETE = "ALREADY_COMPLETE"
    DEFERRED_ACTIVE_OWNER = "DEFERRED_ACTIVE_OWNER"


@dataclass(frozen=True, slots=True)
class ExperimentCycleResult:
    boundary: datetime
    action: ExperimentCycleAction
    attempt: ExperimentRunAttempt | None
    run_id: str | None = None
    detail: str | None = None


class ExperimentOrchestrator:
    """Drives one prospective experiment boundary per cycle.

    Independently callable (tests, operators) and wired into the acquisition
    worker lifecycle as a single-process companion step. The orchestrator owns
    no schedule state: due-ness is derived from the clock, execution state
    from the attempts table.
    """

    def __init__(
        self,
        *,
        attempts: ExperimentAttemptRepository,
        baseline_repository: BaselineIntelligenceRepository,
        persistence: ShadowRunPersistence,
        source_registry_version: Digest,
        freeze_binding: FreezeBindingResolver | None = None,
        shadow_runner: ShadowExperimentRunner | None = None,
        run_class: str = RUN_CLASS_DEV,
        canonical_context: bool = False,
        drift_sentry: DriftChecker | None = None,
        worker_id: str = "frontier-worker",
        lease_seconds: float = 120.0,
        cadence_seconds: int = EXPERIMENT_BOUNDARY_CADENCE_SECONDS,
        clock: Clock | None = None,
    ) -> None:
        if run_class not in RUN_CLASSES:
            raise ValueError("run_class must be DEV or CONFIRMATORY")
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        if cadence_seconds <= 0:
            raise ValueError("cadence_seconds must be positive")
        if not worker_id:
            raise ValueError("worker_id must be non-empty")
        self._attempts = attempts
        self._baseline_repository = baseline_repository
        self._persistence = persistence
        self._source_registry_version = source_registry_version
        self._freeze_binding = freeze_binding
        self._shadow_runner: ShadowExperimentRunner = shadow_runner or run_shadow_experiment
        self._run_class = run_class
        self._canonical_context = canonical_context
        self._drift_sentry = drift_sentry
        self._worker_id = worker_id
        self._lease_seconds = lease_seconds
        self._cadence_seconds = cadence_seconds
        self._clock: Clock = clock or (lambda: datetime.now(UTC))

    def run_cycle(self, *, now: datetime | None = None) -> ExperimentCycleResult:
        """Execute the current due boundary once (idempotent, retry-aware)."""
        at = now or self._clock()
        self._attempts.expire_stale(now=at)
        boundary = derive_experiment_boundary(at, cadence_seconds=self._cadence_seconds)
        latest = self._attempts.latest_attempt(PEF_EXPERIMENT_ID, boundary)
        if latest is not None and latest.status in (
            ExperimentAttemptStatus.DONE,
            ExperimentAttemptStatus.SKIPPED,
        ):
            # A DONE (or gate-skipped) boundary is never re-executed.
            return ExperimentCycleResult(
                boundary=boundary,
                action=ExperimentCycleAction.ALREADY_COMPLETE,
                attempt=latest,
                detail=latest.detail,
            )
        if latest is not None and latest.status is ExperimentAttemptStatus.RUNNING:
            lease_active = latest.lease_expires_at is not None and latest.lease_expires_at > at
            if lease_active and latest.lease_owner != self._worker_id:
                return ExperimentCycleResult(
                    boundary=boundary,
                    action=ExperimentCycleAction.DEFERRED_ACTIVE_OWNER,
                    attempt=latest,
                    detail=f"attempt owned by {latest.lease_owner}",
                )
            # Otherwise the attempt is adoptable (our own active lease).
        attempt_no = 1
        if latest is not None and latest.status.is_retryable:
            attempt_no = latest.attempt_no + 1
        pending = ExperimentRunAttempt(
            experiment_id=PEF_EXPERIMENT_ID,
            as_of=boundary,
            attempt_no=attempt_no,
            status=ExperimentAttemptStatus.PENDING,
        )
        self._attempts.record_attempt(pending)
        lease_expires_at = at + timedelta(seconds=self._lease_seconds)
        if not self._attempts.claim(
            pending.attempt_id,
            owner=self._worker_id,
            lease_expires_at=lease_expires_at,
            now=at,
        ):
            return ExperimentCycleResult(
                boundary=boundary,
                action=ExperimentCycleAction.DEFERRED_ACTIVE_OWNER,
                attempt=_with_status(
                    pending,
                    ExperimentAttemptStatus.RUNNING,
                    lease_owner=self._worker_id,
                    lease_expires_at=lease_expires_at,
                ),
                detail="attempt claimed concurrently by another worker",
            )
        attempt = _with_status(
            pending,
            ExperimentAttemptStatus.RUNNING,
            lease_owner=self._worker_id,
            lease_expires_at=lease_expires_at,
            heartbeat_at=at,
        )
        return self._execute_boundary(attempt, boundary)

    def _execute_boundary(
        self, attempt: ExperimentRunAttempt, boundary: datetime
    ) -> ExperimentCycleResult:
        existing = self._persistence.latest_run_id_and_class_for_as_of(boundary)
        completed = (
            None
            if existing is None
            else self._finish_from_existing_run(attempt, boundary, existing)
        )
        if completed is not None:
            return completed
        freeze_receipt: CandidateFreezeReceipt | None = None
        if self._run_class == RUN_CLASS_CONFIRMATORY:
            decision = self._evaluate_confirmatory_gates(boundary)
            if not decision.allowed:
                self._attempts.finish(
                    attempt.attempt_id,
                    owner=self._worker_id,
                    status=ExperimentAttemptStatus.SKIPPED,
                    detail=decision.reason,
                    at=self._clock(),
                )
                return ExperimentCycleResult(
                    boundary=boundary,
                    action=ExperimentCycleAction.SKIPPED_CONFIRMATORY_GATES,
                    attempt=_with_status(
                        attempt, ExperimentAttemptStatus.SKIPPED, detail=decision.reason
                    ),
                    detail=decision.reason,
                )
            freeze_receipt = decision.receipt
            assert decision.receipt is not None  # gate semantics guarantee a FROZEN receipt
            if self._drift_sentry is not None:
                drift_report = self._drift_sentry.check(decision.receipt, now=self._clock())
                if drift_report.status is DriftStatus.DRIFTED:
                    detail = "DRIFTED: " + "; ".join(drift_report.reasons)
                    self._attempts.finish(
                        attempt.attempt_id,
                        owner=self._worker_id,
                        status=ExperimentAttemptStatus.SKIPPED,
                        detail=detail,
                        at=self._clock(),
                    )
                    return ExperimentCycleResult(
                        boundary=boundary,
                        action=ExperimentCycleAction.SKIPPED_CONFIRMATORY_GATES,
                        attempt=_with_status(
                            attempt, ExperimentAttemptStatus.SKIPPED, detail=detail
                        ),
                        detail=detail,
                    )
        try:
            run = self._run_paired_experiment(attempt, boundary, freeze_receipt)
        except Exception as error:  # explicit FAILED attempt, never silent
            detail = f"experiment execution failed: {type(error).__name__}: {error}"
            self._attempts.finish(
                attempt.attempt_id,
                owner=self._worker_id,
                status=ExperimentAttemptStatus.FAILED,
                detail=detail,
                at=self._clock(),
            )
            return ExperimentCycleResult(
                boundary=boundary,
                action=ExperimentCycleAction.FAILED,
                attempt=_with_status(attempt, ExperimentAttemptStatus.FAILED, detail=detail),
                detail=detail,
            )
        run_id = self._persistence.persist(run, run_class=self._run_class)
        if run.status is ShadowRunStatus.FAILED:
            # A failed candidate execution never becomes an "empty ranking":
            # the failed run is persisted explicitly and the attempt stays
            # FAILED (retryable) with the run's failure reason.
            detail = f"run_id={run_id} failed candidate arm: {run.failure_reason}"
            self._attempts.finish(
                attempt.attempt_id,
                owner=self._worker_id,
                status=ExperimentAttemptStatus.FAILED,
                detail=detail,
                at=self._clock(),
            )
            return ExperimentCycleResult(
                boundary=boundary,
                action=ExperimentCycleAction.FAILED,
                attempt=_with_status(attempt, ExperimentAttemptStatus.FAILED, detail=detail),
                run_id=run_id,
                detail=detail,
            )
        detail = f"run_id={run_id} run_class={self._run_class}"
        self._attempts.finish(
            attempt.attempt_id,
            owner=self._worker_id,
            status=ExperimentAttemptStatus.DONE,
            detail=detail,
            at=self._clock(),
        )
        return ExperimentCycleResult(
            boundary=boundary,
            action=ExperimentCycleAction.RAN,
            attempt=_with_status(attempt, ExperimentAttemptStatus.DONE, detail=detail),
            run_id=run_id,
            detail=detail,
        )

    def _finish_from_existing_run(
        self, attempt: ExperimentRunAttempt, boundary: datetime, existing: tuple[str, str, str]
    ) -> ExperimentCycleResult | None:
        run_id, run_class, run_status = existing
        if self._run_class == RUN_CLASS_CONFIRMATORY and run_class != RUN_CLASS_CONFIRMATORY:
            # A DEV run can never be escalated to confirmatory: the boundary
            # stays explicitly SKIPPED for confirmatory use.
            detail = f"existing run {run_id} is {run_class}, not CONFIRMATORY"
            self._attempts.finish(
                attempt.attempt_id,
                owner=self._worker_id,
                status=ExperimentAttemptStatus.SKIPPED,
                detail=detail,
                at=self._clock(),
            )
            return ExperimentCycleResult(
                boundary=boundary,
                action=ExperimentCycleAction.SKIPPED_CONFIRMATORY_GATES,
                attempt=_with_status(attempt, ExperimentAttemptStatus.SKIPPED, detail=detail),
                detail=detail,
            )
        if run_status == "RAN":
            detail = f"completed run {run_id} already persisted for this boundary"
            self._attempts.finish(
                attempt.attempt_id,
                owner=self._worker_id,
                status=ExperimentAttemptStatus.DONE,
                detail=detail,
                at=self._clock(),
            )
            return ExperimentCycleResult(
                boundary=boundary,
                action=ExperimentCycleAction.ALREADY_COMPLETE,
                attempt=_with_status(attempt, ExperimentAttemptStatus.DONE, detail=detail),
                run_id=run_id,
                detail=detail,
            )
        # An explicitly FAILED run is retryable: re-execution is deterministic
        # (pinned generated_at) and re-persists the identical run, so no
        # duplicate row can appear.
        return None

    def _evaluate_confirmatory_gates(self, boundary: datetime) -> ConfirmatoryDecision:
        binding = None if self._freeze_binding is None else self._freeze_binding.latest_binding()
        return evaluate_confirmatory_gates(
            binding, as_of=boundary, canonical_context=self._canonical_context
        )

    def _run_paired_experiment(
        self,
        attempt: ExperimentRunAttempt,
        boundary: datetime,
        freeze_receipt: CandidateFreezeReceipt | None,
    ) -> ShadowExperimentRun:
        repository = self._baseline_repository
        # One fetch of the eligible universe, deterministically ordered, so
        # BOTH arms consume the identical inputs (R1/R6). Candidate ordering
        # is enforced lexicographically by the PEF ranking itself; input
        # ordering is pinned here so no repository order can leak in.
        observations = tuple(
            sorted(
                repository.list_baseline_observations_as_of(boundary),
                key=lambda item: item.observation_id,
            )
        )
        relations = tuple(repository.list_grouping_relations_as_of(boundary))
        enabled_source_ids = tuple(repository.list_enabled_source_ids())
        health = tuple(repository.list_latest_health_as_of(boundary))
        self._attempts.heartbeat(attempt.attempt_id, owner=self._worker_id, at=self._clock())
        control = run_baseline_intelligence(
            repository,
            as_of=boundary,
            generated_at=boundary,
            source_registry_version=self._source_registry_version,
            observations=observations,
            relations=relations,
            enabled_source_ids=enabled_source_ids,
            health=health,
        )
        self._attempts.heartbeat(attempt.attempt_id, owner=self._worker_id, at=self._clock())
        run = self._shadow_runner(
            observations,
            control_snapshot=control.snapshot,
            control_receipt=control.receipt,
            generated_at=boundary,
            source_registry_version=self._source_registry_version,
            candidate_freeze_receipt=freeze_receipt,
        )
        self._attempts.heartbeat(attempt.attempt_id, owner=self._worker_id, at=self._clock())
        return run


def _with_status(
    attempt: ExperimentRunAttempt,
    status: ExperimentAttemptStatus,
    *,
    detail: str | None = None,
    lease_owner: str | None = None,
    lease_expires_at: datetime | None = None,
    heartbeat_at: datetime | None = None,
) -> ExperimentRunAttempt:
    """Return a copy of ``attempt`` with the given lifecycle fields replaced."""
    return ExperimentRunAttempt(
        experiment_id=attempt.experiment_id,
        as_of=attempt.as_of,
        attempt_no=attempt.attempt_no,
        status=status,
        detail=detail,
        lease_owner=lease_owner,
        lease_expires_at=lease_expires_at,
        heartbeat_at=heartbeat_at,
        schema_version=attempt.schema_version,
    )
