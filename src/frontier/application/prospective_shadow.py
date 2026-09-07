from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol, cast

from frontier.application.advanced_intelligence import (
    ShadowExperimentExecution,
    run_shadow_experiment_execution,
)
from frontier.application.candidate_freeze import collect_freeze_inputs
from frontier.application.intelligence import (
    BaselineIntelligenceRepository,
    BaselineIntelligenceRun,
    run_baseline_intelligence,
)
from frontier.domain.advanced_intelligence import (
    PefArtifact,
    PefArtifactStatus,
    ShadowExperimentRun,
)
from frontier.domain.candidate_freeze import (
    CandidateFreezeReceipt,
    FreezeStatus,
    RegistryEntryDigest,
)
from frontier.domain.digests import Digest
from frontier.domain.evaluation import SNAPSHOT_CADENCE_SECONDS
from frontier.domain.receipt import ProjectionReceipt

RANKING_WINDOW_SECONDS = 2_419_200
_FREEZE_RECEIPT_PUBLICATION_PATH_RE = re.compile(
    r"^experiments/advanced_intelligence/pef_v0/candidate_freeze_receipt_v[0-9]+\.json$"
)


class CandidateFreezeReceiptRepository(Protocol):
    def record_receipt(self, receipt: CandidateFreezeReceipt) -> None: ...


class ProspectivePefArtifactRepository(Protocol):
    def publish_complete_artifact(
        self, artifact: PefArtifact, receipt: ProjectionReceipt
    ) -> None: ...

    def record_failed_artifact(self, artifact: PefArtifact, receipt: ProjectionReceipt) -> None: ...


class ProspectiveShadowRunRepository(Protocol):
    def record_run(self, run: ShadowExperimentRun) -> None: ...

    def has_bound_run_at(self, *, as_of: datetime, candidate_freeze_receipt_id: str) -> bool: ...

    def bound_run_boundaries(
        self,
        *,
        candidate_freeze_receipt_id: str,
        start: datetime,
        end: datetime,
    ) -> tuple[datetime, ...]: ...


@dataclass(frozen=True, slots=True)
class ProspectiveShadowBoundaryResult:
    freeze_receipt: CandidateFreezeReceipt
    control: BaselineIntelligenceRun
    execution: ShadowExperimentExecution


