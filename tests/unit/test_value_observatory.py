from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from frontier.domain.digests import Digest
from frontier.domain.health import HealthValue
from frontier.domain.value_observatory import (
    BenchmarkExecutorIdentity,
    CaptureItem,
    CaptureStatus,
    ExposureState,
    ObservatoryArm,
    OutcomeEvidenceRef,
    OutcomeState,
    SourceHealthBinding,
    ValueObservatoryCapture,
    ValueObservatoryOpportunity,
    ValueObservatoryOutcome,
    require_outcome_opportunity_binding,
)


def digest(char: str) -> Digest:
    return Digest("sha256:" + char * 64)


def health(
    source_id: str = "pypi.updates",
    *,
    at: datetime | None = None,
    digest_char: str = "a",
) -> SourceHealthBinding:
    if at is None:
        at = datetime(2026, 9, 12, 0, 29, tzinfo=UTC)
    return SourceHealthBinding(
        health_observation_id="health_" + digest_char * 64,
        source_id=source_id,
        as_of=at,
        transport=HealthValue.OK,
        freshness=HealthValue.OK,
        completeness=HealthValue.OK,
        schema=HealthValue.OK,
    )


def executor() -> BenchmarkExecutorIdentity:
    return BenchmarkExecutorIdentity(
        executor_id="frontier-naive-control",
        executor_version="v0",
        configuration_digest=digest("1"),
    )


def opportunity(**changes: Any) -> ValueObservatoryOpportunity:
    base: dict[str, Any] = {
        "domain": "SOFTWARE_PACKAGES",
        "anchor_at": datetime(2026, 9, 12, 0, 30, tzinfo=UTC),
        "recorded_at": datetime(2026, 9, 12, 0, 31, tzinfo=UTC),
        "opportunity_protocol_digest": digest("2"),
        "anchor_payload_digest": digest("3"),
        "anchor_refs": ("obs_seed",),
        "canonical_urls": ("https://pypi.org/project/example/1.0.0/",),
        "source_health_bindings": (health(),),
    }
    base.update(changes)
    return ValueObservatoryOpportunity(**base)


def item(position: int = 1, key: str = "episode_1") -> CaptureItem:
    return CaptureItem(
        position=position,
        item_key=key,
        raw_item_digest=digest("4"),
        title="Example",
        canonical_urls=("https://example.com/a",),
        evidence_refs=("obs_1",),
    )


def capture(**changes: Any) -> ValueObservatoryCapture:
    base: dict[str, Any] = {
        "arm": ObservatoryArm.FRONTIER_NAIVE_CONTROL,
        "captured_at": datetime(2026, 9, 12, 1, 0, 5, tzinfo=UTC),
        "knowledge_horizon": datetime(2026, 9, 12, 1, 0, tzinfo=UTC),
        "selection_window_start": datetime(2026, 9, 11, 1, 0, tzinfo=UTC),
        "selection_window_end": datetime(2026, 9, 12, 1, 0, tzinfo=UTC),
        "alert_budget": 20,
        "domain_scope": ("AI_MODELS", "SOFTWARE_PACKAGES"),
        "executor": executor(),
        "protocol_digest": digest("5"),
        "input_digest": digest("6"),
        "source_health_bindings": (
            health(
                at=datetime(2026, 9, 12, 0, 59, tzinfo=UTC),
                digest_char="b",
            ),
            health(
                "hn.frontpage",
                at=datetime(2026, 9, 12, 0, 58, tzinfo=UTC),
                digest_char="c",
            ),
        ),
        "items": (item(),),
        "status": CaptureStatus.COMPLETE,
        "raw_response_digest": digest("7"),
    }
    base.update(changes)
    return ValueObservatoryCapture(**base)


def evidence() -> OutcomeEvidenceRef:
    return OutcomeEvidenceRef(
        evidence_key="obs_follow_on",
        source_id="hn.frontpage",
        role="ATTENTION",
        observed_at=datetime(2026, 9, 12, 8, 0, tzinfo=UTC),
        payload_digest=digest("8"),
    )


def outcome(
    source_opportunity: ValueObservatoryOpportunity,
    **changes: Any,
) -> ValueObservatoryOutcome:
    horizon_seconds = 86_400
    base: dict[str, Any] = {
        "opportunity_id": source_opportunity.opportunity_id,
        "opportunity_anchor_at": source_opportunity.anchor_at,
        "opportunity_recorded_at": source_opportunity.recorded_at,
        "outcome_definition_id": "follow-on-attention-v0",
        "outcome_protocol_digest": digest("9"),
        "horizon_seconds": horizon_seconds,
        "resolution_at": source_opportunity.anchor_at + timedelta(seconds=horizon_seconds),
        "evaluated_at": source_opportunity.anchor_at
        + timedelta(seconds=horizon_seconds, minutes=5),
        "state": OutcomeState.POSITIVE,
        "exposure_state": ExposureState.SHADOW_UNEXPOSED,
        "evidence": (evidence(),),
        "coverage_bindings": (
            health(
                "hn.frontpage",
                at=datetime(2026, 9, 12, 6, 0, tzinfo=UTC),
                digest_char="d",
            ),
        ),
    }
    base.update(changes)
    return ValueObservatoryOutcome(**base)


