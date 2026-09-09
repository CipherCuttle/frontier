from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol

from frontier.application.candidate_freeze_v1 import verify_freeze_v1
from frontier.application.experiment_orchestration import (
    LEASE_EXPIRED_DETAIL,
    ExperimentCycleAction,
    ExperimentCycleResult,
    derive_experiment_boundary,
)
from frontier.application.freeze_publication import require_confirmatory_boundary
from frontier.application.freeze_publication_v1 import derive_freeze_publication_v1
from frontier.application.intelligence import BaselineIntelligenceRepository
from frontier.application.pef_v1 import PefV1ControlRun, run_pef_v1_control
from frontier.domain.advanced_intelligence import ShadowExperimentRun, ShadowRunStatus
from frontier.domain.candidate_freeze import FreezeStatus
from frontier.domain.candidate_freeze_v1 import CandidateFreezeReceiptV1
from frontier.domain.digests import Digest
from frontier.domain.intelligence import BaselineObservationInput
from frontier.domain.opportunity import ExperimentAttemptStatus, ExperimentRunAttempt
from frontier.domain.pef_v1 import (
    PEF_V1_CANDIDATE_ID,
    PEF_V1_CONFIGURATION_DIGEST,
    PEF_V1_EXPERIMENT_ID,
    PefV1Artifact,
    build_pef_v1_artifact,
    build_pef_v1_receipt,
    build_shadow_experiment_run_v1,
    failed_pef_v1_artifact,
)
from frontier.domain.receipt import ProjectionReceipt

RUN_CLASS_CONFIRMATORY = "CONFIRMATORY"


@dataclass(frozen=True, slots=True)
class PefV1FreezeBinding:
    receipt: CandidateFreezeReceiptV1
    durable_freeze_at: datetime | None
    publication_commit: str | None
    publication_committer_at: datetime | None
    publication_digest: Digest | None


@dataclass(frozen=True, slots=True)
class PefV1ConfirmatoryEvidence:
    grouping_receipt: ProjectionReceipt
    control_receipt: ProjectionReceipt
    candidate_artifact: PefV1Artifact
    candidate_receipt: ProjectionReceipt
    run: ShadowExperimentRun


class PefV1FreezeBindingResolver(Protocol):
    def latest_binding(self) -> PefV1FreezeBinding | None: ...


class PefV1AttemptRepository(Protocol):
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


class PefV1ConfirmatoryPersistence(Protocol):
    def latest_run_id_and_class_for_as_of(self, as_of: datetime) -> tuple[str, str, str] | None: ...
    def persist(
        self,
        evidence: PefV1ConfirmatoryEvidence,
        *,
        expected_freeze_receipt_id: str,
    ) -> str: ...


def evaluate_pef_v1_confirmatory_gates(
    binding: PefV1FreezeBinding | None,
    *,
    as_of: datetime,
    canonical_context: bool,
) -> tuple[bool, str]:
    if binding is None:
        return False, "no PEF_V1 candidate freeze receipt is bound"
    receipt = binding.receipt
    if receipt.status is not FreezeStatus.FROZEN:
        return False, "bound PEF_V1 candidate freeze receipt is not FROZEN"
    if receipt.experiment_id != PEF_V1_EXPERIMENT_ID:
        return False, "bound freeze receipt is not PEF_V1"
    if receipt.candidate_id != PEF_V1_CANDIDATE_ID:
        return False, "bound freeze receipt candidate identity mismatch"
    if receipt.configuration_digest != PEF_V1_CONFIGURATION_DIGEST:
        return False, "bound freeze receipt configuration identity mismatch"
    if binding.durable_freeze_at is None:
        return False, "bound PEF_V1 freeze receipt is not durable"
    if (
        binding.publication_commit is None
        or binding.publication_committer_at is None
        or binding.publication_digest is None
    ):
        return False, "bound PEF_V1 freeze receipt has no verified Git publication"
    if binding.publication_committer_at < binding.durable_freeze_at:
        return False, "PEF_V1 Git publication precedes canonical DB durability"
    try:
        require_confirmatory_boundary(
            as_of=as_of,
            publication_committer_at=binding.publication_committer_at,
        )
    except ValueError as error:
        return False, str(error)
    if not canonical_context:
        return False, "PEF_V1 confirmatory run is not in canonical DB context"
    return True, "all PEF_V1 confirmatory binding gates hold"


def _build_candidate(
    observations: tuple[BaselineObservationInput, ...],
    *,
    control: PefV1ControlRun,
    generated_at: datetime,
    source_registry_version: Digest,
) -> tuple[PefV1Artifact, ProjectionReceipt]:
    try:
        artifact = build_pef_v1_artifact(
            observations,
            control_snapshot=control.snapshot,
            control_receipt=control.receipt,
            grouping_projection=control.grouping_projection,
            grouping_receipt=control.grouping_receipt,
            as_of=control.snapshot.as_of,
            generated_at=generated_at,
            source_registry_version=source_registry_version,
        )
    except Exception as error:
        artifact = failed_pef_v1_artifact(
            control_snapshot=control.snapshot,
            control_receipt=control.receipt,
            grouping_projection=control.grouping_projection,
            grouping_receipt=control.grouping_receipt,
            as_of=control.snapshot.as_of,
            generated_at=generated_at,
            source_registry_version=source_registry_version,
            failure_reason=f"candidate arm failed: {error}",
        )
    receipt = build_pef_v1_receipt(
        artifact,
        observations=observations,
        control_snapshot=control.snapshot,
    )
    return artifact, receipt


