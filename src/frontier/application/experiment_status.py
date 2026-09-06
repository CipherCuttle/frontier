"""Application service assembling the coherent experiment status (WP6, G4).

:func:`build_experiment_status` folds stored experiment state inputs (latest
paired run, window boundaries, latest attempt, bound freeze receipt, anchor
counts, coverage health, and the latest preregistered evaluation receipt) into
a single fail-closed :class:`~frontier.domain.experiment_status.ExperimentStatus`
projection. Read-only: no LLM, no canonical authority, no recomputation of
preregistered thresholds or evaluation semantics.
"""

from __future__ import annotations

from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from typing import cast

from frontier.domain.evaluation import EVALUATION_CONFIGURATION
from frontier.domain.experiment_status import (
    DOMAIN_PRESENTATION_ORDER,
    DRIFT_STATE_INVALID_DRIFT,
    DRIFT_STATE_OK,
    EVALUATION_RECEIPT_STATUSES,
    FREEZE_STATE_BOUND,
    FREEZE_STATE_DRIFTED,
    FREEZE_STATE_NOT_DURABLE,
    FREEZE_STATE_UNBOUND,
    NONINFERIORITY_FAIL,
    NONINFERIORITY_PASS,
    STATE_AVAILABLE,
    STATE_NO_DATA,
    STATE_UNAVAILABLE,
    WINDOW_STATE_NO_DATA,
    WINDOW_STATE_OPEN,
    ArmPrecisionStatus,
    BoundFreezeStatus,
    CoverageHealthStatus,
    DomainEvaluationStatusRow,
    DomainOpportunityCounts,
    EvaluationStatisticsStatus,
    ExperimentStatus,
    LatestRunStatus,
    LeadTimeStatus,
    NonInferiorityStatus,
    WindowBoundaryStatus,
    preregistered_sample_adequacy_thresholds,
    worst_coverage_state,
)

NONINFERIORITY_MARGIN = str(EVALUATION_CONFIGURATION["noninferiority_margin"])
FAILED_RUN_STATUS = "FAILED"

_DECIMAL_CONTEXT_PRECISION = 34
_DECIMAL_QUANT = Decimal("0.000000000001")


def _quantize(value: Decimal) -> Decimal:
    with localcontext() as ctx:
        ctx.prec = _DECIMAL_CONTEXT_PRECISION
        ctx.rounding = ROUND_HALF_EVEN
        return value.quantize(_DECIMAL_QUANT)


def _precision_from_counts(surfaced: int | None, positive: int | None) -> ArmPrecisionStatus:
    """Render one arm's precision from receipt counts (never zero coercion).

    An empty arm (no surfaced resolved opportunities) has NO defined
    proportion: it renders ``UNAVAILABLE`` with ``precision=None`` — never 0.
    """
    if surfaced is None or positive is None or surfaced <= 0:
        return ArmPrecisionStatus(
            state=STATE_UNAVAILABLE,
            precision=None,
            surfaced_resolved=surfaced,
            positive_surfaced_resolved=positive,
        )
    precision = _quantize(Decimal(positive) / Decimal(surfaced))
    return ArmPrecisionStatus(
        state=STATE_AVAILABLE,
        precision=str(precision),
        surfaced_resolved=surfaced,
        positive_surfaced_resolved=positive,
    )


def _pooled_arm_counts(
    rows: tuple[DomainEvaluationStatusRow, ...], *, candidate: bool
) -> tuple[int | None, int | None]:
    """Sum the receipt's OWN stored per-arm counts (read projection only).

    Any missing stored count leaves the pooled arm unavailable — never zero.
    """
    if candidate:
        surfaced = [row.candidate_surfaced_resolved for row in rows]
        positive = [row.candidate_positive_surfaced_resolved for row in rows]
    else:
        surfaced = [row.control_surfaced_resolved for row in rows]
        positive = [row.control_positive_surfaced_resolved for row in rows]
    if any(item is None for item in surfaced) or any(item is None for item in positive):
        return (None, None)
    return (
        sum(cast("int", item) for item in surfaced),
        sum(cast("int", item) for item in positive),
    )


def _noninferiority_from_rows(
    rows: tuple[DomainEvaluationStatusRow, ...],
) -> NonInferiorityStatus:
    """Non-inferiority rendering of the receipt's stored per-domain booleans.

    A status rendering, never a recomputation of the preregistered interval:
    any missing stored boolean leaves the result explicitly ``UNAVAILABLE``.
    """
    lower_bounds = [row.difference_lower_bound for row in rows]
    lower_bound = lower_bounds[0] if len(lower_bounds) == 1 else None
    if not rows:
        return NonInferiorityStatus(
            state=STATE_NO_DATA, lower_bound=None, margin=NONINFERIORITY_MARGIN
        )
    passes = [row.noninferiority_pass for row in rows]
    if any(item is None for item in passes):
        return NonInferiorityStatus(
            state=STATE_UNAVAILABLE, lower_bound=lower_bound, margin=NONINFERIORITY_MARGIN
        )
    state = (
        NONINFERIORITY_PASS if all(cast("bool", item) for item in passes) else NONINFERIORITY_FAIL
    )
    return NonInferiorityStatus(state=state, lower_bound=lower_bound, margin=NONINFERIORITY_MARGIN)


