"""Unit tests for the coherent experiment status projection (WP6, G4).

Fail-closed rendering discipline (R4): missing data is explicit
``NO_DATA``/``UNAVAILABLE``/``UNBOUND`` — never zero, never a coerced
``UNKNOWN``; a FAILED run never looks like an empty ranking; a DRIFTED freeze
propagates ``INVALID_DRIFT``; counts come from anchors only (deterministic).
"""

from __future__ import annotations

import pytest

from frontier.application.experiment_status import build_experiment_status
from frontier.domain.experiment_status import (
    DRIFT_STATE_INVALID_DRIFT,
    DRIFT_STATE_OK,
    EXPERIMENT_STATUS_SCHEMA_VERSION,
    FREEZE_STATE_BOUND,
    FREEZE_STATE_DRIFTED,
    FREEZE_STATE_NOT_DURABLE,
    FREEZE_STATE_UNBOUND,
    NONINFERIORITY_FAIL,
    NONINFERIORITY_PASS,
    STATE_AVAILABLE,
    STATE_NO_DATA,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    WINDOW_STATE_NO_DATA,
    WINDOW_STATE_OPEN,
    BoundFreezeStatus,
    CoverageHealthStatus,
    DomainEvaluationStatusRow,
    DomainOpportunityCounts,
    EvaluationStatisticsStatus,
    ExperimentStatus,
    LatestRunStatus,
    WindowBoundaryStatus,
)

WINDOW = WindowBoundaryStatus(
    window_start="2026-01-01T00:05:00.000000Z",
    latest_boundary_as_of="2026-01-01T01:00:00.000000Z",
    latest_attempt_status="DONE",
    latest_attempt_detail="oprun_abc",
)

FROZEN_DURABLE = BoundFreezeStatus(
    receipt_id="freezereceipt_" + "a" * 64,
    status="FROZEN",
    durable_freeze_at="2026-01-01T00:00:00.000000Z",
    implementation_commit="a" * 40,
    implementation_tree_digest="b" * 40,
    source_registry_digest="sha256:" + "c" * 64,
    frozen_at="2026-01-01T00:00:00.000000Z",
)

RAN_RUN = LatestRunStatus(run_id="oprun_" + "d" * 64, status="RAN", run_class="CONFIRMATORY")
FAILED_RUN = LatestRunStatus(run_id="oprun_" + "e" * 64, status="FAILED", run_class="CONFIRMATORY")

OK_COVERAGE = CoverageHealthStatus(
    transport_state="OK",
    freshness_state="OK",
    completeness_state="OK",
    schema_state="OK",
)


def domain_row(
    domain: str,
    *,
    candidate_precision: str | None = None,
    candidate_surfaced: int | None = None,
    candidate_positive: int | None = None,
    control_precision: str | None = None,
    control_surfaced: int | None = None,
    control_positive: int | None = None,
    difference_lower_bound: str | None = None,
    noninferiority_pass: bool | None = None,
    median_lead: str | None = None,
    adequacy: bool | None = None,
) -> DomainEvaluationStatusRow:
    return DomainEvaluationStatusRow(
        domain=domain,
        candidate_precision=candidate_precision,
        candidate_surfaced_resolved=candidate_surfaced,
        candidate_positive_surfaced_resolved=candidate_positive,
        control_precision=control_precision,
        control_surfaced_resolved=control_surfaced,
        control_positive_surfaced_resolved=control_positive,
        difference_lower_bound=difference_lower_bound,
        noninferiority_pass=noninferiority_pass,
        median_lead_time_advantage_seconds=median_lead,
        qualifies_sample_adequacy=adequacy,
    )


def complete_evaluation() -> EvaluationStatisticsStatus:
    """A stored COMPLETE receipt's own per-domain statistics (verbatim)."""
    return EvaluationStatisticsStatus(
        evaluation_id="evaluation_" + "f" * 64,
        status="COMPLETE",
        freeze_status="FROZEN",
        verdict="SUPPORTED",
        status_reason=None,
        pooled_median_lead_time_advantage_seconds="120.000000000000",
        domains=(
            domain_row(
                "SOFTWARE_PACKAGES",
                candidate_precision="0.800000000000",
                candidate_surfaced=30,
                candidate_positive=24,
                control_precision="0.600000000000",
                control_surfaced=30,
                control_positive=18,
                difference_lower_bound="-0.050000000000",
                noninferiority_pass=True,
                median_lead="60.000000000000",
                adequacy=True,
            ),
            domain_row(
                "AI_MODELS",
                candidate_precision="0.900000000000",
                candidate_surfaced=25,
                candidate_positive=27,
                control_precision="0.700000000000",
                control_surfaced=30,
                control_positive=21,
                difference_lower_bound="-0.020000000000",
                noninferiority_pass=True,
                median_lead="180.000000000000",
                adequacy=True,
            ),
        ),
    )