def build_pef_v1_confirmatory_evidence(
    repository: BaselineIntelligenceRepository,
    *,
    as_of: datetime,
    generated_at: datetime,
    source_registry_version: Digest,
    freeze_receipt: CandidateFreezeReceiptV1,
) -> PefV1ConfirmatoryEvidence:
    if freeze_receipt.status is not FreezeStatus.FROZEN:
        raise ValueError("PEF_V1 confirmatory evidence requires a FROZEN receipt")
    if freeze_receipt.experiment_id != PEF_V1_EXPERIMENT_ID:
        raise ValueError("PEF_V1 confirmatory freeze experiment identity mismatch")
    if freeze_receipt.candidate_id != PEF_V1_CANDIDATE_ID:
        raise ValueError("PEF_V1 confirmatory freeze candidate identity mismatch")
    if freeze_receipt.configuration_digest != PEF_V1_CONFIGURATION_DIGEST:
        raise ValueError("PEF_V1 confirmatory freeze configuration identity mismatch")

    observations = tuple(
        sorted(
            repository.list_baseline_observations_as_of(as_of),
            key=lambda item: item.observation_id,
        )
    )
    relations = tuple(repository.list_grouping_relations_as_of(as_of))
    enabled_source_ids = tuple(repository.list_enabled_source_ids())
    health = tuple(repository.list_latest_health_as_of(as_of))
    control = run_pef_v1_control(
        repository,
        as_of=as_of,
        generated_at=generated_at,
        source_registry_version=source_registry_version,
        observations=observations,
        relations=relations,
        enabled_source_ids=enabled_source_ids,
        health=health,
    )
    candidate_artifact, candidate_receipt = _build_candidate(
        observations,
        control=control,
        generated_at=generated_at,
        source_registry_version=source_registry_version,
    )
    run = build_shadow_experiment_run_v1(
        control_snapshot=control.snapshot,
        control_receipt=control.receipt,
        grouping_projection=control.grouping_projection,
        grouping_receipt=control.grouping_receipt,
        candidate_artifact=candidate_artifact,
        candidate_receipt=candidate_receipt,
        as_of=as_of,
        generated_at=generated_at,
    )
    run = replace(run, candidate_freeze_receipt_id=freeze_receipt.receipt_id)
    if run.candidate_freeze_receipt_id != freeze_receipt.receipt_id:
        raise RuntimeError("PEF_V1 confirmatory run failed to bind the authorized freeze")
    return PefV1ConfirmatoryEvidence(
        grouping_receipt=control.grouping_receipt,
        control_receipt=control.receipt,
        candidate_artifact=candidate_artifact,
        candidate_receipt=candidate_receipt,
        run=run,
    )