def _lead_time_from_rows(pooled_median: str | None, *, has_rows: bool) -> LeadTimeStatus:
    """Lead-time rendering from stored medians (arm medians stay UNAVAILABLE)."""
    if not has_rows:
        return LeadTimeStatus(
            state=STATE_NO_DATA,
            candidate_median_lead_time_seconds=None,
            baseline_median_lead_time_seconds=None,
            delta_median_advantage_seconds=None,
        )
    state = STATE_AVAILABLE if pooled_median is not None else STATE_UNAVAILABLE
    return LeadTimeStatus(
        state=state,
        candidate_median_lead_time_seconds=None,
        baseline_median_lead_time_seconds=None,
        delta_median_advantage_seconds=pooled_median,
    )


def _sort_opportunity_counts(
    counts: tuple[DomainOpportunityCounts, ...],
) -> tuple[DomainOpportunityCounts, ...]:
    """Deterministic stratum presentation order (frozen taxonomy first)."""
    rank = {domain: index for index, domain in enumerate(DOMAIN_PRESENTATION_ORDER)}
    return tuple(sorted(counts, key=lambda item: rank.get(item.domain, len(rank))))


def _qualifying_counts(
    counts: tuple[DomainOpportunityCounts, ...],
) -> tuple[DomainOpportunityCounts, ...]:
    """Restrict counts to the frozen qualifying taxonomy order (deterministic)."""
    by_domain = {item.domain: item for item in counts}
    return tuple(
        by_domain[domain] for domain in DOMAIN_PRESENTATION_ORDER[:3] if domain in by_domain
    )


def _freeze_state(freeze: BoundFreezeStatus) -> str:
    """Fail-closed freeze lifecycle rendering (priority: DRIFTED > NOT_DURABLE)."""
    if freeze.status == "DRIFTED":
        return FREEZE_STATE_DRIFTED
    if freeze.durable_freeze_at is None:
        return FREEZE_STATE_NOT_DURABLE
    return FREEZE_STATE_BOUND