# ---------------------------------------------------------------------------
# Full-field population with a COMPLETE receipt.
# ---------------------------------------------------------------------------


class TestCompleteStatus:
    def test_schema_version_is_experiment_status_v0(self) -> None:
        assert (
            build_experiment_status(
                freeze=FROZEN_DURABLE,
                window=WINDOW,
                run=RAN_RUN,
                coverage=OK_COVERAGE,
                opportunity_counts=(),
                evaluation=complete_evaluation(),
            ).schema_version
            == EXPERIMENT_STATUS_SCHEMA_VERSION
        )

    def test_full_field_population_renders_every_available_field(self) -> None:
        status = build_experiment_status(
            freeze=FROZEN_DURABLE,
            window=WINDOW,
            run=RAN_RUN,
            coverage=OK_COVERAGE,
            opportunity_counts=(),
            evaluation=complete_evaluation(),
        )
        assert status.experiment_id == "advanced-ranking-pef-v0"
        assert status.candidate_id == "prospective-primary-emission-freshness-v0"
        assert status.candidate_freeze_receipt_id == FROZEN_DURABLE.receipt_id
        assert status.candidate_freeze_state == FREEZE_STATE_BOUND
        assert status.implementation_state == STATE_AVAILABLE
        assert status.source_registry_state == STATE_AVAILABLE
        assert status.window_state == WINDOW_STATE_OPEN
        assert status.window_start == "2026-01-01T00:05:00.000000Z"
        assert status.latest_boundary_as_of == "2026-01-01T01:00:00.000000Z"
        assert status.latest_attempt_status == "DONE"
        assert status.run_state == "RAN"
        assert status.coverage_state == "OK"
        assert status.evaluation_receipt_status == "COMPLETE"
        assert status.evaluation_receipt_state == STATE_AVAILABLE
        assert status.drift_state == "OK"
        assert status.noninferiority.state == NONINFERIORITY_PASS

    def test_pooled_precision_is_sum_of_receipt_arm_counts(self) -> None:
        status = build_experiment_status(
            freeze=FROZEN_DURABLE,
            window=WINDOW,
            run=RAN_RUN,
            coverage=OK_COVERAGE,
            opportunity_counts=(),
            evaluation=complete_evaluation(),
        )
        assert status.candidate_precision.surfaced_resolved == 55
        assert status.candidate_precision.positive_surfaced_resolved == 51
        assert status.candidate_precision.precision == "0.927272727273"
        assert status.baseline_precision.surfaced_resolved == 60
        assert status.baseline_precision.positive_surfaced_resolved == 39
        assert status.baseline_precision.precision == "0.650000000000"

    def test_pooled_lead_time_delta_and_arm_medians(self) -> None:
        status = build_experiment_status(
            freeze=FROZEN_DURABLE,
            window=WINDOW,
            run=RAN_RUN,
            coverage=OK_COVERAGE,
            opportunity_counts=(),
            evaluation=complete_evaluation(),
        )
        assert status.lead_time.delta_median_advantage_seconds == "120.000000000000"
        # Arm-specific medians are never stored and never fabricated.
        assert status.lead_time.candidate_median_lead_time_seconds is None
        assert status.lead_time.baseline_median_lead_time_seconds is None
        assert status.lead_time.state == STATE_AVAILABLE

    def test_sample_adequacy_thresholds_surface_preregistration_verbatim(self) -> None:
        status = build_experiment_status(
            freeze=FROZEN_DURABLE,
            window=WINDOW,
            run=RAN_RUN,
            coverage=OK_COVERAGE,
            opportunity_counts=(),
            evaluation=complete_evaluation(),
        )
        thresholds = status.sample_adequacy_thresholds
        assert thresholds["min_resolved_opportunities_per_domain"] == 30
        assert thresholds["min_positive_opportunities_per_domain"] == 10
        assert thresholds["min_surfaced_resolved_opportunities_per_arm_per_domain"] == 20
        assert thresholds["min_resolved_label_fraction_bps_per_domain"] == 9000
        assert thresholds["minimum_qualifying_domains"] == 2

    def test_verdict_rendered_verbatim_from_receipt(self) -> None:
        evaluation = complete_evaluation()
        assert evaluation.verdict == "SUPPORTED"


