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
    CoverageRequirement,
    EvidenceCollectionState,
    ExposureState,
    ObservatoryArm,
    OutcomeEvidenceRef,
    OutcomeState,
    PopulationMember,
    RegisteredOutcomeDefinition,
    SourceHealthBinding,
    ValueObservatoryCapture,
    ValueObservatoryOpportunity,
    ValueObservatoryOutcome,
    ValueObservatoryPopulationManifest,
    require_outcome_opportunity_binding,
    require_population_opportunity_completeness,
)


def digest(char: str) -> Digest:
    return Digest("sha256:" + char * 64)


def health(
    source_id: str = "pypi.updates",
    *,
    at: datetime | None = None,
    digest_char: str = "a",
    value: HealthValue = HealthValue.OK,
) -> SourceHealthBinding:
    if at is None:
        at = datetime(2026, 9, 12, 0, 29, tzinfo=UTC)
    return SourceHealthBinding(
        health_observation_id="health_" + digest_char * 64,
        source_id=source_id,
        as_of=at,
        transport=value,
        freshness=value,
        completeness=value,
        schema=value,
    )


def coverage_requirement(
    source_id: str = "hn.frontpage",
    *,
    offset_seconds: int = 21_600,
) -> CoverageRequirement:
    return CoverageRequirement(
        source_id=source_id,
        offset_seconds_from_anchor=offset_seconds,
    )


def outcome_definition(**changes: Any) -> RegisteredOutcomeDefinition:
    base: dict[str, Any] = {
        "outcome_definition_id": "follow-on-attention-v0",
        "outcome_protocol_digest": digest("9"),
        "horizon_seconds": 86_400,
        "coverage_requirements": (
            coverage_requirement(offset_seconds=21_600),
            coverage_requirement(offset_seconds=43_200),
        ),
    }
    base.update(changes)
    return RegisteredOutcomeDefinition(**base)


def population_member(
    key: str = "population_item_1",
    *,
    digest_char: str = "3",
) -> PopulationMember:
    return PopulationMember(
        member_key=key,
        domain="SOFTWARE_PACKAGES",
        anchor_at=datetime(2026, 9, 12, 0, 30, tzinfo=UTC),
        anchor_payload_digest=digest(digest_char),
        anchor_refs=(f"obs_{key}",),
        canonical_urls=(f"https://pypi.org/project/{key}/1.0.0/",),
    )


def population(**changes: Any) -> ValueObservatoryPopulationManifest:
    base: dict[str, Any] = {
        "knowledge_horizon": datetime(2026, 9, 12, 0, 30, tzinfo=UTC),
        "recorded_at": datetime(2026, 9, 12, 0, 30, 30, tzinfo=UTC),
        "population_protocol_digest": digest("1"),
        "domain_scope": ("SOFTWARE_PACKAGES",),
        "members": (population_member(),),
        "source_health_bindings": (health(),),
    }
    base.update(changes)
    return ValueObservatoryPopulationManifest(**base)


def executor(**changes: Any) -> BenchmarkExecutorIdentity:
    base: dict[str, Any] = {
        "executor_id": "frontier-naive-control",
        "executor_version": "v0",
        "configuration_digest": digest("1"),
    }
    base.update(changes)
    return BenchmarkExecutorIdentity(**base)


