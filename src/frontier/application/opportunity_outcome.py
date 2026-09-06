"""Application-layer prospective opportunity/outcome engine (WP3).

Wraps the WP1 domain primitives (:mod:`frontier.domain.opportunity`) with the
preregistered PEF_V0 opportunity rules
(``experiments/advanced_intelligence/pef_v0/preregistration.json``):

- ``opportunity.anchor``: prospectively eligible canonical PRIMARY_EMISSION
  observations from a frozen V0 anchor source inside the ranking window;
  stable anchor identity is the observation identity, anchors are NEVER
  derived from candidate ranks (no post-hoc eligibility);
- membership history: append-only evidence of whether an anchor appeared in
  the eligible universe of a run's CANDIDATE and/or CONTROL arm at a given
  ``as_of`` (never a mutable flag);
- window state: first eligible detection per arm (earliest ``as_of`` whose
  arm's episode rank is at or under the global K) with a digest-bound window
  identity binding;
- outcome advancement EXCLUSIVELY through the WP1 transition state machine
  (``ALLOWED_TRANSITIONS``): terminal states have no outgoing transitions,
  there is no silent deletion, and UNKNOWN stays UNKNOWN as
  ``UNRESOLVED_COVERAGE`` — degraded coverage is never coerced into a label;
- fail-closed blinding discipline enforced at the service layer as well: a
  RESOLVED adjudication requires an explicit BLINDED blinding state;
- idempotency: identical content always yields identical content-derived
  identities; digest-identical replays are no-ops and digest-different
  conflicts are errors.

This service is independently callable: the WP2 orchestrator does not call it
(WP4/evaluation consume its durable state later).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from frontier.domain.canonical_json import (
    CanonicalValue,
    canonical_json_bytes,
    canonical_timestamp,
)
from frontier.domain.digests import sha256_hex
from frontier.domain.evaluation import ANCHOR_SOURCE_BY_DOMAIN, GLOBAL_RANK_CUTOFF_K
from frontier.domain.opportunity import (
    BLINDING_GUARD_MESSAGE,
    BlindingState,
    DomainStratum,
    OpportunityAnchor,
    OpportunityState,
    OpportunityTransition,
    OutcomeLabel,
    OutcomeResolution,
    advance,
    fold_transitions,
    genesis_transition,
)

PROSPECT_OBSERVATION_SCHEMA_VERSION = "prospect-observation-v0"
OPPORTUNITY_MEMBERSHIP_SCHEMA_VERSION = "opportunity-membership-history-v0"
OPPORTUNITY_MEMBERSHIP_ID_PREFIX = "opmember_"
OPPORTUNITY_WINDOW_SCHEMA_VERSION = "opportunity-window-binding-v0"
OPPORTUNITY_WINDOW_ID_PREFIX = "opwindow_"

#: Frozen V0 preregistration ranking window (snapshot_schedule).
RANKING_WINDOW_SECONDS = 2419200

#: Preregistration "opportunity.anchor": prospectively eligible canonical
#: PRIMARY_EMISSION observation from one frozen V0 anchor source.
PEF_PRIMARY_EMISSION_ROLE = "PRIMARY_EMISSION"

#: Frozen V0 activity eligibility (preregistration candidate.configuration):
#: only these first collection reasons are prospective; BACKFILL and
#: recovered-after-gap evidence is never live prospective activity.
PROSPECT_ELIGIBLE_REASONS: tuple[str, ...] = (
    "ACTIVE_ENRICHMENT",
    "DISCOVERY",
    "SCHEDULED",
)

#: Frozen V0 anchor-source → stratum mapping (preregistration domain_mapping;
#: the taxonomy is frozen — this service adds no domains).
STRATUM_BY_ANCHOR_SOURCE: dict[str, DomainStratum] = {
    "pypi.updates": DomainStratum.SOFTWARE_PACKAGES,
    "hf.models": DomainStratum.AI_MODELS,
    "cisa.kev": DomainStratum.SECURITY_VULNERABILITIES,
}
assert set(STRATUM_BY_ANCHOR_SOURCE) == set(ANCHOR_SOURCE_BY_DOMAIN.values())


class MembershipArm(StrEnum):
    """Paired-run arm vocabulary for membership history (never an arm output)."""

    CANDIDATE = "CANDIDATE"
    CONTROL = "CONTROL"


@dataclass(frozen=True, slots=True)
class ProspectObservation:
    """Canonical observation fact offered to anchor derivation (PIT-clean).

    ``is_prospective`` mirrors the frozen preregistration activity eligibility
    exactly (eligible first collection reasons, no BACKFILL, no
    recovered-after-gap). Eligibility is a fact of the observation itself,
    never of any ranking outcome.
    """

    observation_id: str
    source_id: str
    role: str
    observed_at: datetime
    first_reason: str
    recovered_after_gap: bool
    episode_id: str | None = None
    schema_version: str = PROSPECT_OBSERVATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("prospect observation observed_at must be timezone-aware")
        if not self.observation_id.startswith("obs_"):
            raise ValueError("prospect observation requires a canonical observation id")
        if not self.source_id:
            raise ValueError("prospect observation requires a source id")
        if not self.role:
            raise ValueError("prospect observation requires a signal role")
        if self.episode_id is not None and not self.episode_id:
            raise ValueError("prospect observation episode id must be non-empty when present")

    @property
    def is_prospective(self) -> bool:
        """Preregistration activity eligibility (R3 backfill safety)."""
        return not self.recovered_after_gap and self.first_reason in PROSPECT_ELIGIBLE_REASONS

    def to_canonical(self) -> dict[str, CanonicalValue]:
        return {
            "episode_id": self.episode_id,
            "first_reason": self.first_reason,
            "observation_id": self.observation_id,
            "observed_at": canonical_timestamp(self.observed_at),
            "recovered_after_gap": self.recovered_after_gap,
            "role": self.role,
            "schema_version": self.schema_version,
            "source_id": self.source_id,
        }


def derive_anchor(observation: ProspectObservation) -> OpportunityAnchor:
    """Deterministically derive one preregistered anchor from observation identity.

    The anchor is a pure function of the observation identity and its
    preregistration facts (source, observed_at, eligibility): the same
    observation always yields the same content-derived ``anchor_id``. Ranks,
    arms, and any later outcome are structurally absent from the derivation,
    so there can be no post-hoc eligibility. ``as_of`` is pinned to
    ``observed_at`` so re-observation at later boundaries cannot fork anchor
    identity.
    """
    stratum = STRATUM_BY_ANCHOR_SOURCE.get(observation.source_id)
    if stratum is None:
        raise ValueError(
            f"observation source {observation.source_id!r} is not a frozen V0 anchor source"
        )
    if observation.role != PEF_PRIMARY_EMISSION_ROLE:
        raise ValueError("anchor derivation requires a PRIMARY_EMISSION observation")
    if not observation.is_prospective:
        raise ValueError("anchor derivation requires a prospectively eligible observation")
    return OpportunityAnchor(
        observation_id=observation.observation_id,
        source_id=observation.source_id,
        as_of=observation.observed_at,
        observed_at=observation.observed_at,
        domain_stratum=stratum,
    )


def detect_anchors(
    observations: Iterable[ProspectObservation],
    *,
    as_of: datetime,
    window_start: datetime,
) -> tuple[OpportunityAnchor, ...]:
    """Detect preregistered opportunity anchors from canonical observations.

    Point-in-time clean: only observations with
    ``window_start <= observed_at <= as_of`` are visible. Duplicates of the
    same observation identity collapse to one anchor. Results are ordered
    deterministically by ``(observed_at, observation_id)``.
    """
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("detection as_of must be timezone-aware")
    if window_start.tzinfo is None or window_start.utcoffset() is None:
        raise ValueError("detection window_start must be timezone-aware")
    if window_start > as_of:
        raise ValueError("detection window start cannot be after the as_of boundary")
    derived: dict[str, OpportunityAnchor] = {}
    for observation in observations:
        if observation.observed_at > as_of or observation.observed_at < window_start:
            continue
        if not observation.is_prospective:
            continue
        if observation.role != PEF_PRIMARY_EMISSION_ROLE:
            continue
        if observation.source_id not in STRATUM_BY_ANCHOR_SOURCE:
            continue
        anchor = derive_anchor(observation)
        derived.setdefault(anchor.observation_id, anchor)
    return tuple(sorted(derived.values(), key=lambda item: (item.observed_at, item.observation_id)))


@dataclass(frozen=True, slots=True)
class OpportunityMembershipRecord:
    """One append-only membership-history fact (evidence, never a flag).

    Records whether an anchor appeared in the eligible universe of one run's
    CANDIDATE or CONTROL arm at one paired boundary ``as_of``. ``present``
    rows carry the anchor's current grouping episode id and, when the arm
    ranked that episode, its 1-based global rank position. ``present=False``
    rows are the explicit negative evidence of absence at that boundary.
    Content-derived identity: identical facts always yield one
    ``membership_id``; any content change is a different (conflicting) fact.
    """

    anchor_id: str
    experiment_id: str
    as_of: datetime
    arm: MembershipArm
    present: bool
    episode_id: str | None = None
    rank_position: int | None = None
    schema_version: str = OPPORTUNITY_MEMBERSHIP_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.as_of.tzinfo is None or self.as_of.utcoffset() is None:
            raise ValueError("membership as_of must be timezone-aware")
        if not self.anchor_id.startswith("opanchor_"):
            raise ValueError("membership requires a canonical opportunity anchor id")
        if not self.experiment_id:
            raise ValueError("membership experiment id must be non-empty")
        if self.rank_position is not None and self.rank_position < 1:
            raise ValueError("membership rank position must be a positive integer when present")
        if self.episode_id is not None and not self.episode_id:
            raise ValueError("membership episode id must be non-empty when present")
        if not self.present:
            if self.episode_id is not None or self.rank_position is not None:
                raise ValueError("absent membership carries no episode or rank claim")
        elif self.episode_id is None:
            raise ValueError("present membership requires the anchor's grouping episode id")

    def to_canonical(self) -> dict[str, CanonicalValue]:
        return {
            "anchor_id": self.anchor_id,
            "arm": self.arm.value,
            "as_of": canonical_timestamp(self.as_of),
            "episode_id": self.episode_id,
            "experiment_id": self.experiment_id,
            "present": self.present,
            "rank_position": self.rank_position,
            "schema_version": self.schema_version,
        }

    @property
    def membership_digest_hex(self) -> str:
        return sha256_hex(canonical_json_bytes(self.to_canonical()))

    @property
    def membership_id(self) -> str:
        return OPPORTUNITY_MEMBERSHIP_ID_PREFIX + self.membership_digest_hex


@dataclass(frozen=True, slots=True)
class OpportunityWindowBinding:
    """Digest-bound identity of one anchor's preregistered detection window.

    The detection window is ``[anchor.observed_at, anchor.resolution_at]``
    per the preregistration detection rules (earliest paired boundary at or
    before ``resolution_at``; boundaries at or before ``observed_at`` cannot
    detect the anchor). The binding is content-derived and depends only on
    the anchor identity, the window bounds, and the frozen global rank
    cutoff — never on any ranking payload.
    """

    anchor_id: str
    window_start: datetime
    window_end: datetime
    rank_cutoff_k: int
    schema_version: str = OPPORTUNITY_WINDOW_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.window_start.tzinfo is None or self.window_start.utcoffset() is None:
            raise ValueError("window binding start must be timezone-aware")
        if self.window_end.tzinfo is None or self.window_end.utcoffset() is None:
            raise ValueError("window binding end must be timezone-aware")
        if self.window_end <= self.window_start:
            raise ValueError("window binding end must be after its start")
        if self.rank_cutoff_k < 1:
            raise ValueError("window binding rank cutoff must be a positive integer")

    def to_canonical(self) -> dict[str, CanonicalValue]:
        return {
            "anchor_id": self.anchor_id,
            "rank_cutoff_k": self.rank_cutoff_k,
            "schema_version": self.schema_version,
            "window_end": canonical_timestamp(self.window_end),
            "window_start": canonical_timestamp(self.window_start),
        }

    @property
    def window_id(self) -> str:
        return OPPORTUNITY_WINDOW_ID_PREFIX + sha256_hex(canonical_json_bytes(self.to_canonical()))


def window_binding_for(
    anchor: OpportunityAnchor, *, rank_cutoff_k: int = GLOBAL_RANK_CUTOFF_K
) -> OpportunityWindowBinding:
    """Bind the anchor's preregistered detection window identity."""
    return OpportunityWindowBinding(
        anchor_id=anchor.anchor_id,
        window_start=anchor.observed_at,
        window_end=anchor.resolution_at,
        rank_cutoff_k=rank_cutoff_k,
    )