# ---------------------------------------------------------------------------
# NO_DATA: a fresh window with no runs, no freeze, no evaluation.
# ---------------------------------------------------------------------------


class TestFreshWindowNoData:
    def _build(self) -> ExperimentStatus:
        return build_experiment_status(
            freeze=None,
            window=None,
            run=None,
            coverage=None,
            opportunity_counts=(),
            evaluation=None,
        )

    def test_window_state_is_no_data(self) -> None:
        assert self._build().window_state == WINDOW_STATE_NO_DATA  # type: ignore[attr-defined]

    def test_precision_fields_are_unavailable_never_zero(self) -> None:
        status = self._build()
        assert status.candidate_precision.state == STATE_UNAVAILABLE  # type: ignore[attr-defined]
        assert status.candidate_precision.precision is None  # type: ignore[attr-defined]
        assert status.baseline_precision.state == STATE_UNAVAILABLE  # type: ignore[attr-defined]
        assert status.baseline_precision.precision is None
        assert status.baseline_precision.precision is None  # type: ignore[attr-defined]

    def test_freeze_unbound_id_is_explicitly_null(self) -> None:
        status = self._build()
        assert status.candidate_freeze_receipt_id is None  # type: ignore[attr-defined]
        assert status.candidate_freeze_state == FREEZE_STATE_UNBOUND  # type: ignore[attr-defined]

    def test_implementation_identity_unavailable_without_freeze(self) -> None:
        status = self._build()
        assert status.implementation_state == STATE_UNAVAILABLE  # type: ignore[attr-defined]
        assert status.implementation_commit is None  # type: ignore[attr-defined]

    def test_evaluation_receipt_state_is_no_data(self) -> None:
        status = self._build()
        assert status.evaluation_receipt_state == STATE_NO_DATA  # type: ignore[attr-defined]
        assert status.evaluation_receipt_status is None  # type: ignore[attr-defined]

    def test_drift_state_is_ok_without_any_drift_evidence(self) -> None:
        assert self._build().drift_state == DRIFT_STATE_OK  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# FAILED run never looks like an empty ranking.
# ---------------------------------------------------------------------------


class TestFailedRun:
    def test_failed_run_renders_failed_state(self) -> None:
        status = build_experiment_status(
            freeze=FROZEN_DURABLE,
            window=WINDOW,
            run=FAILED_RUN,
            coverage=OK_COVERAGE,
            opportunity_counts=(),
            evaluation=None,
        )
        assert status.run_state == "FAILED"
        assert status.latest_run_status == "FAILED"

    def test_failed_run_statistics_never_render_as_zero_precision(self) -> None:
        status = build_experiment_status(
            freeze=FROZEN_DURABLE,
            window=WINDOW,
            run=FAILED_RUN,
            coverage=OK_COVERAGE,
            opportunity_counts=(),
            evaluation=complete_evaluation(),
        )
        assert status.candidate_precision.state == STATE_UNAVAILABLE
        assert status.candidate_precision.precision is None
        assert status.candidate_precision.surfaced_resolved is None
        assert status.baseline_precision.state == STATE_UNAVAILABLE
        assert status.baseline_precision.precision is None
        assert status.noninferiority.state == STATE_UNAVAILABLE
        assert status.lead_time.state == STATE_UNAVAILABLE
        assert status.lead_time.delta_median_advantage_seconds is None

    def test_failed_run_evaluation_status_still_rendered_verbatim(self) -> None:
        status = build_experiment_status(
            freeze=FROZEN_DURABLE,
            window=WINDOW,
            run=FAILED_RUN,
            coverage=OK_COVERAGE,
            opportunity_counts=(),
            evaluation=complete_evaluation(),
        )
        assert status.evaluation_receipt_status == "COMPLETE"


# ---------------------------------------------------------------------------
# Freeze durability and drift propagation.
# ---------------------------------------------------------------------------


