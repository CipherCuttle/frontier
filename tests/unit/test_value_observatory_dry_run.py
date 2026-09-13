from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from frontier.application.value_observatory_dry_run import (
    BENCHMARK_CAPTURE_V0_REQUIRED_ARMS,
    BenchmarkArmDryRunEvidence,
    validate_benchmark_capture_v0_dry_run,
)
from frontier.domain.digests import Digest
from frontier.domain.health import HealthValue
from frontier.domain.value_observatory import (
    BenchmarkExecutorIdentity,
    CaptureItem,
    CaptureStatus,
    ObservatoryArm,
    PopulationMember,
    RegisteredOutcomeDefinition,
    SourceHealthBinding,
    ValueObservatoryCapture,
    ValueObservatoryOpportunity,
    ValueObservatoryPopulationManifest,
)

HORIZON = datetime(2026, 9, 14, 12, 0, tzinfo=UTC)
PROTOCOL_DIGEST = Digest("sha256:" + "9" * 64)


def digest(char: str) -> Digest:
    return Digest("sha256:" + char * 64)


def health(
    source_id: str,
    *,
    at: datetime,
    char: str,
) -> SourceHealthBinding:
    return SourceHealthBinding(
        health_observation_id="health_" + char * 64,
        source_id=source_id,
        as_of=at,
        transport=HealthValue.OK,
        freshness=HealthValue.OK,
        completeness=HealthValue.OK,
        schema=HealthValue.OK,
    )


def population_member(
    key: str = "package-1",
    *,
    char: str = "1",
) -> PopulationMember:
    return PopulationMember(
        member_key=key,
        domain="SOFTWARE_PACKAGES",
        anchor_at=HORIZON - timedelta(minutes=5),
        anchor_payload_digest=digest(char),
        anchor_refs=(f"obs-{key}",),
        canonical_urls=(f"https://example.test/{key}",),
    )


def population(
    *,
    members: tuple[PopulationMember, ...] | None = None,
) -> ValueObservatoryPopulationManifest:
    if members is None:
        members = (population_member(),)
    return ValueObservatoryPopulationManifest(
        knowledge_horizon=HORIZON,
        recorded_at=HORIZON + timedelta(seconds=1),
        population_protocol_digest=digest("2"),
        domain_scope=("SOFTWARE_PACKAGES",),
        members=members,
        source_health_bindings=(
            health("pypi.updates", at=HORIZON - timedelta(seconds=30), char="a"),
        ),
    )


def opportunity(
    source_population: ValueObservatoryPopulationManifest,
    *,
    member_index: int = 0,
    recorded_at: datetime | None = None,
) -> ValueObservatoryOpportunity:
    member = source_population.members[member_index]
    if recorded_at is None:
        recorded_at = HORIZON + timedelta(seconds=2)
    return ValueObservatoryOpportunity(
        population_manifest_id=source_population.population_id,
        population_member_key=member.member_key,
        domain=member.domain,
        anchor_at=member.anchor_at,
        recorded_at=recorded_at,
        opportunity_protocol_digest=digest("3"),
        anchor_payload_digest=member.anchor_payload_digest,
        anchor_refs=member.anchor_refs,
        canonical_urls=member.canonical_urls,
        source_health_bindings=(
            health(
                "pypi.updates",
                at=member.anchor_at - timedelta(seconds=1),
                char=chr(ord("b") + member_index),
            ),
        ),
        outcome_definitions=(
            RegisteredOutcomeDefinition(
                outcome_definition_id="follow-on-impact-v0",
                outcome_protocol_digest=digest("4"),
                horizon_seconds=86_400,
            ),
        ),
    )


def executor(arm: ObservatoryArm) -> BenchmarkExecutorIdentity:
    kwargs: dict[str, object] = {
        "executor_id": f"{arm.value.lower()}-dry-run",
        "executor_version": "v0",
        "configuration_digest": digest("5"),
    }
    if arm is ObservatoryArm.WEB_LLM_BENCHMARK:
        kwargs.update(
            provider="test-provider",
            model="test-model-v1",
            prompt_digest=digest("6"),
        )
    return BenchmarkExecutorIdentity(**kwargs)  # type: ignore[arg-type]


def capture(
    arm: ObservatoryArm,
    *,
    status: CaptureStatus = CaptureStatus.COMPLETE,
    **changes: object,
) -> ValueObservatoryCapture:
    base: dict[str, object] = {
        "arm": arm,
        "captured_at": HORIZON + timedelta(seconds=10),
        "knowledge_horizon": HORIZON,
        "selection_window_start": HORIZON - timedelta(hours=24),
        "selection_window_end": HORIZON,
        "alert_budget": 5,
        "domain_scope": ("GLOBAL",),
        "executor": executor(arm),
        "protocol_digest": PROTOCOL_DIGEST,
        "input_digest": digest("7"),
        "source_health_bindings": (
            health(
                "benchmark.input",
                at=HORIZON - timedelta(seconds=1),
                char="d",
            ),
        ),
        "items": (
            CaptureItem(
                position=1,
                item_key="package-1",
                raw_item_digest=digest("8"),
            ),
        ),
        "status": status,
        "raw_response_digest": digest("e"),
        "failure_reason": None,
    }
    if status is CaptureStatus.FAILED:
        base.update(
            items=(),
            raw_response_digest=None,
            failure_reason="point-in-time state unavailable",
        )
    base.update(changes)
    return ValueObservatoryCapture(**base)  # type: ignore[arg-type]