@dataclass(frozen=True, slots=True)
class OpportunityWindowState:
    """First eligible detection per arm over an anchor's window (misses kept).

    ``first_candidate_detection_at`` / ``first_control_detection_at`` are the
    earliest membership ``as_of`` inside the bound window where the anchor was
    present in that arm's eligible universe AND the arm ranked the anchor's
    current episode at or under the global rank cutoff. ``None`` means the
    arm never detected the anchor in the window (preregistration
    ``never_detected_time`` assigns such misses ``resolution_at`` at
    evaluation time; the raw window state keeps ``None``).
    """

    binding: OpportunityWindowBinding
    first_candidate_detection_at: datetime | None
    first_control_detection_at: datetime | None
    candidate_surfaced: bool
    control_surfaced: bool

    def to_canonical(self) -> dict[str, CanonicalValue]:
        return {
            "binding": self.binding.to_canonical(),
            "candidate_surfaced": self.candidate_surfaced,
            "control_surfaced": self.control_surfaced,
            "first_candidate_detection_at": None
            if self.first_candidate_detection_at is None
            else canonical_timestamp(self.first_candidate_detection_at),
            "first_control_detection_at": None
            if self.first_control_detection_at is None
            else canonical_timestamp(self.first_control_detection_at),
        }


def fold_window_state(
    anchor: OpportunityAnchor,
    memberships: Sequence[OpportunityMembershipRecord],
    *,
    rank_cutoff_k: int = GLOBAL_RANK_CUTOFF_K,
) -> OpportunityWindowState:
    """Fold append-only membership history into per-arm first-detection state.

    Membership rows outside the bound window and rows above the rank cutoff
    never count as detection; absent-evidence rows never count. The minimum
    qualifying ``as_of`` per arm is the first eligible detection timestamp.
    """
    binding = window_binding_for(anchor, rank_cutoff_k=rank_cutoff_k)
    first: dict[MembershipArm, datetime | None] = {
        MembershipArm.CANDIDATE: None,
        MembershipArm.CONTROL: None,
    }
    for membership in sorted(memberships, key=lambda item: (item.as_of, item.membership_id)):
        if membership.anchor_id != anchor.anchor_id:
            raise ValueError("membership history contains a foreign anchor")
        if not (binding.window_start <= membership.as_of <= binding.window_end):
            continue
        if not membership.present or membership.rank_position is None:
            continue
        if membership.rank_position > rank_cutoff_k:
            continue
        current = first[membership.arm]
        if current is None or membership.as_of < current:
            first[membership.arm] = membership.as_of
    return OpportunityWindowState(
        binding=binding,
        first_candidate_detection_at=first[MembershipArm.CANDIDATE],
        first_control_detection_at=first[MembershipArm.CONTROL],
        candidate_surfaced=first[MembershipArm.CANDIDATE] is not None,
        control_surfaced=first[MembershipArm.CONTROL] is not None,
    )