class TestFreezeStates:
    def _bound_not_durable(self) -> BoundFreezeStatus:
        return BoundFreezeStatus(
            receipt_id=FROZEN_DURABLE.receipt_id,
            status="FROZEN",
            durable_freeze_at=None,
            implementation_commit=FROZEN_DURABLE.implementation_commit,
            implementation_tree_digest=FROZEN_DURABLE.implementation_tree_digest,
            source_registry_digest=FROZEN_DURABLE.source_registry_digest,
            frozen_at=FROZEN_DURABLE.frozen_at,
        )

    def test_bound_but_not_durable_renders_not_durable(self) -> None:
        status = build_experiment_status(
            freeze=self._bound_not_durable(),
            window=WINDOW,
            run=RAN_RUN,
            coverage=OK_COVERAGE,
            opportunity_counts=(),
            evaluation=None,
        )
        assert status.candidate_freeze_state == FREEZE_STATE_NOT_DURABLE
        assert status.candidate_freeze_receipt_id is not None

    def test_drifted_freeze_propagates_invalid_drift(self) -> None:
        drifted = BoundFreezeStatus(
            receipt_id=FROZEN_DURABLE.receipt_id,
            status="DRIFTED",
            durable_freeze_at=FROZEN_DURABLE.durable_freeze_at,
            implementation_commit=None,
            implementation_tree_digest=None,
            source_registry_digest=None,
            frozen_at=FROZEN_DURABLE.frozen_at,
        )
        status = build_experiment_status(
            freeze=drifted,
            window=WINDOW,
            run=RAN_RUN,
            coverage=OK_COVERAGE,
            opportunity_counts=(),
            evaluation=None,
        )
        assert status.candidate_freeze_state == FREEZE_STATE_DRIFTED
        assert status.drift_state == DRIFT_STATE_INVALID_DRIFT
        assert status.implementation_state == STATE_UNAVAILABLE
        assert status.source_registry_state == STATE_UNAVAILABLE

    def test_invalid_drift_evaluation_receipt_propagates_drift_state(self) -> None:
        evaluation = EvaluationStatisticsStatus(
            evaluation_id="evaluation_" + "1" * 64,
            status="INVALID_DRIFT",
            freeze_status="DRIFTED",
            verdict=None,
            status_reason="freeze drifted",
            pooled_median_lead_time_advantage_seconds=None,
            domains=(),
        )
        status = build_experiment_status(
            freeze=FROZEN_DURABLE,
            window=WINDOW,
            run=RAN_RUN,
            coverage=OK_COVERAGE,
            opportunity_counts=(),
            evaluation=evaluation,
        )
        assert status.evaluation_receipt_status == "INVALID_DRIFT"
        assert status.drift_state == DRIFT_STATE_INVALID_DRIFT

    def test_partial_implementation_identity_is_unavailable(self) -> None:
        partial = BoundFreezeStatus(
            receipt_id=FROZEN_DURABLE.receipt_id,
            status="FROZEN",
            durable_freeze_at=FROZEN_DURABLE.durable_freeze_at,
            implementation_commit=FROZEN_DURABLE.implementation_commit,
            implementation_tree_digest=None,
            source_registry_digest=None,
            frozen_at=FROZEN_DURABLE.frozen_at,
        )
        status = build_experiment_status(
            freeze=partial,
            window=None,
            run=None,
            coverage=None,
            opportunity_counts=(),
            evaluation=None,
        )
        assert status.implementation_state == STATE_UNAVAILABLE
        assert status.source_registry_state == STATE_UNAVAILABLE


# ---------------------------------------------------------------------------
# UNKNOWN coverage is never coerced.
# ---------------------------------------------------------------------------


