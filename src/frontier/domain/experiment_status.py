"""Coherent scientific evaluation status model for PEF_V0 (WP6, G4).

A single, framework-independent read projection over stored experiment state
(runs, attempts, freeze receipts, opportunity anchors/outcome resolutions, and
preregistered evaluation receipts). This module owns NO intelligence authority:

- it is a pure rendering of stored state; it never recomputes thresholds,
  statistics, or evaluation semantics;
- preregistered sample-adequacy thresholds are surfaced VERBATIM from
  :data:`~frontier.domain.evaluation.EVALUATION_CONFIGURATION`;
- missing data is an explicit ``NO_DATA``/``UNAVAILABLE``/``UNBOUND`` state —
  NEVER zero and never a coerced ``UNKNOWN`` (R4);
- a failed candidate execution renders FAILED, never an empty ranking;
- a DRIFTED freeze renders ``INVALID_DRIFT`` drift state and never
  confirmatory status.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from .advanced_intelligence import PEF_CANDIDATE_ID, PEF_CONFIGURATION_DIGEST, PEF_EXPERIMENT_ID
from .evaluation import EVALUATION_CONFIGURATION, QUALIFYING_DOMAINS
from .health import HealthValue

EXPERIMENT_STATUS_SCHEMA_VERSION = "experiment-status-v0"
EXPERIMENT_STATUS_AUTHORITY_STATE = "EXPERIMENTAL_SHADOW"
EXPERIMENT_STATUS_INTERPRETATION = (
    "EXPERIMENTAL_SHADOW scientific status surface: identities, digests, "
    "counts, and stored statuses only; never baseline authority, never truth "
    "or confidence; thresholds are surfaced verbatim, never recomputed"
)

# Explicit rendering states (R4): absence is never coerced into data.
STATE_AVAILABLE = "AVAILABLE"
STATE_NO_DATA = "NO_DATA"
STATE_UNAVAILABLE = "UNAVAILABLE"
STATE_UNKNOWN = "UNKNOWN"

WINDOW_STATE_OPEN = "OPEN"
WINDOW_STATE_NO_DATA = "NO_DATA"

FREEZE_STATE_BOUND = "BOUND"
FREEZE_STATE_UNBOUND = "UNBOUND"
FREEZE_STATE_NOT_DURABLE = "NOT_DURABLE"
FREEZE_STATE_DRIFTED = "DRIFTED"

DRIFT_STATE_OK = "OK"
DRIFT_STATE_INVALID_DRIFT = "INVALID_DRIFT"

NONINFERIORITY_PASS = "PASS"
NONINFERIORITY_FAIL = "FAIL"

# Preregistered evaluation receipt statuses, rendered verbatim (never mapped).
EVALUATION_RECEIPT_STATUSES: frozenset[str] = frozenset(
    {"COMPLETE", "INSUFFICIENT_SAMPLE", "FAILED", "INVALID_DRIFT"}
)

# Canonical domain-stratum presentation order: qualifying taxonomy first.
DOMAIN_PRESENTATION_ORDER: tuple[str, ...] = (
    *QUALIFYING_DOMAINS,
    "UNQUALIFIED_MIXED",
    "UNQUALIFIED",
)


def preregistered_sample_adequacy_thresholds() -> dict[str, object]:
    """Preregistration sample-adequacy thresholds VERBATIM (never recomputed).

    Returns an independent copy of the digest-bound preregistration
    ``sample_adequacy`` configuration; mutation by a caller can never drift
    the frozen evaluation configuration itself.
    """
    thresholds = EVALUATION_CONFIGURATION["sample_adequacy"]
    if not isinstance(thresholds, dict):  # pragma: no cover - frozen constant
        raise ValueError("preregistration sample adequacy thresholds are not a mapping")
    return dict(thresholds)


def worst_coverage_state(coverage: CoverageHealthStatus) -> str:
    """Worst-of coverage health across the four control lanes (R4).

    ``UNKNOWN`` is never coerced into ``OK``: it is the explicit rendering when
    any lane is UNKNOWN and no lane is worse.
    """
    ranking = {
        HealthValue.OK: 0,
        HealthValue.DEGRADED: 1,
        HealthValue.FAILED: 2,
        HealthValue.UNKNOWN: 3,
    }
    states = (
        HealthValue(coverage.transport_state),
        HealthValue(coverage.freshness_state),
        HealthValue(coverage.completeness_state),
        HealthValue(coverage.schema_state),
    )
    return max(states, key=lambda item: ranking[item]).value


@dataclass(frozen=True, slots=True)
class BoundFreezeStatus:
    """Bound candidate-freeze receipt inputs (None fields are never guessed).

    ``durable_freeze_at`` is ``None`` exactly when the freeze is not durable in
    the canonical authority (legacy or non-durable rows): it must render
    ``NOT_DURABLE``, never silently durable (R4).
    """

    receipt_id: str
    status: str
    durable_freeze_at: str | None
    implementation_commit: str | None
    implementation_tree_digest: str | None
    source_registry_digest: str | None
    frozen_at: str | None


@dataclass(frozen=True, slots=True)
class WindowBoundaryStatus:
    """Ranking-window boundary projection (window_start / latest boundary).

    ``window_start`` is the earliest stored run boundary and
    ``latest_boundary_as_of`` the latest stored run boundary; both ``None``
    means NO_DATA (no boundary was ever executed).
    """

    window_start: str | None
    latest_boundary_as_of: str | None
    latest_attempt_status: str | None = None
    latest_attempt_detail: str | None = None

    def __post_init__(self) -> None:
        if self.window_start is None and self.latest_boundary_as_of is not None:
            raise ValueError("latest boundary without a window start is inconsistent")
        if self.window_start is not None and self.latest_boundary_as_of is None:
            raise ValueError("window start without a latest boundary is inconsistent")


@dataclass(frozen=True, slots=True)
class LatestRunStatus:
    """Latest paired shadow-run lifecycle state (verbatim, R8)."""

    run_id: str
    status: str
    run_class: str | None = None


@dataclass(frozen=True, slots=True)
class CoverageHealthStatus:
    """Control coverage health of the latest paired boundary (R4).

    ``UNKNOWN`` never coerces into ``OK`` or into a count: it renders as-is.
    """

    transport_state: str
    freshness_state: str
    completeness_state: str
    schema_state: str


@dataclass(frozen=True, slots=True)
class DomainOpportunityCounts:
    """Anchor-derived opportunity accounting for one domain stratum.

    Counts are derived ONLY from opportunity anchors and outcome resolutions;
    an empty anchor set yields zeros by construction (no fabricated anchors),
    and ``UNKNOWN`` coverage is counted as ``unknown``/``unresolved_coverage``
    — never coerced into a resolved negative.
    """

    domain: str
    anchor_count: int
    resolved_positive_count: int
    resolved_negative_count: int
    unresolved_coverage_count: int
    unknown_count: int
    excluded_count: int
    pending_count: int


@dataclass(frozen=True, slots=True)
class DomainEvaluationStatusRow:
    """Per-domain row rendered from the stored evaluation receipt (verbatim).

    ``None`` statistics are the receipt's own absent values; they are never
    filled with zeros or recomputed.
    """

    domain: str
    candidate_precision: str | None
    candidate_surfaced_resolved: int | None
    candidate_positive_surfaced_resolved: int | None
    control_precision: str | None
    control_surfaced_resolved: int | None
    control_positive_surfaced_resolved: int | None
    difference_lower_bound: str | None
    noninferiority_pass: bool | None
    median_lead_time_advantage_seconds: str | None
    qualifies_sample_adequacy: bool | None


@dataclass(frozen=True, slots=True)
class EvaluationStatisticsStatus:
    """Latest preregistered evaluation receipt's status and stored statistics."""

    evaluation_id: str
    status: str
    freeze_status: str | None
    verdict: str | None
    status_reason: str | None
    pooled_median_lead_time_advantage_seconds: str | None
    domains: tuple[DomainEvaluationStatusRow, ...]


