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
from .canonical_json import CanonicalValue
from .experiment_status import DomainEvaluationStatusRow, ExperimentStatus
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
EXPERIMENTAL_READ_UNAVAILABLE = "UNAVAILABLE"
EXPERIMENTAL_READ_AS_OF_SINGLE_BOUNDARY = "SINGLE_BOUNDARY"
EXPERIMENTAL_READ_AS_OF_MIXED_BOUNDARIES = "MIXED_BOUNDARIES"
EXPERIMENTAL_READ_INVALID_LIMIT = "INVALID_LIMIT"
HISTORY_LIMIT_DEFAULT = 50
HISTORY_LIMIT_MAX = 200

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


class InvalidExperimentalLimitError(ExperimentalReadFailure):
    code = "INVALID_LIMIT"


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
class ControlRankEntry:
    """One control-arm per-episode rank entry (deterministic, R8)."""

    episode_id: str
    rank: int


@dataclass(frozen=True, slots=True)
class ShadowRunDetail:
    """Full run record incl. bindings, run_class, and coverage state (R7, R8)."""

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
    run_class: str | None
    coverage_state: str
    control_ranking: tuple[ControlRankEntry, ...]


@dataclass(frozen=True, slots=True)
class EvaluationDetail:
    """Full evaluation receipt incl. stored per-domain rows (R8)."""

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
    domains: tuple[DomainEvaluationStatusRow, ...]


@dataclass(frozen=True, slots=True)
class RunHistoryEntry:
    """One bounded-history run row (deterministic ordering, R8)."""

    run_id: str
    run_digest: str
    run_class: str | None
    status: str
    as_of: str


@dataclass(frozen=True, slots=True)
class EvaluationHistoryEntry:
    """One bounded-history evaluation row (deterministic ordering, R8)."""

    evaluation_id: str
    status: str
    as_of: str


@dataclass(frozen=True, slots=True)
class ExperimentHistory:
    """Bounded, deterministically ordered run/evaluation history (R4, R8)."""

    schema_version: str
    authority_state: str
    interpretation: str
    experiment_id: str
    candidate_id: str
    availability: str
    limit: int
    runs: tuple[RunHistoryEntry, ...]
    evaluations: tuple[EvaluationHistoryEntry, ...]


@dataclass(frozen=True, slots=True)
class EpisodeComparison:
    """Per-episode comparison for one paired run (R1, R4, R7, R8).

    Mixed-identity protection: the envelope always carries the exact
    ``run_id``, ``control_snapshot_id``, ``candidate_freeze_receipt_id``
    (or ``None``), and the evaluation state it was derived from — clients can
    never mix snapshots invisibly. Absent ranks are explicit
    ``UNAVAILABLE``/``NO_DATA`` states and are NEVER rendered as zero.
    """

    schema_version: str
    authority_state: str
    interpretation: str
    availability: str
    episode_id: str
    as_of: str | None
    run_id: str | None
    run_status: str | None
    run_failure_reason: str | None
    control_snapshot_id: str | None
    candidate_freeze_receipt_id: str | None
    evaluation_receipt_id: str | None
    evaluation_receipt_status: str | None
    evaluation_state: str
    baseline_rank_state: str
    baseline_rank: int | None
    candidate_rank_state: str
    candidate_rank: int | None
    rank_delta_state: str
    rank_delta: int | None
    candidate_components_state: str
    candidate_components: dict[str, CanonicalValue] | None
    feature_availability: str
    feature_interpretation_state: str
    feature_interpretation: str | None
    feature_values: list[dict[str, CanonicalValue]]


@dataclass(frozen=True, slots=True)
class RunDetailSection:
    """Explicit availability + full run record (R4, R7, R8)."""

    availability: str
    run: ShadowRunDetail | None


@dataclass(frozen=True, slots=True)
class EvaluationDetailSection:
    """Explicit availability + full evaluation receipt (R4, R8)."""

    availability: str
    evaluation: EvaluationDetail | None


@dataclass(frozen=True, slots=True)
class ExperimentStatusSurface:
    """WP6 operator state with an explicit availability state (R4, R8)."""

    availability: str
    status: ExperimentStatus | None


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
    as_of_consistency: str
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

    section_as_ofs = {
        item.as_of
        for item in (shadow_run, pef_artifact, evaluation_receipt, feature_batch)
        if item is not None
    }
    section_as_ofs.update(item.as_of for item in analysis_artifacts.values())
    any_section_failed = (
        shadow_run_failed
        or pef_artifact_failed
        or evaluation_receipt_failed
        or feature_batch_failed
        or analysis_failed
    )
    if any_section_failed:
        as_of_consistency = EXPERIMENTAL_READ_UNKNOWN
    elif not section_as_ofs:
        as_of_consistency = EXPERIMENTAL_READ_NO_DATA
    elif len(section_as_ofs) == 1:
        as_of_consistency = EXPERIMENTAL_READ_AS_OF_SINGLE_BOUNDARY
    else:
        as_of_consistency = EXPERIMENTAL_READ_AS_OF_MIXED_BOUNDARIES

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
        as_of_consistency=as_of_consistency,
        generated_at=resolved_generated_at,
        availability=availability,
        latest_shadow_run=shadow_run,
        latest_pef_artifact=pef_artifact,
        latest_evaluation_receipt=evaluation_receipt,
        latest_feature_batch=feature_batch,
        analysis_artifacts=dict(analysis_artifacts),
    )


def _absent_comparison(*, episode_id: str, availability: str) -> EpisodeComparison:
    """Explicit absent comparison envelope (R4): no ranks, never zeros."""
    return EpisodeComparison(
        schema_version=EXPERIMENTAL_READ_SCHEMA_VERSION,
        authority_state=EXPERIMENTAL_READ_AUTHORITY_STATE,
        interpretation=EXPERIMENTAL_READ_INTERPRETATION,
        availability=availability,
        episode_id=episode_id,
        as_of=None,
        run_id=None,
        run_status=None,
        run_failure_reason=None,
        control_snapshot_id=None,
        candidate_freeze_receipt_id=None,
        evaluation_receipt_id=None,
        evaluation_receipt_status=None,
        evaluation_state=EXPERIMENTAL_READ_NO_DATA,
        baseline_rank_state=EXPERIMENTAL_READ_UNAVAILABLE,
        baseline_rank=None,
        candidate_rank_state=EXPERIMENTAL_READ_UNAVAILABLE,
        candidate_rank=None,
        rank_delta_state=EXPERIMENTAL_READ_UNAVAILABLE,
        rank_delta=None,
        candidate_components_state=EXPERIMENTAL_READ_UNAVAILABLE,
        candidate_components=None,
        feature_availability=EXPERIMENTAL_READ_UNAVAILABLE,
        feature_interpretation_state=EXPERIMENTAL_READ_UNAVAILABLE,
        feature_interpretation=None,
        feature_values=[],
    )


def build_unavailable_comparison(episode_id: str) -> EpisodeComparison:
    """Repository could not answer: explicit ``UNKNOWN``, never fabricated."""
    return _absent_comparison(episode_id=episode_id, availability=EXPERIMENTAL_READ_UNKNOWN)


def build_no_data_comparison(episode_id: str) -> EpisodeComparison:
    """No comparison data exists for this episode: explicit ``NO_DATA``."""
    return _absent_comparison(episode_id=episode_id, availability=EXPERIMENTAL_READ_NO_DATA)