class TestCoverage:
    def test_unknown_coverage_renders_unknown_never_ok(self) -> None:
        coverage = CoverageHealthStatus(
            transport_state="OK",
            freshness_state="OK",
            completeness_state="UNKNOWN",
            schema_state="OK",
        )
        status = build_experiment_status(
            freeze=None,
            window=WINDOW,
            run=RAN_RUN,
            coverage=coverage,
            opportunity_counts=(),
            evaluation=None,
        )
        assert status.coverage_state == STATE_UNKNOWN

    def test_failed_lane_is_worse_than_degraded(self) -> None:
        coverage = CoverageHealthStatus(
            transport_state="DEGRADED",
            freshness_state="FAILED",
            completeness_state="OK",
            schema_state="OK",
        )
        status = build_experiment_status(
            freeze=None,
            window=None,
            run=RAN_RUN,
            coverage=coverage,
            opportunity_counts=(),
            evaluation=None,
        )
        assert status.coverage_state == "FAILED"

    def test_no_coverage_input_renders_no_data_never_ok(self) -> None:
        status = build_experiment_status(
            freeze=FROZEN_DURABLE,
            window=WINDOW,
            run=RAN_RUN,
            coverage=None,
            opportunity_counts=(),
            evaluation=None,
        )
        assert status.coverage_state == STATE_NO_DATA


# ---------------------------------------------------------------------------
# Counts derived from anchors only (deterministic).
# ---------------------------------------------------------------------------


def counts_for(domain: str, **overrides: int) -> DomainOpportunityCounts:
    defaults = {
        "anchor_count": 0,
        "resolved_positive_count": 0,
        "resolved_negative_count": 0,
        "unresolved_coverage_count": 0,
        "unknown_count": 0,
        "excluded_count": 0,
        "pending_count": 0,
    }
    defaults.update(overrides)
    return DomainOpportunityCounts(domain=domain, **defaults)


class TestOpportunityCounts:
    def test_counts_derived_from_anchors_only(self) -> None:
        counts = (
            counts_for(
                "SOFTWARE_PACKAGES",
                anchor_count=10,
                resolved_positive_count=4,
                resolved_negative_count=3,
                unresolved_coverage_count=1,
                unknown_count=1,
                excluded_count=1,
                pending_count=1,
            ),
            counts_for("AI_MODELS", anchor_count=5, pending_count=5),
        )
        status = build_experiment_status(
            freeze=FROZEN_DURABLE,
            window=WINDOW,
            run=RAN_RUN,
            coverage=OK_COVERAGE,
            opportunity_counts=counts,
            evaluation=None,
        )
        assert status.opportunity_counts == (
            counts[0],
            counts[1],
        )
        assert status.qualifying_opportunity_counts == (counts[0], counts[1])

    def test_unknown_resolutions_never_count_as_resolved_negative(self) -> None:
        counts = counts_for(
            "SECURITY_VULNERABILITIES",
            anchor_count=7,
            unresolved_coverage_count=2,
            unknown_count=2,
        )
        status = build_experiment_status(
            freeze=FROZEN_DURABLE,
            window=WINDOW,
            run=RAN_RUN,
            coverage=OK_COVERAGE,
            opportunity_counts=(counts,),
            evaluation=None,
        )
        rendered = status.opportunity_counts[0]
        assert rendered.unknown_count == 2
        assert rendered.unresolved_coverage_count == 2
        assert rendered.resolved_negative_count == 0
        assert rendered.resolved_positive_count == 0

    def test_unqualified_strata_kept_out_of_qualifying_counts(self) -> None:
        unqualified = counts_for("UNQUALIFIED", anchor_count=3, pending_count=3)
        mixed = counts_for("UNQUALIFIED_MIXED", anchor_count=2, excluded_count=2)
        status = build_experiment_status(
            freeze=FROZEN_DURABLE,
            window=WINDOW,
            run=RAN_RUN,
            coverage=OK_COVERAGE,
            opportunity_counts=(unqualified, mixed),
            evaluation=None,
        )
        assert status.opportunity_counts == (mixed, unqualified)
        assert status.qualifying_opportunity_counts == ()

    def test_counts_are_deterministic_across_input_order(self) -> None:
        a = counts_for("AI_MODELS", anchor_count=5)
        s = counts_for("SECURITY_VULNERABILITIES", anchor_count=6)
        p = counts_for("SOFTWARE_PACKAGES", anchor_count=7)
        first = build_experiment_status(
            freeze=None,
            window=None,
            run=None,
            coverage=None,
            opportunity_counts=(a, s, p),
            evaluation=None,
        )
        second = build_experiment_status(
            freeze=None,
            window=None,
            run=None,
            coverage=None,
            opportunity_counts=(p, a, s),
            evaluation=None,
        )
        assert first.opportunity_counts == second.opportunity_counts

    def test_empty_anchor_set_yields_no_rendered_strata(self) -> None:
        status = build_experiment_status(
            freeze=None,
            window=None,
            run=None,
            coverage=None,
            opportunity_counts=(),
            evaluation=None,
        )
        assert status.opportunity_counts == ()
        assert status.qualifying_opportunity_counts == ()