def build_experiment_status(
    *,
    freeze: BoundFreezeStatus | None,
    window: WindowBoundaryStatus | None,
    run: LatestRunStatus | None,
    coverage: CoverageHealthStatus | None,
    opportunity_counts: tuple[DomainOpportunityCounts, ...],
    evaluation: EvaluationStatisticsStatus | None,
) -> ExperimentStatus:
    """Assemble the single coherent status; every rule is fail-closed (R4).

    - No runs yet → window ``NO_DATA`` and precision fields ``UNAVAILABLE``
      (never zero, never a coerced ``UNKNOWN``).
    - Latest evaluation receipt status rendered verbatim.
    - Freeze unbound → ``candidate_freeze_receipt_id`` ``None`` with state
      ``UNBOUND``; bound but not durable → ``NOT_DURABLE``; DRIFTED → drift
      state ``INVALID_DRIFT``.
    - A FAILED latest run renders ``run_state=FAILED`` and force-renders the
      experiment statistics ``UNAVAILABLE``: a failed execution NEVER looks
      like an empty ranking.
    """
    if evaluation is not None and evaluation.status not in EVALUATION_RECEIPT_STATUSES:
        raise ValueError("evaluation receipt status is not a preregistered status")

    counts = _sort_opportunity_counts(opportunity_counts)
    candidate_precision: ArmPrecisionStatus | None = None
    baseline_precision: ArmPrecisionStatus | None = None
    noninferiority: NonInferiorityStatus | None = None
    lead_time: LeadTimeStatus | None = None

    if evaluation is not None:
        candidate_surface, candidate_positive = _pooled_arm_counts(
            evaluation.domains, candidate=True
        )
        control_surface, control_positive = _pooled_arm_counts(evaluation.domains, candidate=False)
        candidate_precision = _precision_from_counts(candidate_surface, candidate_positive)
        baseline_precision = _precision_from_counts(control_surface, control_positive)
        noninferiority = _noninferiority_from_rows(evaluation.domains)
        lead_time = _lead_time_from_rows(
            evaluation.pooled_median_lead_time_advantage_seconds,
            has_rows=bool(evaluation.domains),
        )

    # A FAILED latest run never renders as an empty ranking: the statistics
    # are explicitly unavailable, not a zeroed precision table.
    failed_run = run is not None and run.status == FAILED_RUN_STATUS
    if failed_run:
        candidate_precision = ArmPrecisionStatus(
            state=STATE_UNAVAILABLE,
            precision=None,
            surfaced_resolved=None,
            positive_surfaced_resolved=None,
        )
        baseline_precision = ArmPrecisionStatus(
            state=STATE_UNAVAILABLE,
            precision=None,
            surfaced_resolved=None,
            positive_surfaced_resolved=None,
        )
        noninferiority = NonInferiorityStatus(
            state=STATE_UNAVAILABLE, lower_bound=None, margin=NONINFERIORITY_MARGIN
        )
        lead_time = LeadTimeStatus(
            state=STATE_UNAVAILABLE,
            candidate_median_lead_time_seconds=None,
            baseline_median_lead_time_seconds=None,
            delta_median_advantage_seconds=None,
        )

    if freeze is None:
        freeze_id: str | None = None
        freeze_rendered_state = FREEZE_STATE_UNBOUND
        implementation_commit: str | None = None
        implementation_tree_digest: str | None = None
        implementation_state = STATE_UNAVAILABLE
        source_registry_digest: str | None = None
        source_registry_state = STATE_UNAVAILABLE
    else:
        freeze_id = freeze.receipt_id
        freeze_rendered_state = _freeze_state(freeze)
        implementation_commit = freeze.implementation_commit
        implementation_tree_digest = freeze.implementation_tree_digest
        implementation_state = (
            STATE_AVAILABLE
            if freeze.implementation_commit is not None
            and freeze.implementation_tree_digest is not None
            else STATE_UNAVAILABLE
        )
        source_registry_digest = freeze.source_registry_digest
        source_registry_state = (
            STATE_AVAILABLE if freeze.source_registry_digest is not None else STATE_UNAVAILABLE
        )

    drift_invalid = (freeze is not None and freeze.status == "DRIFTED") or (
        evaluation is not None and evaluation.status == "INVALID_DRIFT"
    )

    return ExperimentStatus(
        candidate_freeze_receipt_id=freeze_id,
        candidate_freeze_state=freeze_rendered_state,
        implementation_commit=implementation_commit,
        implementation_tree_digest=implementation_tree_digest,
        implementation_state=implementation_state,
        source_registry_digest=source_registry_digest,
        source_registry_state=source_registry_state,
        window_state=(
            WINDOW_STATE_OPEN
            if window is not None and window.window_start is not None
            else WINDOW_STATE_NO_DATA
        ),
        window_start=window.window_start if window is not None else None,
        latest_boundary_as_of=window.latest_boundary_as_of if window is not None else None,
        latest_attempt_status=window.latest_attempt_status if window is not None else None,
        latest_attempt_detail=window.latest_attempt_detail if window is not None else None,
        latest_run_id=run.run_id if run is not None else None,
        latest_run_status=run.status if run is not None else None,
        run_state=run.status if run is not None else STATE_NO_DATA,
        coverage_state=(worst_coverage_state(coverage) if coverage is not None else STATE_NO_DATA),
        opportunity_counts=counts,
        qualifying_opportunity_counts=_qualifying_counts(counts),
        sample_adequacy_thresholds=preregistered_sample_adequacy_thresholds(),
        domain_evaluation_rows=evaluation.domains if evaluation is not None else (),
        candidate_precision=(
            candidate_precision
            if candidate_precision is not None
            else ArmPrecisionStatus(
                state=STATE_UNAVAILABLE,
                precision=None,
                surfaced_resolved=None,
                positive_surfaced_resolved=None,
            )
        ),
        baseline_precision=(
            baseline_precision
            if baseline_precision is not None
            else ArmPrecisionStatus(
                state=STATE_UNAVAILABLE,
                precision=None,
                surfaced_resolved=None,
                positive_surfaced_resolved=None,
            )
        ),
        noninferiority=noninferiority
        if noninferiority is not None
        else NonInferiorityStatus(
            state=STATE_NO_DATA, lower_bound=None, margin=NONINFERIORITY_MARGIN
        ),
        lead_time=lead_time
        if lead_time is not None
        else LeadTimeStatus(
            state=STATE_NO_DATA,
            candidate_median_lead_time_seconds=None,
            baseline_median_lead_time_seconds=None,
            delta_median_advantage_seconds=None,
        ),
        evaluation_receipt_status=evaluation.status if evaluation is not None else None,
        evaluation_receipt_state=(STATE_AVAILABLE if evaluation is not None else STATE_NO_DATA),
        drift_state=DRIFT_STATE_INVALID_DRIFT if drift_invalid else DRIFT_STATE_OK,
    )