class OpportunityOutcomeRepository(Protocol):
    """Persistence port for the durable opportunity/outcome engine.

    All writes are append-only and idempotent: a digest-identical replay is a
    no-op; a digest-different conflict at the same identity is an error.
    """

    def record_anchor(self, anchor: OpportunityAnchor) -> None: ...
    def record_transition(self, transition: OpportunityTransition) -> None: ...
    def record_resolution(self, anchor_id: str, resolution: OutcomeResolution) -> None: ...
    def list_transitions(self, anchor_id: str) -> tuple[OpportunityTransition, ...]: ...
    def record_membership(self, membership: OpportunityMembershipRecord) -> None: ...
    def list_memberships(self, anchor_id: str) -> tuple[OpportunityMembershipRecord, ...]: ...
    def get_anchor_json(self, anchor_id: str) -> dict[str, object] | None: ...


class OpportunityOutcomeService:
    """Durable prospective opportunity and outcome state service (WP3).

    Anchors are detected prospectively from canonical observations; outcome
    state advances ONLY through the WP1 transition state machine. The service
    never deletes state, never mutates membership history, never coerces
    UNKNOWN coverage into a label, and enforces the fail-closed blinding
    guard itself before any resolution is persisted.
    """

    def __init__(self, repository: OpportunityOutcomeRepository) -> None:
        self._repository = repository

    # ------------------------------------------------------------------
    # Anchor detection and registration (prospective, never rank-derived)
    # ------------------------------------------------------------------

    def detect(
        self,
        observations: Sequence[ProspectObservation],
        *,
        as_of: datetime,
        window_start: datetime,
    ) -> tuple[OpportunityAnchor, ...]:
        return detect_anchors(observations, as_of=as_of, window_start=window_start)

    def register_anchor(self, anchor: OpportunityAnchor) -> OpportunityTransition:
        """Record an anchor and its deterministic PENDING genesis event.

        Idempotent: re-registering the same anchor replays the identical
        genesis event (digest-identical inserts are no-ops). The genesis
        ``occurred_at`` is pinned to the anchor's own ``as_of`` so identity
        never depends on processing time. A qualifying stratum must agree
        with the frozen anchor-source mapping.
        """
        self._validate_anchor_taxonomy(anchor)
        self._repository.record_anchor(anchor)
        genesis = genesis_transition(anchor, occurred_at=anchor.as_of)
        self._repository.record_transition(genesis)
        return genesis

    def project(self, anchor: OpportunityAnchor) -> OpportunityState:
        """Fold the anchor's append-only transition log into its state.

        The log is authoritative: a rewritten, gapped, or deleted log raises
        instead of silently projecting (no silent deletion, R8).
        """
        return fold_transitions(self._repository.list_transitions(anchor.anchor_id))

    # ------------------------------------------------------------------
    # Membership history (append-only evidence, both arms)
    # ------------------------------------------------------------------

    def record_membership(self, membership: OpportunityMembershipRecord) -> None:
        """Append one membership-history fact for a registered anchor."""
        if self._repository.get_anchor_json(membership.anchor_id) is None:
            raise ValueError("membership history requires a registered anchor")
        self._repository.record_membership(membership)

    def window_state(
        self, anchor: OpportunityAnchor, *, rank_cutoff_k: int = GLOBAL_RANK_CUTOFF_K
    ) -> OpportunityWindowState:
        return fold_window_state(
            anchor,
            self._repository.list_memberships(anchor.anchor_id),
            rank_cutoff_k=rank_cutoff_k,
        )

    # ------------------------------------------------------------------
    # Outcome advancement (WP1 state machine ONLY)
    # ------------------------------------------------------------------

    def resolve(
        self,
        anchor: OpportunityAnchor,
        resolution: OutcomeResolution,
        *,
        reason: str,
        occurred_at: datetime | None = None,
    ) -> OpportunityTransition | None:
        """Advance the anchor exactly one legal WP1 transition and record the
        adjudication through the fail-closed blinding guard.

        Returns the appended transition, or ``None`` when the anchor is
        already in the resolution's terminal state and the resolution is a
        digest-identical replay (no-op). Rejections:

        - PENDING resolutions carry no adjudication claim;
        - RESOLVED adjudications require ``BLINDED`` (service-layer guard);
        - a terminal anchor cannot be mutated into a different state;
        - an unregistered anchor cannot be adjudicated.
        """
        if resolution.resolution_state is OpportunityState.PENDING:
            raise ValueError("a PENDING resolution carries no adjudication claim")
        self._ensure_blinding_guard(resolution)
        if self._repository.get_anchor_json(anchor.anchor_id) is None:
            raise ValueError("cannot adjudicate an unregistered opportunity anchor")
        # Defense in depth: the domain dataclass already enforces the guard;
        # the service refuses to persist an unblinded label regardless.
        self._ensure_blinding_guard(resolution)
        current = self.project(anchor)
        if current is not OpportunityState.PENDING:
            # Terminal: no post-outcome manipulation. A digest-identical
            # replay of the same terminal resolution stays a no-op; anything
            # else is a rejected mutation.
            if resolution.resolution_state is current:
                self._repository.record_resolution(anchor.anchor_id, resolution)
                return None
            raise ValueError(
                f"opportunity is terminal ({current.value}): transition "
                f"{current.value} -> {resolution.resolution_state.value} is not allowed"
            )
        occurred = resolution.decided_at if occurred_at is None else occurred_at
        if occurred is None:
            raise ValueError("an adjudication without decided_at cannot be recorded")
        transition = advance(
            anchor,
            current,
            resolution.resolution_state,
            reason=reason,
            occurred_at=occurred,
        )
        self._repository.record_transition(transition)
        self._repository.record_resolution(anchor.anchor_id, resolution)
        return transition

    def record_unknown_coverage(
        self,
        anchor: OpportunityAnchor,
        *,
        decided_at: datetime,
        evidence_digest: str,
        lane_health_digest: str | None = None,
        reason: str = "outcome lanes not fully covered: absence cannot resolve negative",
    ) -> OpportunityTransition:
        """Record explicit UNKNOWN/UNRESOLVED_COVERAGE (never coerced).

        Missing or unresolvable outcome evidence stays UNKNOWN with the
        ``UNRESOLVED_COVERAGE`` label; no POSITIVE/NEGATIVE label is produced.
        UNKNOWN is terminal and stays UNKNOWN.
        """
        resolution = OutcomeResolution(
            resolution_state=OpportunityState.UNKNOWN,
            label=OutcomeLabel.UNRESOLVED_COVERAGE,
            blinding_state=BlindingState.OPEN,
            decided_at=decided_at,
            evidence_digest=evidence_digest,
            lane_health_digest=lane_health_digest,
        )
        transition = self.resolve(anchor, resolution, reason=reason, occurred_at=decided_at)
        if transition is None:  # pragma: no cover - UNKNOWN from PENDING always appends
            raise RuntimeError("UNKNOWN coverage replay from PENDING unexpectedly resolved")
        return transition

    def resolve_excluded(
        self,
        anchor: OpportunityAnchor,
        *,
        decided_at: datetime,
        reason: str,
    ) -> OpportunityTransition:
        """Record EXCLUDED (no outcome label; e.g. deduplication discard)."""
        resolution = OutcomeResolution(
            resolution_state=OpportunityState.EXCLUDED,
            label=None,
            blinding_state=BlindingState.OPEN,
            decided_at=decided_at,
        )
        transition = self.resolve(anchor, resolution, reason=reason, occurred_at=decided_at)
        if transition is None:  # pragma: no cover - EXCLUDED from PENDING always appends
            raise RuntimeError("EXCLUDED replay from PENDING unexpectedly resolved")
        return transition

    # ------------------------------------------------------------------

    @staticmethod
    def _validate_anchor_taxonomy(anchor: OpportunityAnchor) -> None:
        expected = STRATUM_BY_ANCHOR_SOURCE.get(anchor.source_id)
        if anchor.domain_stratum in (
            DomainStratum.UNQUALIFIED,
            DomainStratum.UNQUALIFIED_MIXED,
        ):
            raise ValueError(
                "an anchor derived from a single canonical observation carries exactly "
                "one frozen V0 stratum, never an aggregate classification"
            )
        if expected is not None and anchor.domain_stratum is not expected:
            raise ValueError(
                f"anchor stratum {anchor.domain_stratum.value} does not match the frozen "
                f"V0 mapping for source {anchor.source_id!r}"
            )

    @staticmethod
    def _ensure_blinding_guard(resolution: OutcomeResolution) -> None:
        """Fail-closed service-layer blinding guard (defense in depth)."""
        if (
            resolution.resolution_state is OpportunityState.RESOLVED
            and resolution.blinding_state is not BlindingState.BLINDED
        ):
            raise ValueError(BLINDING_GUARD_MESSAGE)


__all__ = [
    "MEMBERSHIP_ARMS",
    "OPPORTUNITY_MEMBERSHIP_ID_PREFIX",
    "OPPORTUNITY_MEMBERSHIP_SCHEMA_VERSION",
    "OPPORTUNITY_WINDOW_ID_PREFIX",
    "OPPORTUNITY_WINDOW_SCHEMA_VERSION",
    "PEF_PRIMARY_EMISSION_ROLE",
    "PROSPECT_ELIGIBLE_REASONS",
    "PROSPECT_OBSERVATION_SCHEMA_VERSION",
    "RANKING_WINDOW_SECONDS",
    "STRATUM_BY_ANCHOR_SOURCE",
    "MembershipArm",
    "OpportunityMembershipRecord",
    "OpportunityOutcomeRepository",
    "OpportunityOutcomeService",
    "OpportunityWindowBinding",
    "OpportunityWindowState",
    "ProspectObservation",
    "derive_anchor",
    "detect_anchors",
    "fold_window_state",
    "window_binding_for",
]

MEMBERSHIP_ARMS: tuple[MembershipArm, ...] = (MembershipArm.CANDIDATE, MembershipArm.CONTROL)