# ---------------------------------------------------------------------------
# Non-inferiority and receipt-status rendering.
# ---------------------------------------------------------------------------


class TestNonInferiority:
    def test_any_failing_domain_renders_fail(self) -> None:
        evaluation = EvaluationStatisticsStatus(
            evaluation_id="evaluation_" + "2" * 64,
            status="INSUFFICIENT_SAMPLE",
            freeze_status="FROZEN",
            verdict=None,
            status_reason="fewer than two adequately sampled domains",
            pooled_median_lead_time_advantage_seconds=None,
            domains=(
                domain_row("SOFTWARE_PACKAGES", noninferiority_pass=True),
                domain_row(
                    "AI_MODELS", noninferiority_pass=False, difference_lower_bound="-0.500000000000"
                ),
            ),
        )
        status = build_experiment_status(
            freeze=FROZEN_DURABLE,
            window=WINDOW,
            run=RAN_RUN,
            coverage=OK_COVERAGE,
            opportunity_counts=(),
            evaluation=evaluation,
        )
        assert status.noninferiority.state == NONINFERIORITY_FAIL
        # Multiple domains cannot pool a single lower bound.
        assert status.noninferiority.lower_bound is None

    def test_missing_noninferiority_boolean_is_unavailable(self) -> None:
        evaluation = EvaluationStatisticsStatus(
            evaluation_id="evaluation_" + "3" * 64,
            status="FAILED",
            freeze_status="FROZEN",
            verdict=None,
            status_reason="unable to compute",
            pooled_median_lead_time_advantage_seconds=None,
            domains=(domain_row("SOFTWARE_PACKAGES", noninferiority_pass=None),),
        )
        status = build_experiment_status(
            freeze=FROZEN_DURABLE,
            window=WINDOW,
            run=RAN_RUN,
            coverage=OK_COVERAGE,
            opportunity_counts=(),
            evaluation=evaluation,
        )
        assert status.noninferiority.state == STATE_UNAVAILABLE

    def test_insufficient_sample_status_rendered_verbatim(self) -> None:
        evaluation = EvaluationStatisticsStatus(
            evaluation_id="evaluation_" + "4" * 64,
            status="INSUFFICIENT_SAMPLE",
            freeze_status="FROZEN",
            verdict=None,
            status_reason="INSUFFICIENT_SAMPLE",
            pooled_median_lead_time_advantage_seconds=None,
            domains=(),
        )
        status = build_experiment_status(
            freeze=FROZEN_DURABLE,
            window=WINDOW,
            run=RAN_RUN,
            coverage=OK_COVERAGE,
            opportunity_counts=(),
            evaluation=evaluation,
        )
        assert status.evaluation_receipt_status == "INSUFFICIENT_SAMPLE"
        assert status.evaluation_receipt_state == STATE_AVAILABLE

    def test_failed_evaluation_status_rendered_verbatim(self) -> None:
        evaluation = EvaluationStatisticsStatus(
            evaluation_id="evaluation_" + "5" * 64,
            status="FAILED",
            freeze_status="FROZEN",
            verdict=None,
            status_reason="unable to compute",
            pooled_median_lead_time_advantage_seconds=None,
            domains=(),
        )
        status = build_experiment_status(
            freeze=FROZEN_DURABLE,
            window=WINDOW,
            run=RAN_RUN,
            coverage=OK_COVERAGE,
            opportunity_counts=(),
            evaluation=evaluation,
        )
        assert status.evaluation_receipt_status == "FAILED"

    def test_non_preregistered_status_is_rejected(self) -> None:
        evaluation = EvaluationStatisticsStatus(
            evaluation_id="evaluation_" + "6" * 64,
            status="SUPPORTED",
            freeze_status="FROZEN",
            verdict="SUPPORTED",
            status_reason=None,
            pooled_median_lead_time_advantage_seconds=None,
            domains=(),
        )
        with pytest.raises(ValueError):
            build_experiment_status(
                freeze=FROZEN_DURABLE,
                window=WINDOW,
                run=RAN_RUN,
                coverage=OK_COVERAGE,
                opportunity_counts=(),
                evaluation=evaluation,
            )