def opportunity(
    *,
    source_population: ValueObservatoryPopulationManifest | None = None,
    **changes: Any,
) -> ValueObservatoryOpportunity:
    if source_population is None:
        source_population = population()
    member = source_population.members[0]
    base: dict[str, Any] = {
        "population_manifest_id": source_population.population_id,
        "population_member_key": member.member_key,
        "domain": member.domain,
        "anchor_at": member.anchor_at,
        "recorded_at": datetime(2026, 9, 12, 0, 31, tzinfo=UTC),
        "opportunity_protocol_digest": digest("2"),
        "anchor_payload_digest": member.anchor_payload_digest,
        "anchor_refs": member.anchor_refs,
        "canonical_urls": member.canonical_urls,
        "source_health_bindings": (health(),),
        "outcome_definitions": (outcome_definition(),),
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


def evidence(**changes: Any) -> OutcomeEvidenceRef:
    base: dict[str, Any] = {
        "evidence_key": "obs_follow_on",
        "source_id": "hn.frontpage",
        "role": "ATTENTION",
        "available_at": datetime(2026, 9, 12, 7, 59, tzinfo=UTC),
        "observed_at": datetime(2026, 9, 12, 8, 0, tzinfo=UTC),
        "collection_state": EvidenceCollectionState.PROSPECTIVE,
        "payload_digest": digest("8"),
    }
    base.update(changes)
    return OutcomeEvidenceRef(**base)


def complete_coverage(
    source_opportunity: ValueObservatoryOpportunity,
    definition: RegisteredOutcomeDefinition | None = None,
    *,
    value: HealthValue = HealthValue.OK,
) -> tuple[SourceHealthBinding, ...]:
    if definition is None:
        definition = source_opportunity.outcome_definitions[0]
    bindings: list[SourceHealthBinding] = []
    for index, requirement in enumerate(definition.coverage_requirements):
        bindings.append(
            health(
                requirement.source_id,
                at=source_opportunity.anchor_at
                + timedelta(seconds=requirement.offset_seconds_from_anchor),
                digest_char=chr(ord("d") + index),
                value=value,
            )
        )
    return tuple(bindings)


def outcome(
    source_opportunity: ValueObservatoryOpportunity,
    **changes: Any,
) -> ValueObservatoryOutcome:
    definition = source_opportunity.outcome_definitions[0]
    base: dict[str, Any] = {
        "opportunity_id": source_opportunity.opportunity_id,
        "opportunity_anchor_at": source_opportunity.anchor_at,
        "opportunity_recorded_at": source_opportunity.recorded_at,
        "outcome_definition": definition,
        "resolution_at": source_opportunity.anchor_at
        + timedelta(seconds=definition.horizon_seconds),
        "evaluated_at": source_opportunity.anchor_at
        + timedelta(seconds=definition.horizon_seconds, minutes=5),
        "state": OutcomeState.POSITIVE,
        "exposure_state": ExposureState.SHADOW_UNEXPOSED,
        "evidence": (evidence(),),
        "coverage_bindings": complete_coverage(source_opportunity, definition),
    }
    base.update(changes)
    return ValueObservatoryOutcome(**base)


def test_population_is_content_addressed_and_order_stable() -> None:
    members = (
        population_member("population_item_1", digest_char="3"),
        population_member("population_item_2", digest_char="4"),
    )
    first = population(members=members)
    second = population(members=tuple(reversed(members)))
    assert first.population_id == second.population_id
    assert first.population_digest == second.population_digest
    assert first.population_id.startswith("valuepopulation_")


def test_population_rejects_future_members_and_health() -> None:
    future_member = replace(
        population_member(),
        anchor_at=datetime(2026, 9, 12, 0, 31, tzinfo=UTC),
    )
    with pytest.raises(ValueError, match="after the knowledge horizon"):
        population(members=(future_member,))
    future_health = health(at=datetime(2026, 9, 12, 0, 31, tzinfo=UTC))
    with pytest.raises(ValueError, match="after the knowledge horizon"):
        population(source_health_bindings=(future_health,))


def test_population_completeness_requires_every_arm_independent_member() -> None:
    source_population = population(
        members=(
            population_member("population_item_1", digest_char="3"),
            population_member("population_item_2", digest_char="4"),
        )
    )
    first = opportunity(source_population=source_population)
    second_member = source_population.members[1]
    second = opportunity(
        source_population=source_population,
        population_member_key=second_member.member_key,
        domain=second_member.domain,
        anchor_at=second_member.anchor_at,
        anchor_payload_digest=second_member.anchor_payload_digest,
        anchor_refs=second_member.anchor_refs,
        canonical_urls=second_member.canonical_urls,
    )
    require_population_opportunity_completeness(source_population, (first, second))
    with pytest.raises(ValueError, match="exactly cover"):
        require_population_opportunity_completeness(source_population, (first,))


def test_population_binding_rejects_member_payload_drift() -> None:
    source_population = population()
    drifted = opportunity(source_population=source_population, anchor_payload_digest=digest("f"))
    with pytest.raises(ValueError, match="payload"):
        require_population_opportunity_completeness(source_population, (drifted,))


def test_opportunity_is_content_addressed_and_order_stable() -> None:
    source_population = population()
    first = opportunity(
        source_population=source_population,
        source_health_bindings=(
            health(digest_char="a"),
            health("hn.frontpage", digest_char="b"),
        ),
    )
    second = opportunity(
        source_population=source_population,
        source_health_bindings=tuple(reversed(first.source_health_bindings)),
    )
    assert first.opportunity_id == second.opportunity_id
    assert first.opportunity_digest == second.opportunity_digest
    assert first.opportunity_id.startswith("valueopportunity_")


def test_opportunity_rejects_retrospective_registration_and_future_health() -> None:
    with pytest.raises(ValueError, match="before its anchor"):
        opportunity(recorded_at=datetime(2026, 9, 12, 0, 29, tzinfo=UTC))
    future_health = health(at=datetime(2026, 9, 12, 0, 31, tzinfo=UTC))
    with pytest.raises(ValueError, match="after the anchor horizon"):
        opportunity(source_health_bindings=(future_health,))


def test_opportunity_requires_anchor_health_and_preregistered_outcomes() -> None:
    with pytest.raises(ValueError, match="anchor reference"):
        opportunity(anchor_refs=())
    with pytest.raises(ValueError, match="source health bindings"):
        opportunity(source_health_bindings=())
    with pytest.raises(ValueError, match="preregistered outcome"):
        opportunity(outcome_definitions=())


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


def test_web_llm_capture_requires_provider_model_and_prompt_identity() -> None:
    for identity in (
        executor(model="model-v1", prompt_digest=digest("a")),
        executor(provider="provider", prompt_digest=digest("a")),
        executor(provider="provider", model="model-v1"),
    ):
        with pytest.raises(ValueError, match="provider, exact model, and prompt digest"):
            capture(arm=ObservatoryArm.WEB_LLM_BENCHMARK, executor=identity)
    complete = capture(
        arm=ObservatoryArm.WEB_LLM_BENCHMARK,
        executor=executor(
            provider="provider",
            model="model-v1",
            prompt_digest=digest("a"),
        ),
    )
    assert complete.executor.model == "model-v1"


def test_outcome_is_independent_of_capture_so_misses_remain_measurable() -> None:
    source_opportunity = opportunity()
    result = outcome(source_opportunity)
    assert result.opportunity_id == source_opportunity.opportunity_id
    assert "capture_id" not in result.to_canonical()


def test_positive_outcome_requires_future_evidence_after_registration() -> None:
    source_opportunity = opportunity()
    with pytest.raises(ValueError, match="requires supporting"):
        outcome(source_opportunity, evidence=())
    leaked = evidence(
        available_at=source_opportunity.recorded_at,
        observed_at=source_opportunity.recorded_at + timedelta(seconds=1),
    )
    with pytest.raises(ValueError, match="become available after registration"):
        outcome(source_opportunity, evidence=(leaked,))


def test_positive_outcome_rejects_late_observed_old_or_recovered_material() -> None:
    source_opportunity = opportunity()
    old_material = evidence(
        available_at=source_opportunity.anchor_at,
        observed_at=datetime(2026, 9, 12, 8, 0, tzinfo=UTC),
        collection_state=EvidenceCollectionState.RECOVERED,
    )
    with pytest.raises(ValueError, match="become available after registration"):
        outcome(source_opportunity, evidence=(old_material,))
    recovered = evidence(collection_state=EvidenceCollectionState.RECOVERED)
    with pytest.raises(ValueError, match="recovered outcome evidence"):
        outcome(source_opportunity, evidence=(recovered,))


def test_positive_outcome_rejects_post_horizon_evidence() -> None:
    source_opportunity = opportunity()
    late = evidence(
        available_at=source_opportunity.anchor_at + timedelta(days=1, seconds=1),
        observed_at=source_opportunity.anchor_at + timedelta(days=1, seconds=2),
    )
    with pytest.raises(ValueError, match="observed prospectively within the horizon"):
        outcome(source_opportunity, evidence=(late,))


def test_outcome_definition_must_match_preregistered_opportunity_rule() -> None:
    source_opportunity = opportunity()
    changed = outcome_definition(
        outcome_definition_id="post-hoc-definition",
        outcome_protocol_digest=digest("f"),
        horizon_seconds=43_200,
        coverage_requirements=(coverage_requirement(offset_seconds=21_600),),
    )
    result = outcome(
        source_opportunity,
        outcome_definition=changed,
        resolution_at=source_opportunity.anchor_at + timedelta(seconds=43_200),
        evaluated_at=source_opportunity.anchor_at + timedelta(seconds=43_200, minutes=5),
        coverage_bindings=complete_coverage(source_opportunity, changed),
    )
    with pytest.raises(ValueError, match="not preregistered"):
        require_outcome_opportunity_binding(source_opportunity, result)


def test_negative_requires_preregistered_complete_healthy_coverage() -> None:
    source_opportunity = opportunity()
    definition = source_opportunity.outcome_definitions[0]
    complete = complete_coverage(source_opportunity, definition)
    valid = outcome(
        source_opportunity,
        state=OutcomeState.NEGATIVE_WITH_ADEQUATE_COVERAGE,
        evidence=(),
        coverage_bindings=complete,
    )
    assert valid.state is OutcomeState.NEGATIVE_WITH_ADEQUATE_COVERAGE

    with pytest.raises(ValueError, match="boundary set"):
        outcome(
            source_opportunity,
            state=OutcomeState.NEGATIVE_WITH_ADEQUATE_COVERAGE,
            evidence=(),
            coverage_bindings=(complete[0],),
        )

    failed = replace(
        complete[0],
        transport=HealthValue.FAILED,
        freshness=HealthValue.FAILED,
        completeness=HealthValue.FAILED,
        schema=HealthValue.FAILED,
    )
    with pytest.raises(ValueError, match="health threshold"):
        outcome(
            source_opportunity,
            state=OutcomeState.NEGATIVE_WITH_ADEQUATE_COVERAGE,
            evidence=(),
            coverage_bindings=(failed, complete[1]),
        )


def test_negative_rejects_unregistered_coverage_policy() -> None:
    source_population = population()
    no_coverage = outcome_definition(coverage_requirements=())
    source_opportunity = opportunity(
        source_population=source_population,
        outcome_definitions=(no_coverage,),
    )
    with pytest.raises(ValueError, match="preregistered coverage requirements"):
        outcome(
            source_opportunity,
            state=OutcomeState.NEGATIVE_WITH_ADEQUATE_COVERAGE,
            evidence=(),
            coverage_bindings=(),
        )


def test_coverage_rejects_duplicate_source_boundary_or_future_health() -> None:
    source_opportunity = opportunity()
    first = complete_coverage(source_opportunity)[0]
    duplicate_boundary = replace(
        first,
        health_observation_id="health_" + "f" * 64,
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
    extra = evidence(
        evidence_key="obs_second",
        source_id="github.ml-repos",
        role="BEHAVIORAL",
        available_at=datetime(2026, 9, 12, 6, 59, tzinfo=UTC),
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