@dataclass(frozen=True, slots=True)
class ArmPrecisionStatus:
    """One arm's precision rendering with an explicit availability state.

    ``precision`` is ``None`` whenever the arm surfaced no resolved
    opportunity: an empty arm has no defined proportion and is NEVER rendered
    as zero.
    """

    state: str
    precision: str | None
    surfaced_resolved: int | None
    positive_surfaced_resolved: int | None


@dataclass(frozen=True, slots=True)
class NonInferiorityStatus:
    """Non-inferiority result rendering (PASS/FAIL/UNAVAILABLE/NO_DATA)."""

    state: str
    lower_bound: str | None
    margin: str


@dataclass(frozen=True, slots=True)
class LeadTimeStatus:
    """Lead-time rendering: only the stored delta median is available.

    Arm-specific medians are not stored in the receipt and stay
    ``UNAVAILABLE`` — never fabricated from the delta (R4).
    """

    state: str
    candidate_median_lead_time_seconds: str | None
    baseline_median_lead_time_seconds: str | None
    delta_median_advantage_seconds: str | None


@dataclass(frozen=True, slots=True)
class ExperimentStatus:
    """Single coherent scientific evaluation status (fail-closed rendering)."""

    schema_version: str = EXPERIMENT_STATUS_SCHEMA_VERSION
    experiment_id: str = PEF_EXPERIMENT_ID
    candidate_id: str = PEF_CANDIDATE_ID
    configuration_digest: str = str(PEF_CONFIGURATION_DIGEST)
    candidate_freeze_receipt_id: str | None = None
    candidate_freeze_state: str = FREEZE_STATE_UNBOUND
    implementation_commit: str | None = None
    implementation_tree_digest: str | None = None
    implementation_state: str = STATE_UNAVAILABLE
    source_registry_digest: str | None = None
    source_registry_state: str = STATE_UNAVAILABLE
    window_state: str = WINDOW_STATE_NO_DATA
    window_start: str | None = None
    latest_boundary_as_of: str | None = None
    latest_attempt_status: str | None = None
    latest_attempt_detail: str | None = None
    latest_run_id: str | None = None
    latest_run_status: str | None = None
    run_state: str = STATE_NO_DATA
    coverage_state: str = STATE_NO_DATA
    opportunity_counts: tuple[DomainOpportunityCounts, ...] = ()
    qualifying_opportunity_counts: tuple[DomainOpportunityCounts, ...] = ()
    sample_adequacy_thresholds: Mapping[str, object] = field(
        default_factory=preregistered_sample_adequacy_thresholds
    )
    domain_evaluation_rows: tuple[DomainEvaluationStatusRow, ...] = ()
    candidate_precision: ArmPrecisionStatus = ArmPrecisionStatus(
        state=STATE_UNAVAILABLE,
        precision=None,
        surfaced_resolved=None,
        positive_surfaced_resolved=None,
    )
    baseline_precision: ArmPrecisionStatus = ArmPrecisionStatus(
        state=STATE_UNAVAILABLE,
        precision=None,
        surfaced_resolved=None,
        positive_surfaced_resolved=None,
    )
    noninferiority: NonInferiorityStatus = NonInferiorityStatus(
        state=STATE_NO_DATA,
        lower_bound=None,
        margin=str(EVALUATION_CONFIGURATION["noninferiority_margin"]),
    )
    lead_time: LeadTimeStatus = LeadTimeStatus(
        state=STATE_NO_DATA,
        candidate_median_lead_time_seconds=None,
        baseline_median_lead_time_seconds=None,
        delta_median_advantage_seconds=None,
    )
    evaluation_receipt_status: str | None = None
    evaluation_receipt_state: str = STATE_NO_DATA
    drift_state: str = DRIFT_STATE_OK