def test_opportunity_is_content_addressed_and_order_stable() -> None:
    first = opportunity(
        source_health_bindings=(
            health(digest_char="a"),
            health("hn.frontpage", digest_char="b"),
        )
    )
    second = opportunity(source_health_bindings=tuple(reversed(first.source_health_bindings)))
    assert first.opportunity_id == second.opportunity_id
    assert first.opportunity_digest == second.opportunity_digest
    assert first.opportunity_id.startswith("valueopportunity_")


def test_opportunity_rejects_retrospective_registration_and_future_health() -> None:
    with pytest.raises(ValueError, match="before its anchor"):
        opportunity(recorded_at=datetime(2026, 9, 12, 0, 29, tzinfo=UTC))
    future_health = health(at=datetime(2026, 9, 12, 0, 31, tzinfo=UTC))
    with pytest.raises(ValueError, match="after the anchor horizon"):
        opportunity(source_health_bindings=(future_health,))


def test_opportunity_requires_independent_anchor_material_and_health() -> None:
    with pytest.raises(ValueError, match="anchor reference"):
        opportunity(anchor_refs=())
    with pytest.raises(ValueError, match="source health bindings"):
        opportunity(source_health_bindings=())


def test_complete_capture_is_content_addressed_and_order_stable() -> None:
    first = capture()
    second = capture(source_health_bindings=tuple(reversed(first.source_health_bindings)))
    assert first.capture_id == second.capture_id
    assert first.capture_digest == second.capture_digest
    assert first.capture_id.startswith("valuecapture_")


def test_capture_identity_changes_when_bound_health_changes() -> None:
    first = capture()
    changed_health = replace(first.source_health_bindings[0], freshness=HealthValue.DEGRADED)
    second = capture(source_health_bindings=(changed_health, first.source_health_bindings[1]))
    assert first.capture_id != second.capture_id


def test_capture_rejects_future_knowledge_and_future_health() -> None:
    with pytest.raises(ValueError, match="knowledge horizon"):
        capture(knowledge_horizon=datetime(2026, 9, 12, 1, 1, tzinfo=UTC))
    future_health = health(
        at=datetime(2026, 9, 12, 1, 1, tzinfo=UTC),
        digest_char="e",
    )
    with pytest.raises(ValueError, match="after the knowledge horizon"):
        capture(source_health_bindings=(future_health,))


def test_capture_requires_source_health_context() -> None:
    with pytest.raises(ValueError, match="source health bindings"):
        capture(source_health_bindings=())


def test_capture_rejects_noncontiguous_or_overbudget_alerts() -> None:
    with pytest.raises(ValueError, match="contiguous"):
        capture(items=(item(position=2),))
    with pytest.raises(ValueError, match="exceeds"):
        capture(alert_budget=1, items=(item(1, "a"), item(2, "b")))


def test_failed_capture_is_a_first_class_content_addressed_artifact() -> None:
    failed = capture(
        status=CaptureStatus.FAILED,
        items=(),
        raw_response_digest=None,
        failure_reason="provider timeout",
    )
    assert failed.capture_id.startswith("valuecapture_")
    assert failed.to_canonical()["failure_reason"] == "provider timeout"


def test_capture_status_rules_fail_closed() -> None:
    with pytest.raises(ValueError, match="raw_response_digest"):
        capture(raw_response_digest=None)
    with pytest.raises(ValueError, match="failed capture cannot carry"):
        capture(status=CaptureStatus.FAILED, failure_reason="boom")


def test_outcome_is_independent_of_capture_so_misses_remain_measurable() -> None:
    source_opportunity = opportunity()
    result = outcome(source_opportunity)
    assert result.opportunity_id == source_opportunity.opportunity_id
    assert "capture_id" not in result.to_canonical()


def test_positive_outcome_requires_future_evidence_after_registration() -> None:
    source_opportunity = opportunity()
    with pytest.raises(ValueError, match="requires supporting"):
        outcome(source_opportunity, evidence=())
    leaked = replace(
        evidence(),
        observed_at=source_opportunity.recorded_at,
    )
    with pytest.raises(ValueError, match="future-only"):
        outcome(source_opportunity, evidence=(leaked,))


def test_positive_outcome_rejects_post_horizon_evidence() -> None:
    source_opportunity = opportunity()
    late = replace(
        evidence(),
        observed_at=source_opportunity.anchor_at + timedelta(days=1, seconds=1),
    )
    with pytest.raises(ValueError, match="within the outcome horizon"):
        outcome(source_opportunity, evidence=(late,))