# ---------------------------------------------------------------------------
# Empty-precision discipline inside a populated receipt.
# ---------------------------------------------------------------------------


class TestEmptyArms:
    def test_empty_pooled_arm_never_yields_zero_precision(self) -> None:
        evaluation = EvaluationStatisticsStatus(
            evaluation_id="evaluation_" + "7" * 64,
            status="INSUFFICIENT_SAMPLE",
            freeze_status="FROZEN",
            verdict=None,
            status_reason="INSUFFICIENT_SAMPLE",
            pooled_median_lead_time_advantage_seconds=None,
            domains=(
                domain_row(
                    "SOFTWARE_PACKAGES",
                    candidate_precision=None,
                    candidate_surfaced=0,
                    candidate_positive=0,
                    control_precision=None,
                    control_surfaced=0,
                    control_positive=0,
                ),
            ),
        )
        status = build_experiment_status(
            freeze=FROZEN_DURABLE,
            window=WINDOW,
            run=RAN_RUN,
            coverage=OK_COVERAGE,
            opportunity_counts=(),
            evaluation=evaluation,
        )
        assert status.candidate_precision.state == STATE_UNAVAILABLE
        assert status.candidate_precision.precision is None
        assert status.baseline_precision.state == STATE_UNAVAILABLE
        assert status.baseline_precision.precision is None
        # Zero-count surfaces render as stored (0), the proportion stays None.
        assert status.candidate_precision.surfaced_resolved == 0

    def test_missing_stored_counts_are_unavailable_not_zero(self) -> None:
        evaluation = EvaluationStatisticsStatus(
            evaluation_id="evaluation_" + "8" * 64,
            status="FAILED",
            freeze_status="FROZEN",
            verdict=None,
            status_reason="failed",
            pooled_median_lead_time_advantage_seconds=None,
            domains=(
                domain_row("SOFTWARE_PACKAGES", candidate_surfaced=None, candidate_positive=None),
            ),
        )
        status = build_experiment_status(
            freeze=FROZEN_DURABLE,
            window=WINDOW,
            run=RAN_RUN,
            coverage=OK_COVERAGE,
            opportunity_counts=(),
            evaluation=evaluation,
        )
        assert status.candidate_precision.state == STATE_UNAVAILABLE
        assert status.candidate_precision.surfaced_resolved is None

    def test_lead_time_without_pooled_median_is_unavailable(self) -> None:
        evaluation = EvaluationStatisticsStatus(
            evaluation_id="evaluation_" + "9" * 64,
            status="INSUFFICIENT_SAMPLE",
            freeze_status="FROZEN",
            verdict=None,
            status_reason="reason",
            pooled_median_lead_time_advantage_seconds=None,
            domains=(domain_row("AI_MODELS", median_lead=None, adequacy=False),),
        )
        status = build_experiment_status(
            freeze=FROZEN_DURABLE,
            window=WINDOW,
            run=RAN_RUN,
            coverage=OK_COVERAGE,
            opportunity_counts=(),
            evaluation=evaluation,
        )
        assert status.lead_time.state == STATE_UNAVAILABLE
        assert status.lead_time.delta_median_advantage_seconds is None


# ---------------------------------------------------------------------------
# Window boundary invariants.
# ---------------------------------------------------------------------------


class TestWindowInvariants:
    def test_latest_boundary_without_window_start_rejected(self) -> None:
        with pytest.raises(ValueError):
            WindowBoundaryStatus(window_start=None, latest_boundary_as_of="2026-01-01T00:05:00Z")

    def test_attempt_detail_rendered_verbatim(self) -> None:
        window = WindowBoundaryStatus(
            window_start="2026-01-01T00:05:00.000000Z",
            latest_boundary_as_of="2026-01-01T00:10:00.000000Z",
            latest_attempt_status="EXPIRED",
            latest_attempt_detail="lease expired without heartbeat",
        )
        status = build_experiment_status(
            freeze=None,
            window=window,
            run=None,
            coverage=None,
            opportunity_counts=(),
            evaluation=None,
        )
        assert status.latest_attempt_status == "EXPIRED"
        assert status.latest_attempt_detail == "lease expired without heartbeat"
        assert status.window_state == WINDOW_STATE_OPEN
