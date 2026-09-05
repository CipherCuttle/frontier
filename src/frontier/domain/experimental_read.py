"""EXPERIMENTAL_SHADOW read models for the public read plane (slice G).

Read-only summary surfaces over stored EXPERIMENTAL advanced-intelligence
outputs (shadow experiment runs, PEF_V0 candidate artifacts, preregistered
evaluation receipts, advanced feature-vector batches, and experimental
analysis artifacts). This module owns no intelligence authority:

- every model is explicitly labelled ``EXPERIMENTAL_SHADOW`` (R7);
- identity is never hidden: run/artifact/receipt ids, digests, configuration
  digests, snapshot bindings, and ``as_of`` are always visible (R8);
- no scalar score, confidence, confirmation, truth, or verdict-escalation key
  can appear in any summary;
- missing data is an explicit ``NO_DATA`` state and an unavailable repository
  is an explicit ``UNKNOWN`` state — neither is ever coerced into fabricated
  data (R4);
- the baseline read plane is untouched: nothing here writes or reranks.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .advanced_intelligence import PEF_CANDIDATE_ID, PEF_CONFIGURATION_DIGEST, PEF_EXPERIMENT_ID
from .experimental_analysis import ExperimentalAnalysisKind

EXPERIMENTAL_READ_SCHEMA_VERSION = "experimental-read-response-v0"
EXPERIMENTAL_READ_AUTHORITY_STATE = "EXPERIMENTAL_SHADOW"
EXPERIMENTAL_READ_INTERPRETATION = (
    "EXPERIMENTAL_SHADOW read surface: identities, digests, and statuses only; "
    "never baseline authority, never truth, confidence, or independent "
    "confirmation; every item is hypothesis-level experimental output"
)
EXPERIMENTAL_READ_UNKNOWN = "UNKNOWN"
EXPERIMENTAL_READ_AVAILABLE = "AVAILABLE"
EXPERIMENTAL_READ_NO_DATA = "NO_DATA"

SECTION_SHADOW_RUN = "shadow_run"
SECTION_PEF_ARTIFACT = "pef_artifact"
SECTION_EVALUATION_RECEIPT = "evaluation_receipt"
SECTION_FEATURE_BATCH = "feature_batch"
SECTION_ANALYSIS_PREFIX = "analysis:"


class ExperimentalReadFailure(RuntimeError):
    """Framework-independent experimental read failure (transport maps codes)."""

    code: str


class InvalidExperimentalAsOfError(ExperimentalReadFailure):
    code = "INVALID_AS_OF"


class InvalidExperimentalAnalysisKindError(ExperimentalReadFailure):
    code = "INVALID_ANALYSIS_KIND"


@dataclass(frozen=True, slots=True)
class ShadowRunSummary:
    """Identity surface of the latest paired shadow experiment run (R7, R8)."""

    run_id: str
    run_digest: str
    experiment_id: str
    candidate_id: str
    schema_version: str
    algorithm_version: str
    configuration_digest: str
    authority_state: str
    status: str
    as_of: str
    generated_at: str
    control_snapshot_id: str
    control_receipt_id: str
    candidate_artifact_id: str
    candidate_output_digest: str
    episode_universe_digest: str
    candidate_freeze_receipt_id: str | None
    failure_reason: str | None


@dataclass(frozen=True, slots=True)
class PefArtifactSummary:
    """Identity surface of the latest PEF_V0 candidate artifact (R7, R8)."""

    artifact_id: str
    output_digest: str
    receipt_id: str
    status: str
    as_of: str
    generated_at: str
    experiment_id: str
    candidate_id: str
    schema_version: str
    algorithm_version: str
    ranking_policy_version: str
    configuration_digest: str
    authority_state: str
    control_snapshot_id: str
    control_receipt_id: str
    episode_count: int | None
    failure_reason: str | None


@dataclass(frozen=True, slots=True)
class EvaluationReceiptSummary:
    """Identity surface of the latest preregistered evaluation receipt (R8)."""

    evaluation_id: str
    receipt_digest: str
    status: str
    as_of: str
    generated_at: str
    experiment_id: str
    candidate_id: str
    schema_version: str
    evaluation_algorithm_version: str
    candidate_configuration_digest: str
    evaluation_configuration_digest: str
    authority_state: str
    candidate_freeze_receipt_id: str
    freeze_receipt_digest: str
    freeze_status: str
    preregistration_digest: str
    shadow_run_ids: tuple[str, ...]
    status_reason: str | None
    verdict: str | None


@dataclass(frozen=True, slots=True)
class FeatureBatchSummary:
    """Identity surface of the latest EXPERIMENTAL feature-vector batch (R8)."""

    batch_id: str
    batch_digest: str
    status: str
    as_of: str
    generated_at: str
    control_snapshot_id: str
    control_receipt_id: str
    episode_universe_digest: str
    configuration_digest: str
    schema_version: str
    algorithm_version: str
    authority_state: str
    vector_count: int | None


@dataclass(frozen=True, slots=True)
class AnalysisArtifactSummary:
    """Identity surface of one stored EXPERIMENTAL analysis artifact (R7, R8)."""

    analysis_id: str
    kind: str
    status: str
    authority_state: str
    as_of: str
    generated_at: str
    configuration_digest: str
    output_digest: str
    schema_version: str
    algorithm_version: str
    control_snapshot_id: str | None
    control_receipt_id: str | None
    source_registry_version: str | None
    episode_universe_digest: str | None
    input_digest: str | None


@dataclass(frozen=True, slots=True)
class ExperimentalOverview:
    """Labelled EXPERIMENTAL_SHADOW envelope over latest stored experiment items.

    ``availability`` is explicit per section (``AVAILABLE`` / ``NO_DATA`` /
    ``UNKNOWN``); ``NO_DATA`` sections carry a ``None`` summary, and ``UNKNOWN``
    means the repository could not answer — never fabricated data (R4).
    """

    schema_version: str
    authority_state: str
    interpretation: str
    experiment_id: str
    candidate_id: str
    configuration_digest: str
    as_of: str
    generated_at: str
    availability: dict[str, str]
    latest_shadow_run: ShadowRunSummary | None
    latest_pef_artifact: PefArtifactSummary | None
    latest_evaluation_receipt: EvaluationReceiptSummary | None
    latest_feature_batch: FeatureBatchSummary | None
    analysis_artifacts: dict[ExperimentalAnalysisKind, AnalysisArtifactSummary]


def parse_experimental_as_of(value: str) -> datetime:
    """Parse a canonical ``frontier-canonical-json-v1`` UTC timestamp (R1).

    Accepts exactly ``YYYY-MM-DDTHH:MM:SS[.ffffff]Z``; anything else fails
    closed with :class:`InvalidExperimentalAsOfError`.
    """
    if not value.endswith("Z"):
        raise InvalidExperimentalAsOfError("as_of must be a canonical UTC timestamp")
    try:
        return datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise InvalidExperimentalAsOfError("as_of must be a canonical UTC timestamp") from exc


def parse_experimental_analysis_kind(value: str) -> ExperimentalAnalysisKind:
    """Validate an analysis-kind path parameter against the frozen kinds."""
    try:
        return ExperimentalAnalysisKind(value)
    except ValueError as exc:
        raise InvalidExperimentalAnalysisKindError(
            "unknown experimental analysis artifact kind"
        ) from exc


def section_key(kind: ExperimentalAnalysisKind) -> str:
    return SECTION_ANALYSIS_PREFIX + kind.value


def experimental_availability(item: object | None, *, failed: bool) -> str:
    """Explicit per-section availability (R4): never fabricated, never silent."""
    if failed:
        return EXPERIMENTAL_READ_UNKNOWN
    if item is None:
        return EXPERIMENTAL_READ_NO_DATA
    return EXPERIMENTAL_READ_AVAILABLE


def build_experimental_overview(
    *,
    as_of: str | None,
    shadow_run: ShadowRunSummary | None,
    pef_artifact: PefArtifactSummary | None,
    evaluation_receipt: EvaluationReceiptSummary | None,
    feature_batch: FeatureBatchSummary | None,
    analysis_artifacts: dict[ExperimentalAnalysisKind, AnalysisArtifactSummary],
    shadow_run_failed: bool,
    pef_artifact_failed: bool,
    evaluation_receipt_failed: bool,
    feature_batch_failed: bool,
    analysis_failed: bool,
) -> ExperimentalOverview:
    """Assemble the deterministic EXPERIMENTAL_SHADOW overview envelope."""
    resolved_as_of = as_of
    if resolved_as_of is None:
        candidates = [
            item.as_of
            for item in (shadow_run, pef_artifact, evaluation_receipt, feature_batch)
            if item is not None
        ]
        candidates.extend(item.as_of for item in analysis_artifacts.values())
        resolved_as_of = max(candidates) if candidates else EXPERIMENTAL_READ_UNKNOWN

    generated_candidates = [
        item.generated_at
        for item in (shadow_run, pef_artifact, evaluation_receipt, feature_batch)
        if item is not None
    ]
    resolved_generated_at = (
        max(generated_candidates) if generated_candidates else EXPERIMENTAL_READ_UNKNOWN
    )

    availability: dict[str, str] = {
        SECTION_SHADOW_RUN: experimental_availability(shadow_run, failed=shadow_run_failed),
        SECTION_PEF_ARTIFACT: experimental_availability(pef_artifact, failed=pef_artifact_failed),
        SECTION_EVALUATION_RECEIPT: experimental_availability(
            evaluation_receipt, failed=evaluation_receipt_failed
        ),
        SECTION_FEATURE_BATCH: experimental_availability(
            feature_batch, failed=feature_batch_failed
        ),
    }
    for kind in ExperimentalAnalysisKind:
        summary = analysis_artifacts.get(kind)
        availability[section_key(kind)] = experimental_availability(summary, failed=analysis_failed)

    return ExperimentalOverview(
        schema_version=EXPERIMENTAL_READ_SCHEMA_VERSION,
        authority_state=EXPERIMENTAL_READ_AUTHORITY_STATE,
        interpretation=EXPERIMENTAL_READ_INTERPRETATION,
        experiment_id=PEF_EXPERIMENT_ID,
        candidate_id=PEF_CANDIDATE_ID,
        configuration_digest=str(PEF_CONFIGURATION_DIGEST),
        as_of=resolved_as_of,
        generated_at=resolved_generated_at,
        availability=availability,
        latest_shadow_run=shadow_run,
        latest_pef_artifact=pef_artifact,
        latest_evaluation_receipt=evaluation_receipt,
        latest_feature_batch=feature_batch,
        analysis_artifacts=dict(analysis_artifacts),
    )
