"""Unit tests for the WP3 prospective opportunity/outcome engine.

Coverage: deterministic anchor derivation from observation identity,
membership history for both arms, first-detection window state, transition
legality through the WP1 state machine (no post-terminal mutation), no
silent deletion, UNKNOWN/UNRESOLVED_COVERAGE for missing evidence, the
fail-closed blinding guard at the service layer, and idempotent
reprocessing.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import cast

import pytest

from frontier.application.opportunity_outcome import (
    MEMBERSHIP_ARMS,
    OPPORTUNITY_MEMBERSHIP_SCHEMA_VERSION,
    MembershipArm,
    OpportunityMembershipRecord,
    OpportunityOutcomeService,
    OpportunityWindowBinding,
    ProspectObservation,
    derive_anchor,
    detect_anchors,
    fold_window_state,
    window_binding_for,
)
from frontier.domain.opportunity import (
    BLINDING_GUARD_MESSAGE,
    BlindingState,
    DomainStratum,
    OpportunityAnchor,
    OpportunityState,
    OpportunityTransition,
    OutcomeLabel,
    OutcomeResolution,
    fold_transitions,
)

OBSERVED_AT = datetime(2026, 9, 5, 12, 0, tzinfo=UTC)
AS_OF = OBSERVED_AT + timedelta(seconds=300)
RESOLUTION_AT = OBSERVED_AT + timedelta(seconds=86400)
EXPERIMENT_ID = "advanced-ranking-pef-v0"


class InMemoryOpportunityRepository:
    """Append-only in-memory stand-in for the persistence port (tests only).

    Mirrors the durable contract: digest-identical replays are no-ops,
    digest-different conflicts at the same identity raise, and there is no
    deletion or mutation surface at all.
    """

    def __init__(self) -> None:
        self.anchors: dict[str, dict[str, object]] = {}
        self.transitions: dict[str, list[OpportunityTransition]] = {}
        self.resolutions: dict[str, tuple[str, OutcomeResolution]] = {}
        self.memberships: dict[
            str, dict[tuple[str, str, datetime, str], OpportunityMembershipRecord]
        ] = {}

    def record_anchor(self, anchor: OpportunityAnchor) -> None:
        existing = self.anchors.get(anchor.anchor_id)
        if existing is None:
            self.anchors[anchor.anchor_id] = cast("dict[str, object]", anchor.to_canonical())
            return
        if existing != anchor.to_canonical():
            raise RuntimeError("opportunity anchor identity conflict with different digest")

    def record_transition(self, transition: OpportunityTransition) -> None:
        log = self.transitions.setdefault(transition.anchor_id, [])
        if any(item.transition_id == transition.transition_id for item in log):
            return
        log.append(transition)

    def record_resolution(self, anchor_id: str, resolution: OutcomeResolution) -> None:
        existing = self.resolutions.get(anchor_id)
        if existing is None:
            self.resolutions[anchor_id] = (
                "sha256:" + resolution.resolution_digest_hex,
                resolution,
            )
            return
        if existing[0] != "sha256:" + resolution.resolution_digest_hex:
            raise RuntimeError("outcome resolution conflict with different digest")

    def list_transitions(self, anchor_id: str) -> tuple[OpportunityTransition, ...]:
        return tuple(self.transitions.get(anchor_id, ()))

    def record_membership(self, membership: OpportunityMembershipRecord) -> None:
        key = (
            membership.anchor_id,
            membership.experiment_id,
            membership.as_of,
            membership.arm.value,
        )
        per_anchor = self.memberships.setdefault(membership.anchor_id, {})
        existing = per_anchor.get(key)
        if existing is None:
            per_anchor[key] = membership
            return
        if existing.membership_id != membership.membership_id:
            raise RuntimeError("opportunity membership conflict with different digest")

    def list_memberships(self, anchor_id: str) -> tuple[OpportunityMembershipRecord, ...]:
        return tuple(
            sorted(self.memberships.get(anchor_id, {}).values(), key=lambda item: item.as_of)
        )

    def get_anchor_json(self, anchor_id: str) -> dict[str, object] | None:
        return self.anchors.get(anchor_id)

    def count_of_transitions(self, anchor_id: str) -> int:
        return len(self.list_transitions(anchor_id))


def _prospect(
    *,
    observation_id: str = "obs_" + "a" * 64,
    source_id: str = "pypi.updates",
    role: str = "PRIMARY_EMISSION",
    observed_at: datetime = OBSERVED_AT,
    first_reason: str = "SCHEDULED",
    recovered_after_gap: bool = False,
    episode_id: str | None = "ep_1",
) -> ProspectObservation:
    return ProspectObservation(
        observation_id=observation_id,
        source_id=source_id,
        role=role,
        observed_at=observed_at,
        first_reason=first_reason,
        recovered_after_gap=recovered_after_gap,
        episode_id=episode_id,
    )


def _service() -> tuple[OpportunityOutcomeService, InMemoryOpportunityRepository]:
    repository = InMemoryOpportunityRepository()
    return OpportunityOutcomeService(repository), repository


def _registered_anchor() -> tuple[
    OpportunityOutcomeService, InMemoryOpportunityRepository, OpportunityAnchor
]:
    service, repository = _service()
    anchor = derive_anchor(_prospect())
    service.register_anchor(anchor)
    return service, repository, anchor


def _membership(
    anchor: OpportunityAnchor,
    *,
    arm: MembershipArm,
    as_of: datetime,
    present: bool = True,
    rank: int | None = None,
    experiment_id: str = EXPERIMENT_ID,
) -> OpportunityMembershipRecord:
    return OpportunityMembershipRecord(
        anchor_id=anchor.anchor_id,
        experiment_id=experiment_id,
        as_of=as_of,
        arm=arm,
        present=present,
        episode_id="ep_1" if present else None,
        rank_position=rank if present else None,
    )


# ---------------------------------------------------------------------------
# Prospect observation eligibility (preregistration activity eligibility)
# ---------------------------------------------------------------------------


def test_prospect_observation_is_prospective_for_eligible_reasons() -> None:
    for reason in ("ACTIVE_ENRICHMENT", "DISCOVERY", "SCHEDULED"):
        assert _prospect(first_reason=reason).is_prospective


def test_prospect_observation_backfill_is_never_prospective() -> None:
    assert not _prospect(first_reason="BACKFILL").is_prospective


def test_prospect_observation_recovered_after_gap_is_never_prospective() -> None:
    assert not _prospect(first_reason="SCHEDULED", recovered_after_gap=True).is_prospective


def test_prospect_observation_requires_canonical_observation_id() -> None:
    with pytest.raises(ValueError, match="canonical observation id"):
        _prospect(observation_id="raw-1")


def test_prospect_observation_requires_timezone_aware_observed_at() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        _prospect(observed_at=OBSERVED_AT.replace(tzinfo=None))


# ---------------------------------------------------------------------------
# Deterministic anchor derivation (same observation -> same anchor)
# ---------------------------------------------------------------------------


def test_anchor_derivation_is_deterministic_from_observation_identity() -> None:
    first = derive_anchor(_prospect())
    second = derive_anchor(_prospect())
    assert first == second
    assert first.anchor_id == second.anchor_id
    assert first.anchor_id.startswith("opanchor_")


def test_anchor_derivation_is_independent_of_ranks_and_arms() -> None:
    # Anchor identity must never incorporate candidate ranks: only the
    # observation identity facts participate in the derivation.
    anchor = derive_anchor(_prospect())
    assert anchor.anchor_id == derive_anchor(_prospect()).anchor_id
    assert anchor.domain_stratum is DomainStratum.SOFTWARE_PACKAGES
    assert anchor.resolution_at == OBSERVED_AT + timedelta(seconds=86400)


def test_anchor_derivation_maps_frozen_v0_strata() -> None:
    assert derive_anchor(_prospect(source_id="pypi.updates")).domain_stratum is (
        DomainStratum.SOFTWARE_PACKAGES
    )
    assert derive_anchor(_prospect(source_id="hf.models")).domain_stratum is DomainStratum.AI_MODELS
    assert (
        derive_anchor(_prospect(source_id="cisa.kev")).domain_stratum
        is DomainStratum.SECURITY_VULNERABILITIES
    )


def test_anchor_derivation_rejects_non_anchor_source() -> None:
    with pytest.raises(ValueError, match="not a frozen V0 anchor source"):
        derive_anchor(_prospect(source_id="hn.frontpage"))


def test_anchor_derivation_rejects_non_primary_emission_role() -> None:
    with pytest.raises(ValueError, match="PRIMARY_EMISSION"):
        derive_anchor(_prospect(role="ATTENTION"))


def test_anchor_derivation_rejects_backfill_observation() -> None:
    with pytest.raises(ValueError, match="prospectively eligible"):
        derive_anchor(_prospect(first_reason="BACKFILL"))


def test_detect_anchors_enforces_pit_horizon_and_window() -> None:
    inside = _prospect(observation_id="obs_" + "b" * 64)
    after_horizon = _prospect(
        observation_id="obs_" + "c" * 64, observed_at=AS_OF + timedelta(seconds=1)
    )
    before_window = _prospect(
        observation_id="obs_" + "d" * 64, observed_at=OBSERVED_AT - timedelta(seconds=1)
    )
    anchors = detect_anchors(
        [inside, after_horizon, before_window], as_of=AS_OF, window_start=OBSERVED_AT
    )
    assert tuple(item.observation_id for item in anchors) == (inside.observation_id,)


def test_detect_anchors_deduplicates_the_same_observation_identity() -> None:
    anchors = detect_anchors([_prospect(), _prospect()], as_of=AS_OF, window_start=OBSERVED_AT)
    assert len(anchors) == 1


def test_detect_anchors_ignores_backfill_and_non_anchor_sources() -> None:
    anchors = detect_anchors(
        [
            _prospect(first_reason="BACKFILL"),
            _prospect(observation_id="obs_" + "e" * 64, source_id="hn.frontpage"),
        ],
        as_of=AS_OF,
        window_start=OBSERVED_AT,
    )
    assert anchors == ()


def test_detect_anchors_orders_deterministically() -> None:
    later = _prospect(
        observation_id="obs_" + "f" * 64, observed_at=OBSERVED_AT + timedelta(seconds=1)
    )
    anchors = detect_anchors([later, _prospect()], as_of=AS_OF, window_start=OBSERVED_AT)
    assert tuple(item.observation_id for item in anchors) == (
        "obs_" + "a" * 64,
        "obs_" + "f" * 64,
    )


def test_detect_anchors_requires_timezone_aware_boundaries() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        detect_anchors([], as_of=AS_OF.replace(tzinfo=None), window_start=OBSERVED_AT)
    with pytest.raises(ValueError, match="timezone-aware"):
        detect_anchors([], as_of=AS_OF, window_start=OBSERVED_AT.replace(tzinfo=None))


# ---------------------------------------------------------------------------
# Anchor registration (idempotent genesis)
# ---------------------------------------------------------------------------


def test_register_anchor_records_pending_genesis_once() -> None:
    service, repository, anchor = _registered_anchor()
    assert service.project(anchor) is OpportunityState.PENDING
    assert len(repository.list_transitions(anchor.anchor_id)) == 1


def test_register_anchor_is_idempotent_for_the_same_observation() -> None:
    service, repository, anchor = _registered_anchor()
    genesis = service.register_anchor(anchor)
    assert repository.count_of_transitions(anchor.anchor_id) == 1
    assert genesis.from_state is None
    assert genesis.to_state is OpportunityState.PENDING


def test_register_anchor_rejects_stratum_source_mismatch() -> None:
    service, _ = _service()
    anchor = OpportunityAnchor(
        observation_id="obs_" + "a" * 64,
        source_id="pypi.updates",
        as_of=OBSERVED_AT,
        observed_at=OBSERVED_AT,
        domain_stratum=DomainStratum.AI_MODELS,
    )
    with pytest.raises(ValueError, match="does not match the frozen"):
        service.register_anchor(anchor)


def test_register_anchor_rejects_aggregate_strata() -> None:
    service, _ = _service()
    anchor = OpportunityAnchor(
        observation_id="obs_" + "a" * 64,
        source_id="pypi.updates",
        as_of=OBSERVED_AT,
        observed_at=OBSERVED_AT,
        domain_stratum=DomainStratum.UNQUALIFIED_MIXED,
    )
    with pytest.raises(ValueError, match="exactly one frozen V0 stratum"):
        service.register_anchor(anchor)


# ---------------------------------------------------------------------------
# Membership history (append-only evidence for both arms)
# ---------------------------------------------------------------------------


def test_membership_identity_is_content_derived_and_stable() -> None:
    _, _, anchor = _registered_anchor()
    first = _membership(anchor, arm=MembershipArm.CANDIDATE, as_of=AS_OF, rank=1)
    second = _membership(anchor, arm=MembershipArm.CANDIDATE, as_of=AS_OF, rank=1)
    assert first.membership_id == second.membership_id
    assert first.membership_id.startswith("opmember_")


def test_membership_identity_changes_with_content() -> None:
    _, _, anchor = _registered_anchor()
    candidate = _membership(anchor, arm=MembershipArm.CANDIDATE, as_of=AS_OF, rank=1)
    control = _membership(anchor, arm=MembershipArm.CONTROL, as_of=AS_OF, rank=1)
    assert candidate.membership_id != control.membership_id


def test_membership_absent_row_carries_no_episode_or_rank() -> None:
    _, _, anchor = _registered_anchor()
    record = _membership(anchor, arm=MembershipArm.CONTROL, as_of=AS_OF, present=False)
    assert record.episode_id is None
    assert record.rank_position is None
    with pytest.raises(ValueError, match="no episode or rank claim"):
        OpportunityMembershipRecord(
            anchor_id=anchor.anchor_id,
            experiment_id=EXPERIMENT_ID,
            as_of=AS_OF,
            arm=MembershipArm.CONTROL,
            present=False,
            episode_id="ep_1",
        )
    with pytest.raises(ValueError, match="requires the anchor's grouping episode"):
        OpportunityMembershipRecord(
            anchor_id=anchor.anchor_id,
            experiment_id=EXPERIMENT_ID,
            as_of=AS_OF,
            arm=MembershipArm.CONTROL,
            present=True,
        )


def test_record_membership_requires_registered_anchor() -> None:
    service, _ = _service()
    anchor = derive_anchor(_prospect())
    with pytest.raises(ValueError, match="registered anchor"):
        service.record_membership(
            _membership(anchor, arm=MembershipArm.CANDIDATE, as_of=AS_OF, rank=1)
        )


def test_record_membership_replays_are_noops_for_both_arms() -> None:
    service, repository, anchor = _registered_anchor()
    candidate = _membership(anchor, arm=MembershipArm.CANDIDATE, as_of=AS_OF, rank=1)
    control = _membership(anchor, arm=MembershipArm.CONTROL, as_of=RESOLUTION_AT, rank=7)
    for _ in range(3):
        service.record_membership(candidate)
        service.record_membership(control)
    stored = repository.list_memberships(anchor.anchor_id)
    assert len(stored) == 2
    assert {item.arm for item in stored} == {MembershipArm.CANDIDATE, MembershipArm.CONTROL}


def test_membership_conflict_at_same_identity_raises() -> None:
    service, _, anchor = _registered_anchor()
    service.record_membership(_membership(anchor, arm=MembershipArm.CANDIDATE, as_of=AS_OF, rank=1))
    with pytest.raises(RuntimeError, match="conflict with different digest"):
        service.record_membership(
            _membership(anchor, arm=MembershipArm.CANDIDATE, as_of=AS_OF, rank=2)
        )


def test_membership_schema_version_is_enforced() -> None:
    _, _, anchor = _registered_anchor()
    membership = _membership(anchor, arm=MembershipArm.CANDIDATE, as_of=AS_OF, rank=1)
    tampered = OpportunityMembershipRecord(
        anchor_id=membership.anchor_id,
        experiment_id=membership.experiment_id,
        as_of=membership.as_of,
        arm=membership.arm,
        present=membership.present,
        episode_id=membership.episode_id,
        rank_position=membership.rank_position,
        schema_version="wrong-version",
    )
    assert tampered.schema_version != OPPORTUNITY_MEMBERSHIP_SCHEMA_VERSION


# ---------------------------------------------------------------------------
# Window state: first eligible detection per arm + window identity binding
# ---------------------------------------------------------------------------


def test_window_state_first_detection_is_minimum_as_of_per_arm() -> None:
    service, _, anchor = _registered_anchor()
    later = AS_OF + timedelta(seconds=600)
    service.record_membership(_membership(anchor, arm=MembershipArm.CANDIDATE, as_of=later, rank=3))
    earlier = AS_OF
    service.record_membership(
        _membership(anchor, arm=MembershipArm.CANDIDATE, as_of=earlier, rank=1)
    )
    service.record_membership(_membership(anchor, arm=MembershipArm.CONTROL, as_of=later, rank=9))
    state = service.window_state(anchor)
    assert state.first_candidate_detection_at == earlier
    assert state.first_control_detection_at == later
    assert state.candidate_surfaced and state.control_surfaced


def test_window_state_ignores_ranks_above_cutoff() -> None:
    service, _, anchor = _registered_anchor()
    service.record_membership(
        _membership(anchor, arm=MembershipArm.CANDIDATE, as_of=AS_OF, rank=101)
    )
    state = service.window_state(anchor, rank_cutoff_k=100)
    assert state.first_candidate_detection_at is None
    assert not state.candidate_surfaced


def test_window_state_ignores_absent_evidence_rows() -> None:
    service, _, anchor = _registered_anchor()
    service.record_membership(
        _membership(anchor, arm=MembershipArm.CONTROL, as_of=AS_OF, present=False)
    )
    state = service.window_state(anchor)
    assert state.first_control_detection_at is None
    assert not state.control_surfaced


def test_window_state_ignores_memberships_outside_the_window() -> None:
    service, _, anchor = _registered_anchor()
    service.record_membership(
        _membership(
            anchor,
            arm=MembershipArm.CANDIDATE,
            as_of=RESOLUTION_AT + timedelta(seconds=1),
            rank=1,
        )
    )
    state = service.window_state(anchor)
    assert state.first_candidate_detection_at is None


def test_window_state_miss_is_none_for_never_detected_arms() -> None:
    service, _, anchor = _registered_anchor()
    state = service.window_state(anchor)
    assert state.first_candidate_detection_at is None
    assert state.first_control_detection_at is None


def test_window_identity_binding_is_stable_and_content_derived() -> None:
    anchor = derive_anchor(_prospect())
    first = window_binding_for(anchor)
    second = window_binding_for(anchor)
    assert first == second
    assert first.window_id == second.window_id
    assert first.window_id.startswith("opwindow_")
    assert first.window_start == anchor.observed_at
    assert first.window_end == anchor.resolution_at
    with pytest.raises(ValueError, match="positive integer"):
        OpportunityWindowBinding(
            anchor_id=anchor.anchor_id,
            window_start=anchor.observed_at,
            window_end=anchor.resolution_at,
            rank_cutoff_k=0,
        )


def test_window_state_catches_foreign_membership_history() -> None:
    anchor = derive_anchor(_prospect())
    foreign = derive_anchor(_prospect(observation_id="obs_" + "b" * 64))
    with pytest.raises(ValueError, match="foreign anchor"):
        fold_window_state(
            anchor, [_membership(foreign, arm=MembershipArm.CANDIDATE, as_of=AS_OF, rank=1)]
        )


# ---------------------------------------------------------------------------
# Outcome advancement: WP1 state machine only
# ---------------------------------------------------------------------------


def _blinded_resolution(label: OutcomeLabel, *, decided_at: datetime) -> OutcomeResolution:
    return OutcomeResolution(
        resolution_state=OpportunityState.RESOLVED,
        label=label,
        blinding_state=BlindingState.BLINDED,
        decided_at=decided_at,
        evidence_digest="sha256:" + "c" * 64,
    )


def test_blinding_guard_rejects_open_adjudication_at_service_layer() -> None:
    service, repository, anchor = _registered_anchor()
    # The domain dataclass refuses to CONSTRUCT an unblinded RESOLVED
    # resolution, so simulate an adjudication that was blinded at validation
    # time and then opened: the SERVICE layer must independently refuse to
    # persist it (defense in depth).
    resolution = OutcomeResolution(
        resolution_state=OpportunityState.RESOLVED,
        label=OutcomeLabel.POSITIVE,
        blinding_state=BlindingState.BLINDED,
        decided_at=RESOLUTION_AT,
        evidence_digest="sha256:" + "c" * 64,
    )
    object.__setattr__(resolution, "blinding_state", BlindingState.OPEN)
    assert resolution.blinding_state is BlindingState.OPEN
    with pytest.raises(ValueError) as caught:
        service.resolve(anchor, resolution, reason="tampered adjudication")
    assert BLINDING_GUARD_MESSAGE in str(caught.value)
    # Nothing was adjudicated: the log keeps only the genesis event and there
    # is no resolution row.
    assert repository.count_of_transitions(anchor.anchor_id) == 1
    assert repository.resolutions == {}
    assert repository.get_anchor_json(anchor.anchor_id) is not None


def test_resolve_records_transition_and_resolution() -> None:
    service, repository, anchor = _registered_anchor()
    resolution = _blinded_resolution(OutcomeLabel.POSITIVE, decided_at=RESOLUTION_AT)
    transition = service.resolve(
        anchor, resolution, reason="blinded automated adjudication resolved POSITIVE"
    )
    assert transition is not None
    assert transition.from_state is OpportunityState.PENDING
    assert transition.to_state is OpportunityState.RESOLVED
    assert service.project(anchor) is OpportunityState.RESOLVED
    assert repository.resolutions[anchor.anchor_id][1].label is OutcomeLabel.POSITIVE


def test_resolve_is_idempotent_for_identical_resolution_replays() -> None:
    service, repository, anchor = _registered_anchor()
    resolution = _blinded_resolution(OutcomeLabel.POSITIVE, decided_at=RESOLUTION_AT)
    service.resolve(anchor, resolution, reason="blinded automated adjudication")
    again = service.resolve(anchor, resolution, reason="blinded automated adjudication")
    assert again is None
    assert repository.count_of_transitions(anchor.anchor_id) == 2  # genesis + resolution
    assert service.project(anchor) is OpportunityState.RESOLVED


def test_resolve_conflicting_resolution_digest_raises() -> None:
    service, _, anchor = _registered_anchor()
    service.resolve(
        anchor,
        _blinded_resolution(OutcomeLabel.POSITIVE, decided_at=RESOLUTION_AT),
        reason="blinded automated adjudication",
    )
    conflicting = OutcomeResolution(
        resolution_state=OpportunityState.RESOLVED,
        label=OutcomeLabel.POSITIVE,
        blinding_state=BlindingState.BLINDED,
        decided_at=RESOLUTION_AT,
        evidence_digest="sha256:" + "d" * 64,
    )
    with pytest.raises(RuntimeError, match="conflict with different digest"):
        service.resolve(anchor, conflicting, reason="blinded automated adjudication")


def test_post_terminal_mutation_is_rejected() -> None:
    service, repository, anchor = _registered_anchor()
    service.resolve(
        anchor,
        _blinded_resolution(OutcomeLabel.POSITIVE, decided_at=RESOLUTION_AT),
        reason="blinded automated adjudication",
    )
    before = repository.list_transitions(anchor.anchor_id)
    # Cross-state post-terminal mutation is rejected by the state machine.
    with pytest.raises(ValueError, match="terminal"):
        service.resolve(
            anchor,
            OutcomeResolution(
                resolution_state=OpportunityState.UNKNOWN,
                label=OutcomeLabel.UNRESOLVED_COVERAGE,
                blinding_state=BlindingState.OPEN,
                decided_at=RESOLUTION_AT,
                evidence_digest="sha256:" + "e" * 64,
            ),
            reason="post-terminal mutation",
        )
    # A same-state re-adjudication with a DIFFERENT digest is a content
    # conflict, never a silent rewrite.
    with pytest.raises(RuntimeError, match="conflict with different digest"):
        service.resolve(
            anchor,
            OutcomeResolution(
                resolution_state=OpportunityState.RESOLVED,
                label=OutcomeLabel.NEGATIVE,
                blinding_state=BlindingState.BLINDED,
                decided_at=RESOLUTION_AT,
                evidence_digest="sha256:" + "d" * 64,
            ),
            reason="rewritten adjudication",
        )
    assert repository.list_transitions(anchor.anchor_id) == before
    assert len(repository.resolutions) == 1


def test_unknown_coverage_stays_unknown() -> None:
    service, _, anchor = _registered_anchor()
    service.record_unknown_coverage(
        anchor,
        decided_at=RESOLUTION_AT,
        evidence_digest="sha256:" + "e" * 64,
        lane_health_digest="sha256:" + "f" * 64,
    )
    assert service.project(anchor) is OpportunityState.UNKNOWN
    # UNKNOWN is terminal and stays UNKNOWN: no label coercion afterwards.
    with pytest.raises(ValueError, match="terminal"):
        service.resolve(
            anchor,
            _blinded_resolution(OutcomeLabel.NEGATIVE, decided_at=RESOLUTION_AT),
            reason="late coercion attempt",
        )


def test_unknown_coverage_requires_evidence_digest() -> None:
    service, _, anchor = _registered_anchor()
    with pytest.raises(ValueError, match="evidence digest"):
        service.record_unknown_coverage(
            anchor,
            decided_at=RESOLUTION_AT,
            evidence_digest=None,  # type: ignore[arg-type]
        )


def test_resolve_rejects_pending_resolution_and_unregistered_anchor() -> None:
    service, _, anchor = _registered_anchor()
    pending = OutcomeResolution(
        resolution_state=OpportunityState.PENDING,
        label=None,
        blinding_state=None,
        decided_at=None,
    )
    with pytest.raises(ValueError, match="no adjudication claim"):
        service.resolve(anchor, pending, reason="not an adjudication")

    unregistered = derive_anchor(_prospect(observation_id="obs_" + "b" * 64))
    with pytest.raises(ValueError, match="unregistered"):
        service.resolve(
            unregistered,
            _blinded_resolution(OutcomeLabel.POSITIVE, decided_at=RESOLUTION_AT),
            reason="blinded automated adjudication",
        )


def test_excluded_resolution_carries_no_label() -> None:
    service, repository, anchor = _registered_anchor()
    service.resolve_excluded(anchor, decided_at=RESOLUTION_AT, reason="duplicate anchor discarded")
    assert service.project(anchor) is OpportunityState.EXCLUDED
    stored = repository.resolutions[anchor.anchor_id][1]
    assert stored.label is None
    assert stored.resolution_state is OpportunityState.EXCLUDED


def test_project_raises_on_tampered_transition_log_no_silent_deletion() -> None:
    service, repository, anchor = _registered_anchor()
    # Simulate a deleted genesis event: the fold refuses to guess state.
    repository.transitions[anchor.anchor_id] = [
        transition
        for transition in repository.list_transitions(anchor.anchor_id)
        if transition.from_state is not None
    ]
    with pytest.raises(ValueError, match="no transition log to fold"):
        service.project(anchor)


def test_full_boundary_reprocessing_is_idempotent() -> None:
    # Re-processing the same observations/boundary yields identical ids, the
    # same single genesis event, the same membership facts, and the same
    # projection state.
    observations = [_prospect(), _prospect()]
    service, repository, anchor = _registered_anchor()
    assert detect_anchors(observations, as_of=AS_OF, window_start=OBSERVED_AT) == (anchor,)

    for _ in range(2):
        anchors = detect_anchors(observations, as_of=AS_OF, window_start=OBSERVED_AT)
        for detected in anchors:
            service.register_anchor(detected)
            service.record_membership(
                _membership(detected, arm=MembershipArm.CANDIDATE, as_of=AS_OF, rank=1)
            )
            service.record_membership(
                _membership(detected, arm=MembershipArm.CONTROL, as_of=AS_OF, present=False)
            )
    assert repository.count_of_transitions(anchor.anchor_id) == 1
    assert len(repository.list_memberships(anchor.anchor_id)) == 2
    assert service.project(anchor) is OpportunityState.PENDING
    state = service.window_state(anchor)
    assert state.first_candidate_detection_at == AS_OF
    assert state.first_control_detection_at is None


def test_membership_schema_constant_is_frozen_v0() -> None:
    assert OPPORTUNITY_MEMBERSHIP_SCHEMA_VERSION == "opportunity-membership-history-v0"
    assert set(MEMBERSHIP_ARMS) == {MembershipArm.CANDIDATE, MembershipArm.CONTROL}


def test_fold_matches_service_projection_after_transitions() -> None:
    service, repository, anchor = _registered_anchor()
    service.resolve(
        anchor,
        _blinded_resolution(OutcomeLabel.NEGATIVE, decided_at=RESOLUTION_AT),
        reason="blinded automated adjudication resolved NEGATIVE",
    )
    assert fold_transitions(repository.list_transitions(anchor.anchor_id)) is (
        OpportunityState.RESOLVED
    )
    assert service.project(anchor) is OpportunityState.RESOLVED