def test_negative_requires_explicit_coverage_binding() -> None:
    source_opportunity = opportunity()
    with pytest.raises(ValueError, match="adequate-coverage"):
        outcome(
            source_opportunity,
            state=OutcomeState.NEGATIVE_WITH_ADEQUATE_COVERAGE,
            evidence=(),
            coverage_bindings=(),
        )


def test_coverage_can_bind_multiple_boundaries_for_same_source() -> None:
    source_opportunity = opportunity()
    result = outcome(
        source_opportunity,
        state=OutcomeState.NEGATIVE_WITH_ADEQUATE_COVERAGE,
        evidence=(),
        coverage_bindings=(
            health(
                "hn.frontpage",
                at=datetime(2026, 9, 12, 6, 0, tzinfo=UTC),
                digest_char="d",
            ),
            health(
                "hn.frontpage",
                at=datetime(2026, 9, 12, 12, 0, tzinfo=UTC),
                digest_char="e",
            ),
        ),
    )
    assert len(result.coverage_bindings) == 2


def test_coverage_rejects_duplicate_source_boundary_or_future_health() -> None:
    source_opportunity = opportunity()
    first = health(
        "hn.frontpage",
        at=datetime(2026, 9, 12, 6, 0, tzinfo=UTC),
        digest_char="d",
    )
    duplicate_boundary = health(
        "hn.frontpage",
        at=datetime(2026, 9, 12, 6, 0, tzinfo=UTC),
        digest_char="e",
    )
    with pytest.raises(ValueError, match="duplicate source boundaries"):
        outcome(source_opportunity, coverage_bindings=(first, duplicate_boundary))
    future_health = health(
        "hn.frontpage",
        at=source_opportunity.anchor_at + timedelta(days=1, seconds=1),
        digest_char="f",
    )
    with pytest.raises(ValueError, match="prospective outcome window"):
        outcome(source_opportunity, coverage_bindings=(future_health,))


def test_unresolved_coverage_requires_reason() -> None:
    source_opportunity = opportunity()
    with pytest.raises(ValueError, match="coverage reason"):
        outcome(
            source_opportunity,
            state=OutcomeState.UNRESOLVED_COVERAGE,
            evidence=(),
            coverage_reason=None,
        )


def test_public_exposure_is_explicit_and_cannot_predate_registration() -> None:
    source_opportunity = opportunity()
    with pytest.raises(ValueError, match="requires exposure_at"):
        outcome(source_opportunity, exposure_state=ExposureState.PUBLICLY_EXPOSED)
    with pytest.raises(ValueError, match="predate opportunity registration"):
        outcome(
            source_opportunity,
            exposure_state=ExposureState.PUBLICLY_EXPOSED,
            exposure_at=source_opportunity.anchor_at,
        )
    exposed = outcome(
        source_opportunity,
        exposure_state=ExposureState.PUBLICLY_EXPOSED,
        exposure_at=datetime(2026, 9, 12, 2, 0, tzinfo=UTC),
    )
    assert exposed.to_canonical()["exposure_state"] == "PUBLICLY_EXPOSED"


def test_unknown_exposure_cannot_smuggle_a_timestamp() -> None:
    source_opportunity = opportunity()
    with pytest.raises(ValueError, match="unknown exposure state"):
        outcome(
            source_opportunity,
            exposure_state=ExposureState.UNKNOWN,
            exposure_at=datetime(2026, 9, 12, 2, 0, tzinfo=UTC),
        )


def test_outcome_is_content_addressed_and_order_stable() -> None:
    source_opportunity = opportunity()
    extra = OutcomeEvidenceRef(
        evidence_key="obs_second",
        source_id="github.ml-repos",
        role="BEHAVIORAL",
        observed_at=datetime(2026, 9, 12, 7, 0, tzinfo=UTC),
        payload_digest=digest("a"),
    )
    first = outcome(source_opportunity, evidence=(evidence(), extra))
    second = outcome(source_opportunity, evidence=(extra, evidence()))
    assert first.outcome_id == second.outcome_id
    assert first.outcome_digest == second.outcome_digest


def test_outcome_opportunity_binding_requires_exact_registration() -> None:
    source_opportunity = opportunity()
    result = outcome(source_opportunity)
    require_outcome_opportunity_binding(source_opportunity, result)
    with pytest.raises(ValueError, match="registration time"):
        require_outcome_opportunity_binding(
            source_opportunity,
            replace(
                result,
                opportunity_recorded_at=source_opportunity.recorded_at + timedelta(seconds=1),
            ),
        )


def test_outcome_rejects_opportunity_registered_after_resolution() -> None:
    source_opportunity = opportunity()
    late_registration = source_opportunity.anchor_at + timedelta(days=1)
    with pytest.raises(ValueError, match="registered before its resolution"):
        outcome(
            source_opportunity,
            opportunity_recorded_at=late_registration,
        )