class PefV1ConfirmatoryOrchestrator:
    def __init__(
        self,
        *,
        attempts: PefV1AttemptRepository,
        baseline_repository: BaselineIntelligenceRepository,
        persistence: PefV1ConfirmatoryPersistence,
        freeze_binding: PefV1FreezeBindingResolver,
        source_registry_version: Digest,
        repository_root: Path,
        canonical_context: bool,
        worker_id: str = "frontier-worker",
        lease_seconds: float = 120.0,
    ) -> None:
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        self._attempts = attempts
        self._baseline_repository = baseline_repository
        self._persistence = persistence
        self._freeze_binding = freeze_binding
        self._source_registry_version = source_registry_version
        self._repository_root = repository_root
        self._canonical_context = canonical_context
        self._worker_id = worker_id
        self._lease_seconds = lease_seconds

    def run_cycle(self, *, now: datetime | None = None) -> ExperimentCycleResult:
        at = now or datetime.now(UTC)
        self._attempts.expire_stale(now=at)
        boundary = derive_experiment_boundary(at)
        latest = self._attempts.latest_attempt(PEF_V1_EXPERIMENT_ID, boundary)
        if latest is not None and latest.status in (
            ExperimentAttemptStatus.DONE,
            ExperimentAttemptStatus.SKIPPED,
        ):
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
        attempt_no = (
            1 if latest is None or not latest.status.is_retryable else latest.attempt_no + 1
        )
        pending = ExperimentRunAttempt(
            experiment_id=PEF_V1_EXPERIMENT_ID,
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
                attempt=pending,
                detail="PEF_V1 attempt claimed concurrently by another worker",
            )

        binding = self._freeze_binding.latest_binding()
        allowed, reason = evaluate_pef_v1_confirmatory_gates(
            binding,
            as_of=boundary,
            canonical_context=self._canonical_context,
        )
        if not allowed or binding is None:
            return self._skip(pending, reason, at=at, boundary=boundary)

        verification = verify_freeze_v1(
            binding.receipt,
            root=self._repository_root,
            verified_at=at,
            implementation_ref=binding.receipt.implementation_commit,
        )
        if verification.status is not FreezeStatus.FROZEN:
            detail = "DRIFTED: " + "; ".join(verification.drift_reasons)
            return self._skip(pending, detail, at=at, boundary=boundary)
        try:
            runtime_publication = derive_freeze_publication_v1(
                self._repository_root,
                binding.receipt,
            )
        except (RuntimeError, ValueError) as error:
            return self._skip(
                pending,
                f"runtime freeze publication verification failed: {error}",
                at=at,
                boundary=boundary,
            )
        if (
            runtime_publication.publication_commit != binding.publication_commit
            or runtime_publication.publication_committer_at != binding.publication_committer_at
            or runtime_publication.publication_digest != binding.publication_digest
        ):
            return self._skip(
                pending,
                "runtime freeze publication does not equal canonical DB publication authority",
                at=at,
                boundary=boundary,
            )

        existing = self._persistence.latest_run_id_and_class_for_as_of(boundary)
        if existing is not None:
            run_id, run_class, run_status = existing
            if run_class == RUN_CLASS_CONFIRMATORY and run_status == "RAN":
                detail = f"completed PEF_V1 confirmatory run {run_id} already persisted"
                self._attempts.finish(
                    pending.attempt_id,
                    owner=self._worker_id,
                    status=ExperimentAttemptStatus.DONE,
                    detail=detail,
                    at=at,
                )
                return ExperimentCycleResult(
                    boundary=boundary,
                    action=ExperimentCycleAction.ALREADY_COMPLETE,
                    attempt=replace(pending, status=ExperimentAttemptStatus.DONE, detail=detail),
                    run_id=run_id,
                    detail=detail,
                )
            if run_class != RUN_CLASS_CONFIRMATORY:
                return self._skip(
                    pending,
                    f"existing PEF_V1 run {run_id} is {run_class}, not CONFIRMATORY",
                    at=at,
                    boundary=boundary,
                )

        self._attempts.heartbeat(pending.attempt_id, owner=self._worker_id, at=at)
        try:
            evidence = build_pef_v1_confirmatory_evidence(
                self._baseline_repository,
                as_of=boundary,
                generated_at=boundary,
                source_registry_version=self._source_registry_version,
                freeze_receipt=binding.receipt,
            )
            run_id = self._persistence.persist(
                evidence,
                expected_freeze_receipt_id=binding.receipt.receipt_id,
            )
        except Exception as error:
            detail = f"PEF_V1 confirmatory execution failed: {type(error).__name__}: {error}"
            finished_at = datetime.now(UTC)
            self._attempts.finish(
                pending.attempt_id,
                owner=self._worker_id,
                status=ExperimentAttemptStatus.FAILED,
                detail=detail,
                at=finished_at,
            )
            return ExperimentCycleResult(
                boundary=boundary,
                action=ExperimentCycleAction.FAILED,
                attempt=replace(pending, status=ExperimentAttemptStatus.FAILED, detail=detail),
                detail=detail,
            )

        terminal_status = (
            ExperimentAttemptStatus.DONE
            if evidence.run.status is ShadowRunStatus.RAN
            else ExperimentAttemptStatus.FAILED
        )
        detail = f"run_id={run_id} run_class={RUN_CLASS_CONFIRMATORY}"
        if terminal_status is ExperimentAttemptStatus.FAILED:
            detail += f" failure={evidence.run.failure_reason}"
        self._attempts.finish(
            pending.attempt_id,
            owner=self._worker_id,
            status=terminal_status,
            detail=detail,
            at=datetime.now(UTC),
        )
        return ExperimentCycleResult(
            boundary=boundary,
            action=(
                ExperimentCycleAction.RAN
                if terminal_status is ExperimentAttemptStatus.DONE
                else ExperimentCycleAction.FAILED
            ),
            attempt=replace(pending, status=terminal_status, detail=detail),
            run_id=run_id,
            detail=detail,
        )

    def _skip(
        self,
        pending: ExperimentRunAttempt,
        detail: str,
        *,
        at: datetime,
        boundary: datetime,
    ) -> ExperimentCycleResult:
        self._attempts.finish(
            pending.attempt_id,
            owner=self._worker_id,
            status=ExperimentAttemptStatus.SKIPPED,
            detail=detail,
            at=at,
        )
        return ExperimentCycleResult(
            boundary=boundary,
            action=ExperimentCycleAction.SKIPPED_CONFIRMATORY_GATES,
            attempt=replace(pending, status=ExperimentAttemptStatus.SKIPPED, detail=detail),
            detail=detail,
        )


__all__ = [
    "PefV1ConfirmatoryEvidence",
    "PefV1ConfirmatoryOrchestrator",
    "PefV1FreezeBinding",
    "build_pef_v1_confirmatory_evidence",
    "evaluate_pef_v1_confirmatory_gates",
]