def arm_evidence(
    arm: ObservatoryArm,
    *,
    horizon_enforced: bool = True,
    source_state_horizon: datetime | None = HORIZON,
    started_at: datetime | None = None,
) -> BenchmarkArmDryRunEvidence:
    if started_at is None:
        started_at = HORIZON + timedelta(seconds=3)
    return BenchmarkArmDryRunEvidence(
        arm=arm,
        started_at=started_at,
        horizon_enforced=horizon_enforced,
        source_state_horizon=source_state_horizon,
    )


def valid_boundary() -> tuple[
    ValueObservatoryPopulationManifest,
    tuple[ValueObservatoryOpportunity, ...],
    tuple[ValueObservatoryCapture, ...],
    tuple[BenchmarkArmDryRunEvidence, ...],
]:
    source_population = population()
    opportunities = (opportunity(source_population),)
    captures = tuple(capture(arm) for arm in BENCHMARK_CAPTURE_V0_REQUIRED_ARMS)
    evidence = tuple(arm_evidence(arm) for arm in BENCHMARK_CAPTURE_V0_REQUIRED_ARMS)
    return source_population, opportunities, captures, evidence


def validate(
    source_population: ValueObservatoryPopulationManifest,
    opportunities: tuple[ValueObservatoryOpportunity, ...],
    captures: tuple[ValueObservatoryCapture, ...],
    evidence: tuple[BenchmarkArmDryRunEvidence, ...],
):
    return validate_benchmark_capture_v0_dry_run(
        protocol_digest=PROTOCOL_DIGEST,
        population=source_population,
        opportunities=opportunities,
        captures=captures,
        arm_evidence=evidence,
    )


def test_valid_boundary_proves_all_four_complete_arms_without_scoring() -> None:
    source_population, opportunities, captures, evidence = valid_boundary()
    result = validate(source_population, opportunities, captures, evidence)

    assert result.population_id == source_population.population_id
    assert result.complete_arms == BENCHMARK_CAPTURE_V0_REQUIRED_ARMS
    assert result.failed_arms == ()
    assert len(result.capture_ids) == 4


def test_population_horizon_must_match_frozen_utc_cadence() -> None:
    source_population, opportunities, captures, evidence = valid_boundary()
    off_cadence = HORIZON + timedelta(minutes=1)
    invalid_population = replace(
        source_population,
        knowledge_horizon=off_cadence,
        recorded_at=off_cadence + timedelta(seconds=1),
    )

    with pytest.raises(ValueError, match="aligned to 00:00, 06:00, 12:00, or 18:00 UTC"):
        validate(invalid_population, opportunities, captures, evidence)


def test_population_must_exactly_cover_arm_independent_denominator() -> None:
    source_population = population(
        members=(population_member(), population_member("package-2", char="2"))
    )
    opportunities = (opportunity(source_population),)
    captures = tuple(capture(arm) for arm in BENCHMARK_CAPTURE_V0_REQUIRED_ARMS)
    evidence = tuple(arm_evidence(arm) for arm in BENCHMARK_CAPTURE_V0_REQUIRED_ARMS)

    with pytest.raises(ValueError, match="exactly cover"):
        validate(source_population, opportunities, captures, evidence)


def test_population_and_outcomes_must_be_preregistered_before_any_arm_starts() -> None:
    source_population, _, captures, evidence = valid_boundary()
    late_opportunity = opportunity(
        source_population,
        recorded_at=HORIZON + timedelta(seconds=4),
    )

    with pytest.raises(ValueError, match="preregistered before any benchmark arm starts"):
        validate(source_population, (late_opportunity,), captures, evidence)


def test_registration_must_be_strictly_before_first_arm_start() -> None:
    source_population, _, captures, evidence = valid_boundary()
    first_arm_start = min(item.started_at for item in evidence)

    boundary_population = replace(source_population, recorded_at=first_arm_start)
    boundary_opportunities = (opportunity(boundary_population),)
    with pytest.raises(ValueError, match="manifest must be frozen"):
        validate(boundary_population, boundary_opportunities, captures, evidence)

    boundary_opportunity = opportunity(source_population, recorded_at=first_arm_start)
    with pytest.raises(ValueError, match="preregistered before any benchmark arm starts"):
        validate(source_population, (boundary_opportunity,), captures, evidence)


def test_manifest_must_be_frozen_before_any_arm_starts() -> None:
    source_population, opportunities, captures, evidence = valid_boundary()
    too_early = replace(evidence[0], started_at=HORIZON)

    with pytest.raises(ValueError, match="manifest must be frozen"):
        validate(source_population, opportunities, captures, (too_early, *evidence[1:]))


