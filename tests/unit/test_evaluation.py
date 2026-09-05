"""Unit tests for the preregistered PEF_V0 evaluation machinery (slice D)."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal, localcontext
from typing import cast

import pytest

from frontier.application.evaluation import PairedSnapshot, evaluate_shadow_experiment
from frontier.domain.advanced_intelligence import (
    PEF_CONFIGURATION_DIGEST,
    ShadowControlArmRanking,
    ShadowExperimentRun,
    ShadowRunStatus,
)
from frontier.domain.candidate_freeze import (
    CandidateFreezeReceipt,
    FreezeInputs,
    FreezeStatus,
    build_candidate_freeze_receipt,
)
from frontier.domain.digests import Digest
from frontier.domain.evaluation import (
    DOMAIN_AI_MODELS,
    DOMAIN_SOFTWARE_PACKAGES,
    DOMAIN_UNQUALIFIED,
    DOMAIN_UNQUALIFIED_MIXED,
    EVALUATION_CONFIGURATION,
    AnchorObservation,
    AnchorTracking,
    ArmPrecision,
    DomainEvaluation,
    EvaluationCounts,
    EvaluationStatus,
    LaneBoundary,
    OpportunityGroup,
    OutcomeLabel,
    RetainedOpportunity,
    ShadowRunBinding,
    build_retained_opportunities,
    classify_anchor_domain,
    detect_anchor,
    evaluate_domains,
    expected_lane_boundaries,
    lead_time_advantage_seconds,
    median,
    newcombe_difference_bounds,
    pooled_lead_time_median,
    resolve_outcome_label,
    sample_adequacy_pass,
    wilson_score_bounds,
)
from frontier.domain.health import HealthValue

BASE_EPOCH = int(datetime(2026, 9, 1, 0, 0, tzinfo=UTC).timestamp())
CADENCE = 300


def _at(offset_seconds: int) -> datetime:
    return datetime.fromtimestamp(BASE_EPOCH + offset_seconds, tz=UTC)


def _anchor(
    label: str,
    *,
    source_id: str = "pypi.updates",
    role: str = "PRIMARY_EMISSION",
    observed_at: datetime,
) -> AnchorObservation:
    return AnchorObservation(
        observation_id="obs_" + hashlib.sha256(label.encode()).hexdigest(),
        source_id=source_id,
        role=role,
        observed_at=observed_at,
    )


def _boundary(
    as_of: datetime, source_id: str, *, state: HealthValue = HealthValue.OK
) -> LaneBoundary:
    return LaneBoundary(
        source_id=source_id,
        as_of=as_of,
        transport_state=state,
        freshness_state=state,
        completeness_state=state,
        schema_state=state,
    )


def _full_lane_coverage(anchor_observed_at: datetime) -> tuple[LaneBoundary, ...]:
    boundaries: list[LaneBoundary] = []
    for source_id in ("hn.frontpage", "gdelt.frontier"):
        for boundary_at in expected_lane_boundaries(anchor_observed_at):
            boundaries.append(_boundary(boundary_at, source_id))
    return tuple(boundaries)


def _track_at(
    as_of: datetime,
    episode_id: str,
    *,
    control_rank: int | None,
    candidate_rank: int | None,
) -> AnchorTracking:
    return AnchorTracking(
        as_of=as_of, episode_id=episode_id, control_rank=control_rank, candidate_rank=candidate_rank
    )


def _group(
    anchor: AnchorObservation,
    *,
    outcome: OutcomeLabel,
    extra_members: tuple[AnchorObservation, ...] = (),
    other_anchors: tuple[AnchorObservation, ...] = (),
) -> OpportunityGroup:
    attention = tuple(
        (
            _anchor(
                anchor.observation_id + "-hn",
                source_id="hn.frontpage",
                role="ATTENTION",
                observed_at=anchor.observed_at + timedelta(seconds=600),
            ),
        )
        if outcome is OutcomeLabel.POSITIVE
        else ()
    )
    return OpportunityGroup(
        resolution_episode_id="ep_" + anchor.observation_id,
        primary_emission_anchors=(anchor, *other_anchors),
        member_observations=(anchor, *extra_members, *attention),
        lane_boundaries=()
        if outcome is OutcomeLabel.UNRESOLVED_COVERAGE
        else _full_lane_coverage(anchor.observed_at),
    )


def _opportunity(
    label: str,
    domain: str,
    outcome: OutcomeLabel,
    observed_at: datetime,
) -> RetainedOpportunity:
    return RetainedOpportunity(
        anchor=_anchor(label, observed_at=observed_at),
        domain=domain,
        resolution_episode_id="ep_" + label,
        resolution_at=observed_at + timedelta(seconds=86400),
        label=outcome,
    )


class TestOutcomeLabels:
    def test_positive_from_attention_within_window(self) -> None:
        anchor = _anchor("a1", observed_at=_at(0))
        attention = _anchor(
            "a1-hn", source_id="hn.frontpage", role="ATTENTION", observed_at=_at(600)
        )
        label = resolve_outcome_label(
            anchor, member_observations=(anchor, attention), lane_boundaries=()
        )
        assert label is OutcomeLabel.POSITIVE

    def test_positive_from_discovery_within_window(self) -> None:
        anchor = _anchor("a2", observed_at=_at(0))
        discovery = _anchor(
            "a2-gd", source_id="gdelt.frontier", role="DISCOVERY", observed_at=_at(600)
        )
        label = resolve_outcome_label(
            anchor, member_observations=(anchor, discovery), lane_boundaries=()
        )
        assert label is OutcomeLabel.POSITIVE

    def test_positive_remains_positive_under_degraded_coverage(self) -> None:
        anchor = _anchor("a3", observed_at=_at(0))
        attention = _anchor(
            "a3-hn", source_id="hn.frontpage", role="ATTENTION", observed_at=_at(600)
        )
        degraded = _boundary(_at(900), "hn.frontpage", state=HealthValue.DEGRADED)
        label = resolve_outcome_label(
            anchor,
            member_observations=(anchor, attention),
            lane_boundaries=(degraded,),
        )
        assert label is OutcomeLabel.POSITIVE

    def test_outcome_observation_outside_window_is_not_positive(self) -> None:
        anchor = _anchor("a4", observed_at=_at(0))
        before = _anchor("a4-b", source_id="hn.frontpage", role="ATTENTION", observed_at=_at(-300))
        late = _anchor("a4-l", source_id="hn.frontpage", role="ATTENTION", observed_at=_at(86700))
        label = resolve_outcome_label(
            anchor,
            member_observations=(anchor, before, late),
            lane_boundaries=_full_lane_coverage(_at(0)),
        )
        assert label is OutcomeLabel.NEGATIVE

    def test_negative_requires_full_lane_coverage(self) -> None:
        anchor = _anchor("a5", observed_at=_at(0))
        label = resolve_outcome_label(
            anchor, member_observations=(anchor,), lane_boundaries=_full_lane_coverage(_at(0))
        )
        assert label is OutcomeLabel.NEGATIVE

    def test_missing_lane_boundary_is_unresolved_coverage(self) -> None:
        anchor = _anchor("a6", observed_at=_at(0))
        label = resolve_outcome_label(anchor, member_observations=(anchor,), lane_boundaries=())
        assert label is OutcomeLabel.UNRESOLVED_COVERAGE

    def test_unknown_lane_health_is_unresolved_coverage(self) -> None:
        anchor = _anchor("a7", observed_at=_at(0))
        boundaries = list(_full_lane_coverage(_at(0)))
        assert boundaries
        boundaries[0] = _boundary(
            boundaries[0].as_of, boundaries[0].source_id, state=HealthValue.UNKNOWN
        )
        label = resolve_outcome_label(
            anchor, member_observations=(anchor,), lane_boundaries=tuple(boundaries)
        )
        assert label is OutcomeLabel.UNRESOLVED_COVERAGE


class TestAnchors:
    def test_dedup_retains_earliest_qualifying_anchor(self) -> None:
        first = _anchor("d1-first", observed_at=_at(300))
        second = _anchor("d1-second", observed_at=_at(600))
        (retained,) = build_retained_opportunities(
            (_group(first, outcome=OutcomeLabel.NEGATIVE, other_anchors=(second,)),)
        )
        assert retained.anchor.observation_id == first.observation_id
        assert retained.domain == DOMAIN_SOFTWARE_PACKAGES

    def test_dedup_tiebreaks_by_observation_id(self) -> None:
        a = _anchor("d2-a", observed_at=_at(300))
        b = _anchor("d2-b", observed_at=_at(300))
        (retained,) = build_retained_opportunities(
            (_group(a, outcome=OutcomeLabel.NEGATIVE, other_anchors=(b,)),)
        )
        assert retained.anchor.observation_id == min(a.observation_id, b.observation_id)

    def test_unqualified_mixed_classification(self) -> None:
        assert classify_anchor_domain(["pypi.updates"]) == DOMAIN_SOFTWARE_PACKAGES
        assert classify_anchor_domain(["hf.models"]) == DOMAIN_AI_MODELS
        assert classify_anchor_domain(["hn.frontpage", "gdelt.frontier"]) == DOMAIN_UNQUALIFIED
        assert classify_anchor_domain(["pypi.updates", "cisa.kev"]) == DOMAIN_UNQUALIFIED_MIXED

    def test_unqualified_mixed_anchor_is_retained_but_not_qualifying(self) -> None:
        mixed = _anchor("m1", source_id="pypi.updates", observed_at=_at(300))
        other = _anchor("m2", source_id="cisa.kev", observed_at=_at(600))
        (retained,) = build_retained_opportunities(
            (_group(mixed, outcome=OutcomeLabel.NEGATIVE, other_anchors=(other,)),)
        )
        assert retained.domain == DOMAIN_UNQUALIFIED_MIXED

    def test_unqualified_group_is_dropped(self) -> None:
        attention_only = _anchor(
            "u1", source_id="hn.frontpage", role="ATTENTION", observed_at=_at(300)
        )
        assert (
            build_retained_opportunities(
                (
                    OpportunityGroup(
                        resolution_episode_id="ep_u",
                        primary_emission_anchors=(attention_only,),
                        member_observations=(attention_only,),
                        lane_boundaries=_full_lane_coverage(_at(300)),
                    ),
                )
            )
            == ()
        )


class TestPrecisionAtK:
    def test_hand_computed_precision(self) -> None:
        # Four resolved opportunities (2 positive, 2 negative). Candidate
        # surfaces both positives and one negative (3 surfaced, precision 2/3);
        # control surfaces all four (precision 2/4 = 1/2). Hand-computed.
        specs = [
            ("p1", OutcomeLabel.POSITIVE, 1, 1),
            ("p2", OutcomeLabel.POSITIVE, 1, 1),
            ("n1", OutcomeLabel.NEGATIVE, 1, 1),
            ("n2", OutcomeLabel.NEGATIVE, 1, None),
        ]
        groups: list[OpportunityGroup] = []
        tracking: dict[str, Sequence[AnchorTracking]] = {}
        for index, (label, outcome, control_rank, candidate_rank) in enumerate(specs):
            anchor = _anchor(f"prec-{label}", observed_at=_at(CADENCE * (index + 1)))
            tracking[anchor.observation_id] = (
                _track_at(
                    anchor.observed_at,
                    "ep",
                    control_rank=control_rank,
                    candidate_rank=candidate_rank,
                ),
            )
            groups.append(_group(anchor, outcome=outcome))
        (evaluation,) = evaluate_domains(build_retained_opportunities(groups), tracking)
        assert evaluation.domain == DOMAIN_SOFTWARE_PACKAGES
        assert evaluation.resolved_label_fraction_denominator == 4
        assert evaluation.resolved_label_fraction_numerator == 4
        assert evaluation.candidate_arm.surfaced_resolved == 3
        assert evaluation.candidate_arm.positive_surfaced_resolved == 2
        assert evaluation.control_arm.surfaced_resolved == 4
        assert evaluation.control_arm.positive_surfaced_resolved == 2
        assert evaluation.candidate_arm.precision == Decimal("0.666666666667")
        assert evaluation.control_arm.precision == Decimal("0.5")
        assert evaluation.point_floor_pass is True
        # Both arms detect each positive at the same boundary: tie lead times.
        assert evaluation.median_lead_time_advantage_seconds == Decimal(0)


class TestUnresolvedCoverageAccounting:
    def test_unresolved_excluded_from_numerator_and_denominator(self) -> None:
        groups: list[OpportunityGroup] = []
        tracking: dict[str, Sequence[AnchorTracking]] = {}
        for index in range(30):
            outcome = OutcomeLabel.POSITIVE if index < 10 else OutcomeLabel.NEGATIVE
            anchor = _anchor(f"res-{index}", observed_at=_at(CADENCE * (index + 1)))
            tracking[anchor.observation_id] = (
                _track_at(anchor.observed_at, "ep", control_rank=1, candidate_rank=1),
            )
            groups.append(_group(anchor, outcome=outcome))
        for index in range(3):
            anchor = _anchor(f"unres-{index}", observed_at=_at(CADENCE * (index + 1)))
            tracking[anchor.observation_id] = (
                _track_at(anchor.observed_at, "ep", control_rank=1, candidate_rank=1),
            )
            groups.append(_group(anchor, outcome=OutcomeLabel.UNRESOLVED_COVERAGE))
        (evaluation,) = evaluate_domains(build_retained_opportunities(groups), tracking)
        assert evaluation.resolved_label_fraction_denominator == 33
        assert evaluation.resolved_label_fraction_numerator == 30
        assert evaluation.unresolved_coverage_count == 3
        assert evaluation.resolved_label_fraction_bps == (30 * 10000) // 33
        assert evaluation.qualifies_sample_adequacy is True


class TestNewcombe:
    Z = Decimal("1.959963984540054")

    def test_wilson_degenerate_closed_forms(self) -> None:
        # Independent hand-derived closed forms:
        #   x=0: L=0 and U = z^2/(n+z^2);  x=n: U=1 and L = n/(n+z^2).
        z2 = self.Z * self.Z
        n = Decimal(10)
        quant = Decimal("0.000000000001")
        bounds_zero = wilson_score_bounds(0, 10)
        assert bounds_zero is not None
        assert bounds_zero[0] == Decimal(0)
        assert bounds_zero[1] == (z2 / (n + z2)).quantize(quant)
        bounds_full = wilson_score_bounds(10, 10)
        assert bounds_full is not None
        assert bounds_full[1] == Decimal(1)
        assert bounds_full[0] == (n / (n + z2)).quantize(quant)

    def test_newcombe_matches_independent_closed_form(self) -> None:
        x1, n1 = 8, 40
        x2, n2 = 5, 40
        z = self.Z

        def wilson(x: int, n: int) -> tuple[Decimal, Decimal]:
            with localcontext() as ctx:
                ctx.prec = 50
                denom = Decimal(2) * (Decimal(n) + z * z)
                radicand = z * z + Decimal(4) * Decimal(x) * (Decimal(n) - Decimal(x)) / Decimal(n)
                root = radicand.sqrt()
                center = (Decimal(2) * Decimal(x) + z * z) / denom
                half = z * root / denom
            zero, one = Decimal(0), Decimal(1)
            return (max(zero, center - half), min(one, center + half))

        p1 = Decimal(x1) / Decimal(n1)
        p2 = Decimal(x2) / Decimal(n2)
        l1, u1 = wilson(x1, n1)
        l2, u2 = wilson(x2, n2)
        expected_lower = (p1 - p2) - ((p1 - l1) ** 2 + (u2 - p2) ** 2).sqrt()
        expected_upper = (p1 - p2) + ((u1 - p1) ** 2 + (p2 - l2) ** 2).sqrt()
        computed = newcombe_difference_bounds(x1, n1, x2, n2)
        assert computed is not None
        assert abs(computed[0] - expected_lower) < Decimal("0.000001")
        assert abs(computed[1] - expected_upper) < Decimal("0.000001")

    def test_empty_arm_yields_no_fabricated_interval(self) -> None:
        assert newcombe_difference_bounds(0, 0, 5, 10) is None
        assert wilson_score_bounds(0, 0) is None

    def test_noninferiority_margin_gate_semantics(self) -> None:
        inferior = newcombe_difference_bounds(4, 40, 8, 40)
        assert inferior is not None and inferior[0] < Decimal("-0.10")
        equal = newcombe_difference_bounds(20, 200, 20, 200)
        assert equal is not None
        assert Decimal("-0.10") <= equal[0] < Decimal(0)


class TestLeadTime:
    def test_candidate_detected_earlier_gives_positive_lead_time(self) -> None:
        opportunity = _opportunity(
            "lt1", DOMAIN_SOFTWARE_PACKAGES, OutcomeLabel.POSITIVE, _at(CADENCE)
        )
        detection = detect_anchor(
            opportunity,
            (_track_at(_at(CADENCE), "ep_lt1", control_rank=None, candidate_rank=1),),
        )
        assert detection.candidate_surfaced is True
        assert detection.control_surfaced is False
        assert lead_time_advantage_seconds(detection) == 86400

    def test_control_detected_earlier_gives_negative_lead_time(self) -> None:
        opportunity = _opportunity(
            "lt2", DOMAIN_SOFTWARE_PACKAGES, OutcomeLabel.POSITIVE, _at(CADENCE)
        )
        detection = detect_anchor(
            opportunity,
            (_track_at(_at(CADENCE), "ep_lt2", control_rank=1, candidate_rank=None),),
        )
        assert lead_time_advantage_seconds(detection) == -86400

    def test_both_arms_miss_is_zero_and_retained(self) -> None:
        opportunity = _opportunity(
            "lt3", DOMAIN_SOFTWARE_PACKAGES, OutcomeLabel.POSITIVE, _at(CADENCE)
        )
        detection = detect_anchor(opportunity, ())
        assert detection.control_surfaced is False
        assert detection.candidate_surfaced is False
        assert lead_time_advantage_seconds(detection) == 0

    def test_boundaries_outside_the_tracking_window_are_ignored(self) -> None:
        opportunity = _opportunity(
            "lt4", DOMAIN_SOFTWARE_PACKAGES, OutcomeLabel.POSITIVE, _at(CADENCE)
        )
        detection = detect_anchor(
            opportunity,
            (
                _track_at(_at(0), "ep_lt4", control_rank=1, candidate_rank=1),
                _track_at(_at(86400), "ep_lt4", control_rank=1, candidate_rank=1),
            ),
        )
        assert detection.control_detection_time == _at(86400)
        assert detection.candidate_detection_time == _at(86400)

    def test_median_odd_and_even_counts(self) -> None:
        assert median([5, 3, 300]) == Decimal(5)
        assert median([4, 300]) == Decimal(152)
        assert median([2, 300, 4, 6]) == Decimal(5)


class TestSampleAdequacy:
    def _evaluation(self, **overrides: object) -> DomainEvaluation:
        base = DomainEvaluation(
            domain=DOMAIN_SOFTWARE_PACKAGES,
            resolved_label_fraction_denominator=30,
            resolved_label_fraction_numerator=30,
            unresolved_coverage_count=0,
            positive_count=10,
            negative_count=20,
            candidate_arm=ArmPrecision(surfaced_resolved=30, positive_surfaced_resolved=10),
            control_arm=ArmPrecision(surfaced_resolved=30, positive_surfaced_resolved=10),
            difference_lower_bound=Decimal("-0.05"),
            median_lead_time_advantage_seconds=Decimal(300),
            qualifies_sample_adequacy=False,
        )
        return replace(base, **overrides)  # type: ignore[arg-type]

    def test_adequate_domain_qualifies(self) -> None:
        assert sample_adequacy_pass(self._evaluation()) is True

    def test_fewer_than_min_resolved_fails(self) -> None:
        evaluation = self._evaluation(
            resolved_label_fraction_denominator=29,
            resolved_label_fraction_numerator=29,
        )
        assert sample_adequacy_pass(evaluation) is False

    def test_fewer_than_min_positives_fails(self) -> None:
        evaluation = self._evaluation(positive_count=9, negative_count=21)
        assert sample_adequacy_pass(evaluation) is False

    def test_fewer_than_min_surfaced_per_arm_fails(self) -> None:
        assert sample_adequacy_pass(self._evaluation(candidate_arm=ArmPrecision(19, 10))) is False
        assert sample_adequacy_pass(self._evaluation(control_arm=ArmPrecision(19, 10))) is False

    def test_resolved_label_fraction_gate(self) -> None:
        # 26 resolved of 30 retained: 26/30 = 8666 bps < 9000 -> not adequate.
        evaluation = self._evaluation(
            resolved_label_fraction_numerator=26, unresolved_coverage_count=4
        )
        assert evaluation.resolved_label_fraction_bps == (26 * 10000) // 30
        assert sample_adequacy_pass(evaluation) is False

    def test_domain_gate_properties(self) -> None:
        evaluation = self._evaluation(qualifies_sample_adequacy=True)
        assert evaluation.noninferiority_pass is True
        assert evaluation.lead_time_pass is True
        assert evaluation.promotion_eligible is True
        failing = self._evaluation(difference_lower_bound=Decimal("-0.11"))
        assert failing.noninferiority_pass is False
        assert failing.promotion_eligible is False


# ---------------------------------------------------------------------------
# Application-service fixtures (synthetic but valid durable artifacts)
# ---------------------------------------------------------------------------

FROZEN_FREEZE = "frozen"
DRIFTED_FREEZE = "drifted"


def _freeze_receipt(status: str) -> CandidateFreezeReceipt:
    frozen = status == FROZEN_FREEZE
    inputs = FreezeInputs(
        preregistration_digest=Digest("sha256:" + "2" * 64),
        preregistration_config_digest=PEF_CONFIGURATION_DIGEST,
        implementation_commit="a" * 64 if frozen else None,
        implementation_tree_digest="b" * 64 if frozen else None,
        dependency_lock_digest=Digest("sha256:" + "3" * 64) if frozen else None,
        source_registry_digest=Digest("sha256:" + "4" * 64) if frozen else None,
        registry_entry_digests=() if frozen else None,
    )
    receipt = build_candidate_freeze_receipt(inputs, frozen_at=_at(0))
    assert receipt.status is (FreezeStatus.FROZEN if frozen else FreezeStatus.DRIFTED)
    return receipt


def _shadow_run(
    as_of: datetime, status: ShadowRunStatus = ShadowRunStatus.RAN
) -> ShadowExperimentRun:
    return ShadowExperimentRun(
        as_of=as_of,
        generated_at=as_of,
        control_snapshot_id="snapshot_" + "1" * 64,
        control_receipt_id="receipt_" + "2" * 64,
        coverage_state=HealthValue.OK,
        freshness_state=HealthValue.OK,
        transport_state=HealthValue.OK,
        schema_state=HealthValue.OK,
        status=status,
        episode_universe_digest=Digest("sha256:" + "4" * 64),
        candidate_artifact_id="artifact_" + "5" * 64,
        candidate_output_digest=Digest("sha256:" + "6" * 64),
        control_ranking=(ShadowControlArmRanking(rank=1, episode_id="ep_main"),)
        if status is ShadowRunStatus.RAN
        else (),
        failure_reason=None if status is ShadowRunStatus.RAN else "candidate arm failed",
    )


def _snapshot(
    as_of: datetime,
    anchor: AnchorObservation,
    status: ShadowRunStatus = ShadowRunStatus.RAN,
) -> PairedSnapshot:
    return PairedSnapshot(
        run=_shadow_run(as_of, status=status),
        candidate_rank_by_episode={"ep_main": 7},
        episode_memberships={"ep_main": (anchor.observation_id,)},
    )


class TestApplicationService:
    HORIZON = _at(86400 + 2 * CADENCE)

    def _evaluate(
        self,
        anchor: AnchorObservation,
        *,
        freeze_status: str,
        run_status: ShadowRunStatus = ShadowRunStatus.RAN,
    ):
        return evaluate_shadow_experiment(
            snapshots=(_snapshot(_at(2 * CADENCE), anchor, run_status),),
            opportunity_groups=(_group(anchor, outcome=OutcomeLabel.POSITIVE),),
            freeze_receipt=_freeze_receipt(freeze_status),
            evaluation_horizon=self.HORIZON,
            generated_at=self.HORIZON,
        )

    def test_insufficient_sample_is_explicit_epistemic_state(self) -> None:
        anchor = _anchor("app1", observed_at=_at(CADENCE))
        receipt = self._evaluate(anchor, freeze_status=FROZEN_FREEZE)
        assert receipt.status is EvaluationStatus.INSUFFICIENT_SAMPLE
        assert receipt.verdict is None
        assert receipt.confirmatory_evidence is False
        assert receipt.status_reason is not None
        assert receipt.qualifying_domain_count < 2

    def test_failed_run_does_not_masquerade_as_complete(self) -> None:
        anchor = _anchor("app2", observed_at=_at(CADENCE))
        receipt = self._evaluate(
            anchor, freeze_status=FROZEN_FREEZE, run_status=ShadowRunStatus.FAILED
        )
        assert receipt.status is EvaluationStatus.FAILED
        assert receipt.verdict is None
        assert receipt.confirmatory_evidence is False

    def test_drifted_freeze_invalidates_confirmatory_status(self) -> None:
        anchor = _anchor("app3", observed_at=_at(CADENCE))
        receipt = self._evaluate(anchor, freeze_status=DRIFTED_FREEZE)
        assert receipt.status is EvaluationStatus.INVALID_DRIFT
        assert receipt.verdict is None
        assert receipt.confirmatory_evidence is False
        assert receipt.freeze_status is FreezeStatus.DRIFTED

    def test_paired_anchor_tracking_symmetry(self) -> None:
        # The shared universe means the anchor's episode exists for BOTH arms
        # at every snapshot: the paired design is preserved by construction.
        from frontier.application.evaluation import build_anchor_tracking

        anchor = _anchor("app4", observed_at=_at(CADENCE))
        snapshot = _snapshot(_at(2 * CADENCE), anchor)
        (opportunity,) = build_retained_opportunities(
            (_group(anchor, outcome=OutcomeLabel.NEGATIVE),)
        )
        (entry,) = build_anchor_tracking(opportunity, (snapshot,))
        assert entry.episode_id == "ep_main"
        assert entry.control_rank == 1
        assert entry.candidate_rank == 7
        assert entry.as_of == snapshot.run.as_of


def _counts(**overrides: int):
    values: dict[str, int] = {
        "opportunity_groups": 0,
        "anchors_retained": 0,
        "unqualified_mixed_count": 0,
        "unqualified_count": 0,
        "resolved_positive": 0,
        "resolved_negative": 0,
        "unresolved_coverage": 0,
    }
    values.update(overrides)
    return EvaluationCounts(**values)


def _receipt(**overrides: object):
    from frontier.domain.evaluation import EvaluationReceipt

    params: dict[str, object] = {
        "as_of": _at(90000),
        "generated_at": _at(0),
        "status": EvaluationStatus.INSUFFICIENT_SAMPLE,
        "status_reason": "insufficient sample reason",
        "counts": _counts(),
        "shadow_runs": (
            ShadowRunBinding(
                run_id="shadowrun_" + "9" * 64, run_digest=Digest("sha256:" + "8" * 64)
            ),
        ),
        "candidate_freeze_receipt_id": "freezereceipt_" + "c" * 64,
        "freeze_receipt_digest": Digest("sha256:" + "c" * 64),
        "preregistration_digest": Digest("sha256:" + "2" * 64),
        "freeze_status": FreezeStatus.FROZEN,
        "domains": (),
        "pooled_median_lead_time_advantage_seconds": None,
        "verdict": None,
    }
    params.update(overrides)
    return EvaluationReceipt(**params)  # type: ignore[arg-type]


class TestReceiptSemantics:
    def test_determinism_same_inputs_same_digest(self) -> None:
        first = _receipt()
        second = _receipt()
        assert first.evaluation_id == second.evaluation_id
        assert first.receipt_digest == second.receipt_digest
        assert first.to_canonical() == second.to_canonical()

    def test_different_payloads_bind_different_digests(self) -> None:
        changed = _receipt(counts=_counts(resolved_positive=1, anchors_retained=1))
        assert changed.evaluation_id != _receipt().evaluation_id

    def test_incomplete_statuses_cannot_masquerade(self) -> None:
        for status in (
            EvaluationStatus.INSUFFICIENT_SAMPLE,
            EvaluationStatus.FAILED,
            EvaluationStatus.INVALID_DRIFT,
        ):
            receipt = _receipt(status=status)
            assert receipt.verdict is None
            assert receipt.confirmatory_evidence is False

    def test_complete_requires_frozen_freeze(self) -> None:

        with pytest.raises(ValueError, match="FROZEN freeze receipt"):
            _receipt(
                status=EvaluationStatus.COMPLETE,
                status_reason=None,
                verdict="SUPPORTED",
                freeze_status=FreezeStatus.DRIFTED,
            )

    def test_complete_requires_verdict(self) -> None:

        with pytest.raises(ValueError, match="verdict"):
            _receipt(status=EvaluationStatus.COMPLETE, status_reason=None, verdict=None)

    def test_no_truth_labelling_keys(self) -> None:
        receipt = _receipt()
        canonical = cast(dict[str, object], receipt.to_canonical())
        forbidden = ("truth", "confidence", "probability")

        def walk(node: object) -> None:
            if isinstance(node, dict):
                entries = cast(dict[str, object], node)
                for key, nested in entries.items():
                    lowered = key.lower()
                    assert not any(word in lowered for word in forbidden), key
                    walk(nested)
            elif isinstance(node, list):
                items = cast(list[object], node)
                for item in items:
                    walk(item)

        walk(canonical)
        assert receipt.authority_state == "EXPERIMENTAL_EVALUATION"
        assert canonical["candidate_authority_state"] == "EXPERIMENTAL_SHADOW"
        assert "EXPERIMENTAL_COMPARISON_NOT_TRUTH" in str(
            EVALUATION_CONFIGURATION["verdict_semantics"]
        )


class TestPooledLeadTime:
    def test_pool_includes_misses_and_skips_underpowered_domains(self) -> None:
        late = _opportunity("pool1", DOMAIN_SOFTWARE_PACKAGES, OutcomeLabel.POSITIVE, _at(CADENCE))
        early = _opportunity(
            "pool2", DOMAIN_SOFTWARE_PACKAGES, OutcomeLabel.POSITIVE, _at(2 * CADENCE)
        )
        other = _opportunity("pool3", DOMAIN_AI_MODELS, OutcomeLabel.POSITIVE, _at(CADENCE))
        adequate = DomainEvaluation(
            domain=DOMAIN_SOFTWARE_PACKAGES,
            resolved_label_fraction_denominator=30,
            resolved_label_fraction_numerator=30,
            unresolved_coverage_count=0,
            positive_count=10,
            negative_count=20,
            candidate_arm=ArmPrecision(20, 10),
            control_arm=ArmPrecision(20, 10),
            difference_lower_bound=Decimal("-0.05"),
            median_lead_time_advantage_seconds=Decimal(300),
            qualifies_sample_adequacy=True,
        )
        underpowered = replace(adequate, domain=DOMAIN_AI_MODELS, qualifies_sample_adequacy=False)
        tracking = {
            late.anchor.observation_id: (
                _track_at(_at(CADENCE), "ep", control_rank=None, candidate_rank=1),
            ),
            early.anchor.observation_id: (
                _track_at(_at(2 * CADENCE), "ep", control_rank=None, candidate_rank=1),
                _track_at(_at(3 * CADENCE), "ep", control_rank=1, candidate_rank=1),
            ),
            other.anchor.observation_id: (
                _track_at(_at(2 * CADENCE), "ep", control_rank=1, candidate_rank=1),
            ),
        }
        pooled = pooled_lead_time_median((adequate, underpowered), tracking, (late, early, other))
        # late: control misses -> control detection = resolution_at -> 86400;
        # early: control detected 900 seconds later -> 300; median = 43350.
        assert pooled == Decimal(43350)