def _parse_timestamp(value: object, *, name: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{name} must be an ISO-8601 timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return parsed


def _digest(value: object, *, name: str, optional: bool = False) -> Digest | None:
    if value is None and optional:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a digest")
    try:
        return Digest(value)
    except ValueError as error:
        raise ValueError(f"{name} must be a digest") from error


def _optional_str(value: object, *, name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string or null")
    return value


def _repo_relative_path(root: Path, path: Path) -> str:
    try:
        relative = path.resolve().relative_to(root.resolve())
    except (OSError, ValueError) as error:
        raise ValueError("candidate freeze receipt must be inside the repository root") from error
    return relative.as_posix()


def _runtime_git_delta(root: Path, implementation_commit: str | None) -> tuple[tuple[str, str], ...]:
    if implementation_commit is None:
        raise RuntimeError("candidate freeze receipt is missing implementation commit identity")
    try:
        ancestor = subprocess.run(
            ["git", "merge-base", "--is-ancestor", implementation_commit, "HEAD"],
            cwd=root,
            capture_output=True,
            check=False,
            timeout=30,
        )
        if ancestor.returncode != 0:
            raise RuntimeError(
                "frozen implementation commit is unavailable or not an ancestor of runtime HEAD"
            )
        diff = subprocess.run(
            [
                "git",
                "diff",
                "--name-status",
                "-z",
                "--no-renames",
                implementation_commit,
                "HEAD",
                "--",
            ],
            cwd=root,
            capture_output=True,
            check=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise RuntimeError("candidate freeze Git identity cannot be verified") from error

    fields = diff.stdout.split(b"\0")
    if fields and fields[-1] == b"":
        fields.pop()
    if len(fields) % 2 != 0:
        raise RuntimeError("candidate freeze Git delta is malformed")

    delta: list[tuple[str, str]] = []
    for index in range(0, len(fields), 2):
        try:
            status = fields[index].decode("ascii")
            path = fields[index + 1].decode("utf-8")
        except UnicodeDecodeError as error:
            raise RuntimeError("candidate freeze Git delta contains an undecodable path") from error
        delta.append((status, path))
    return tuple(delta)


def _require_exact_receipt_publication_delta(
    root: Path,
    receipt: CandidateFreezeReceipt,
    *,
    receipt_path: Path,
) -> None:
    expected_path = _repo_relative_path(root, receipt_path)
    if _FREEZE_RECEIPT_PUBLICATION_PATH_RE.fullmatch(expected_path) is None:
        raise ValueError("candidate freeze receipt path is not a canonical versioned publication path")
    delta = _runtime_git_delta(root, receipt.implementation_commit)
    expected_delta = (("A", expected_path),)
    if delta != expected_delta:
        observed = ", ".join(f"{status}:{path}" for status, path in delta) or "none"
        raise RuntimeError(
            "candidate implementation tree drifted outside exact freeze receipt publication; "
            f"expected A:{expected_path}; observed {observed}"
        )


def load_candidate_freeze_receipt(path: Path) -> CandidateFreezeReceipt:
    """Load an immutable canonical candidate-freeze receipt fail-closed."""
    try:
        raw = cast(object, json.loads(path.read_text(encoding="utf-8")))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"unable to load candidate freeze receipt: {path}") from error
    if not isinstance(raw, dict):
        raise ValueError("candidate freeze receipt must be a JSON object")
    document = cast(dict[str, object], raw)

    entries_raw = document.get("registry_entry_digests")
    entries: tuple[RegistryEntryDigest, ...] | None
    if entries_raw is None:
        entries = None
    elif isinstance(entries_raw, list):
        parsed_entries: list[RegistryEntryDigest] = []
        for index, item in enumerate(cast(list[object], entries_raw)):
            if not isinstance(item, dict):
                raise ValueError(f"registry_entry_digests[{index}] must be an object")
            entry = cast(dict[str, object], item)
            entry_path = entry.get("path")
            if not isinstance(entry_path, str) or not entry_path:
                raise ValueError(f"registry_entry_digests[{index}].path must be non-empty")
            entry_digest = _digest(
                entry.get("digest"), name=f"registry_entry_digests[{index}].digest"
            )
            assert entry_digest is not None
            parsed_entries.append(RegistryEntryDigest(path=entry_path, digest=entry_digest))
        entries = tuple(parsed_entries)
    else:
        raise ValueError("registry_entry_digests must be a list or null")

    drift_raw = document.get("drift_reasons")
    if not isinstance(drift_raw, list):
        raise ValueError("drift_reasons must be a list of strings")
    drift_values = cast(list[object], drift_raw)
    if not all(isinstance(item, str) for item in drift_values):
        raise ValueError("drift_reasons must be a list of strings")
    drift_reasons = tuple(cast(str, item) for item in drift_values)

    preregistration_digest = _digest(
        document.get("preregistration_digest"), name="preregistration_digest"
    )
    configuration_digest = _digest(
        document.get("configuration_digest"), name="configuration_digest"
    )
    assert preregistration_digest is not None
    assert configuration_digest is not None

    verified_raw = document.get("verified_at")
    verified_at = (
        None if verified_raw is None else _parse_timestamp(verified_raw, name="verified_at")
    )

    status_raw = document.get("status")
    if not isinstance(status_raw, str):
        raise ValueError("status must be a string")

    receipt = CandidateFreezeReceipt(
        frozen_at=_parse_timestamp(document.get("frozen_at"), name="frozen_at"),
        status=FreezeStatus(status_raw),
        drift_reasons=drift_reasons,
        preregistration_digest=preregistration_digest,
        preregistration_config_digest=_digest(
            document.get("preregistration_config_digest"),
            name="preregistration_config_digest",
            optional=True,
        ),
        implementation_commit=_optional_str(
            document.get("implementation_commit"), name="implementation_commit"
        ),
        implementation_tree_digest=_optional_str(
            document.get("implementation_tree_digest"), name="implementation_tree_digest"
        ),
        dependency_lock_digest=_digest(
            document.get("dependency_lock_digest"), name="dependency_lock_digest", optional=True
        ),
        source_registry_digest=_digest(
            document.get("source_registry_digest"), name="source_registry_digest", optional=True
        ),
        registry_entry_digests=entries,
        candidate_id=str(document.get("candidate_id", "")),
        experiment_id=str(document.get("experiment_id", "")),
        algorithm_version=str(document.get("algorithm_version", "")),
        configuration_digest=configuration_digest,
        preregistration_path=str(document.get("preregistration_path", "")),
        schema_version=str(document.get("schema_version", "")),
        verified_at=verified_at,
        original_receipt_digest=_digest(
            document.get("original_receipt_digest"),
            name="original_receipt_digest",
            optional=True,
        ),
    )
    if receipt.to_canonical() != document:
        raise ValueError("candidate freeze receipt is not the exact canonical receipt payload")
    return receipt


def require_runtime_freeze_material(
    root: Path,
    receipt: CandidateFreezeReceipt,
    *,
    receipt_path: Path,
) -> None:
    """Fail closed unless runtime material is the exact frozen implementation plus its receipt.

    The receipt binds the pre-publication implementation commit/tree. The only
    permitted tree delta at runtime is the later durable publication of this
    exact versioned receipt file. Any other tracked change means the frozen
    implementation identity has changed and requires a new freeze/restart.
    """
    inputs = collect_freeze_inputs(root)
    mismatches: list[str] = []
    if inputs.preregistration_digest != receipt.preregistration_digest:
        mismatches.append("preregistration digest")
    if inputs.preregistration_config_digest != receipt.preregistration_config_digest:
        mismatches.append("preregistration configuration digest")
    if inputs.dependency_lock_digest != receipt.dependency_lock_digest:
        mismatches.append("dependency lock digest")
    if inputs.source_registry_digest != receipt.source_registry_digest:
        mismatches.append("source registry digest")
    if inputs.registry_entry_digests != receipt.registry_entry_digests:
        mismatches.append("source registry entry digests")
    if mismatches:
        raise RuntimeError("candidate freeze material drifted: " + ", ".join(mismatches))
    _require_exact_receipt_publication_delta(root, receipt, receipt_path=receipt_path)


def first_confirmatory_boundary(durable_freeze_at: datetime) -> datetime:
    if durable_freeze_at.tzinfo is None or durable_freeze_at.utcoffset() is None:
        raise ValueError("durable_freeze_at must be timezone-aware")
    utc = durable_freeze_at.astimezone(UTC)
    epoch = int(utc.timestamp())
    boundary_epoch = (epoch // SNAPSHOT_CADENCE_SECONDS + 1) * SNAPSHOT_CADENCE_SECONDS
    return datetime.fromtimestamp(boundary_epoch, tz=UTC)


def confirmatory_window_end(durable_freeze_at: datetime) -> datetime:
    return first_confirmatory_boundary(durable_freeze_at) + timedelta(
        seconds=RANKING_WINDOW_SECONDS
    )


def require_confirmatory_boundary(*, as_of: datetime, durable_freeze_at: datetime) -> None:
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("as_of must be timezone-aware")
    as_of_utc = as_of.astimezone(UTC)
    if as_of_utc.microsecond != 0 or int(as_of_utc.timestamp()) % SNAPSHOT_CADENCE_SECONDS != 0:
        raise ValueError("as_of must align to a UTC epoch multiple of 300 seconds")
    start = first_confirmatory_boundary(durable_freeze_at)
    end = start + timedelta(seconds=RANKING_WINDOW_SECONDS)
    if as_of_utc < start or as_of_utc >= end:
        raise ValueError("as_of is outside the fixed preregistered ranking window")


def due_confirmatory_boundaries(
    *,
    durable_freeze_at: datetime,
    now: datetime,
    existing_boundaries: tuple[datetime, ...],
) -> tuple[datetime, ...]:
    """Return missing fixed-window boundaries that can be reconstructed PIT now."""
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    start = first_confirmatory_boundary(durable_freeze_at)
    end = start + timedelta(seconds=RANKING_WINDOW_SECONDS)
    normalized = tuple(item.astimezone(UTC) for item in existing_boundaries)
    if len(set(normalized)) != len(normalized):
        raise RuntimeError("duplicate bound shadow runs exist for a confirmatory boundary")
    existing = set(normalized)
    now_utc = now.astimezone(UTC)
    latest_due_epoch = (
        int(now_utc.timestamp()) // SNAPSHOT_CADENCE_SECONDS
    ) * SNAPSHOT_CADENCE_SECONDS
    latest_due = datetime.fromtimestamp(latest_due_epoch, tz=UTC)
    due: list[datetime] = []
    boundary = start
    while boundary < end and boundary <= latest_due:
        if boundary not in existing:
            due.append(boundary)
        boundary += timedelta(seconds=SNAPSHOT_CADENCE_SECONDS)
    return tuple(due)


def run_confirmatory_shadow_boundary(
    *,
    baseline_repository: BaselineIntelligenceRepository,
    pef_repository: ProspectivePefArtifactRepository,
    shadow_repository: ProspectiveShadowRunRepository,
    freeze_repository: CandidateFreezeReceiptRepository,
    freeze_receipt: CandidateFreezeReceipt,
    durable_freeze_at: datetime,
    as_of: datetime,
    generated_at: datetime,
    source_registry_version: Digest,
) -> ProspectiveShadowBoundaryResult:
    """Append one fixed-window paired PEF snapshot without shifting its boundary."""
    require_confirmatory_boundary(as_of=as_of, durable_freeze_at=durable_freeze_at)
    if generated_at.tzinfo is None or generated_at.utcoffset() is None:
        raise ValueError("generated_at must be timezone-aware")
    if generated_at < as_of:
        raise ValueError("generated_at cannot precede the paired snapshot boundary")
    if freeze_receipt.status is not FreezeStatus.FROZEN:
        raise ValueError("confirmatory shadow run requires a FROZEN candidate receipt")
    if shadow_repository.has_bound_run_at(
        as_of=as_of,
        candidate_freeze_receipt_id=freeze_receipt.receipt_id,
    ):
        raise RuntimeError("a bound shadow run already exists for this confirmatory boundary")

    freeze_repository.record_receipt(freeze_receipt)
    control = run_baseline_intelligence(
        baseline_repository,
        as_of=as_of,
        generated_at=generated_at,
        source_registry_version=source_registry_version,
    )
    observations = tuple(baseline_repository.list_baseline_observations_as_of(as_of))
    execution = run_shadow_experiment_execution(
        observations,
        control_snapshot=control.snapshot,
        control_receipt=control.receipt,
        generated_at=generated_at,
        source_registry_version=source_registry_version,
        candidate_freeze_receipt=freeze_receipt,
    )
    if execution.candidate.artifact.status is PefArtifactStatus.RAN:
        pef_repository.publish_complete_artifact(
            execution.candidate.artifact, execution.candidate.receipt
        )
    elif execution.candidate.artifact.status is PefArtifactStatus.FAILED:
        pef_repository.record_failed_artifact(
            execution.candidate.artifact, execution.candidate.receipt
        )
    else:
        raise RuntimeError("confirmatory candidate artifact must be RAN or FAILED")
    shadow_repository.record_run(execution.run)
    return ProspectiveShadowBoundaryResult(
        freeze_receipt=freeze_receipt,
        control=control,
        execution=execution,
    )