def test_boundary_requires_exactly_one_capture_and_proof_for_each_frozen_arm() -> None:
    source_population, opportunities, captures, evidence = valid_boundary()

    with pytest.raises(ValueError, match="exactly the four frozen benchmark arms"):
        validate(source_population, opportunities, captures[:-1], evidence)
    with pytest.raises(ValueError, match="exactly the four frozen benchmark arms"):
        validate(source_population, opportunities, captures, evidence[:-1])
    with pytest.raises(ValueError, match="duplicate benchmark arm"):
        validate(source_population, opportunities, (*captures, captures[0]), evidence)


def test_capture_must_bind_frozen_budget_scope_window_and_protocol() -> None:
    source_population, opportunities, captures, evidence = valid_boundary()
    first = captures[0]

    invalid = (
        replace(first, alert_budget=4),
        replace(first, domain_scope=("SOFTWARE_PACKAGES",)),
        replace(first, selection_window_start=HORIZON - timedelta(hours=23)),
        replace(first, protocol_digest=digest("f")),
    )
    messages = ("K=5", "GLOBAL", "24-hour", "protocol digest")

    for changed, message in zip(invalid, messages, strict=True):
        with pytest.raises(ValueError, match=message):
            validate(source_population, opportunities, (changed, *captures[1:]), evidence)


def test_capture_must_use_population_horizon_and_finish_by_deadline() -> None:
    source_population, opportunities, captures, evidence = valid_boundary()
    first = captures[0]

    changed_horizon = HORIZON + timedelta(minutes=1)
    wrong_horizon = replace(
        first,
        captured_at=changed_horizon + timedelta(seconds=10),
        knowledge_horizon=changed_horizon,
        selection_window_start=changed_horizon - timedelta(hours=24),
        selection_window_end=changed_horizon,
    )
    with pytest.raises(ValueError, match="knowledge horizon"):
        validate(source_population, opportunities, (wrong_horizon, *captures[1:]), evidence)

    late_capture = replace(first, captured_at=HORIZON + timedelta(minutes=30, seconds=1))
    with pytest.raises(ValueError, match="capture deadline"):
        validate(source_population, opportunities, (late_capture, *captures[1:]), evidence)


def test_arm_cannot_start_before_manifest_or_after_deadline() -> None:
    source_population, opportunities, captures, evidence = valid_boundary()

    before_manifest = replace(evidence[0], started_at=HORIZON - timedelta(seconds=1))
    with pytest.raises(ValueError, match="manifest must be frozen"):
        validate(
            source_population,
            opportunities,
            captures,
            (before_manifest, *evidence[1:]),
        )

    after = replace(evidence[0], started_at=HORIZON + timedelta(minutes=30, seconds=1))
    with pytest.raises(ValueError, match="arm start exceeds"):
        validate(source_population, opportunities, captures, (after, *evidence[1:]))


@pytest.mark.parametrize(
    "arm",
    (
        ObservatoryArm.FRONTIER_EXISTING_EXPERIMENTAL,
        ObservatoryArm.ORDINARY_AGGREGATION,
        ObservatoryArm.WEB_LLM_BENCHMARK,
    ),
)
def test_complete_comparator_requires_exact_horizon_safe_source_state(
    arm: ObservatoryArm,
) -> None:
    source_population, opportunities, captures, evidence = valid_boundary()
    index = BENCHMARK_CAPTURE_V0_REQUIRED_ARMS.index(arm)

    stale = replace(
        evidence[index],
        source_state_horizon=HORIZON - timedelta(seconds=1),
    )
    with pytest.raises(ValueError, match="exact knowledge horizon"):
        validate(
            source_population,
            opportunities,
            captures,
            (*evidence[:index], stale, *evidence[index + 1 :]),
        )

    unsafe = replace(evidence[index], horizon_enforced=False)
    with pytest.raises(ValueError, match="enforced point-in-time"):
        validate(
            source_population,
            opportunities,
            captures,
            (*evidence[:index], unsafe, *evidence[index + 1 :]),
        )


def test_horizon_unsafe_arm_is_valid_only_when_persisted_as_failed() -> None:
    source_population, opportunities, captures, evidence = valid_boundary()
    index = BENCHMARK_CAPTURE_V0_REQUIRED_ARMS.index(ObservatoryArm.FRONTIER_EXISTING_EXPERIMENTAL)
    failed = capture(
        ObservatoryArm.FRONTIER_EXISTING_EXPERIMENTAL,
        status=CaptureStatus.FAILED,
    )
    unavailable = arm_evidence(
        ObservatoryArm.FRONTIER_EXISTING_EXPERIMENTAL,
        horizon_enforced=False,
        source_state_horizon=None,
    )

    result = validate(
        source_population,
        opportunities,
        (*captures[:index], failed, *captures[index + 1 :]),
        (*evidence[:index], unavailable, *evidence[index + 1 :]),
    )

    assert result.failed_arms == (ObservatoryArm.FRONTIER_EXISTING_EXPERIMENTAL,)
    assert ObservatoryArm.FRONTIER_EXISTING_EXPERIMENTAL not in result.complete_arms
