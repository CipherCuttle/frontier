"""Framework-independent opportunity/outcome state foundations (WP1).

Identity and lifecycle rules derive from the PEF_V0 preregistration
(``experiments/advanced_intelligence/pef_v0/preregistration.json``):
opportunity anchors are prospectively eligible canonical PRIMARY_EMISSION
observations from a frozen V0 anchor source inside the ranking window, with
``resolution_at = anchor.observed_at + 86400`` seconds. Opportunity state is an
append-only transition log folded into a projection; there is no silent
deletion, correction, or rewrite of opportunity state.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from .canonical_json import CanonicalValue, canonical_json_bytes, canonical_timestamp
from .digests import sha256_hex

OPPORTUNITY_SCHEMA_VERSION = "opportunity-outcome-state-v0"
OPPORTUNITY_ANCHOR_ID_PREFIX = "opanchor_"
OPPORTUNITY_TRANSITION_ID_PREFIX = "optrans_"
RUN_ATTEMPT_ID_PREFIX = "opattempt_"

LABEL_MATURATION_SECONDS = 86400

BLINDING_GUARD_MESSAGE = "an adjudication without BLINDED state cannot resolve a label"


class OpportunityState(StrEnum):
    """Explicit opportunity lifecycle states.

    ``PENDING`` anchors await adjudication at ``resolution_at``. ``UNKNOWN``
    stays UNKNOWN: absence of outcome evidence is never coerced into a label.
    """

    PENDING = "PENDING"
    RESOLVED = "RESOLVED"
    EXCLUDED = "EXCLUDED"
    UNKNOWN = "UNKNOWN"


class OutcomeLabel(StrEnum):
    """Preregistration outcome-label vocabulary (model-independent)."""

    POSITIVE = "POSITIVE"
    NEGATIVE = "NEGATIVE"
    UNRESOLVED_COVERAGE = "UNRESOLVED_COVERAGE"


class BlindingState(StrEnum):
    """Adjudication blinding discipline (fail-closed)."""

    BLINDED = "BLINDED"
    OPEN = "OPEN"


class DomainStratum(StrEnum):
    """Source-domain stratum vocabulary (frozen V0 taxonomy; do not extend)."""

    SOFTWARE_PACKAGES = "SOFTWARE_PACKAGES"
    AI_MODELS = "AI_MODELS"
    SECURITY_VULNERABILITIES = "SECURITY_VULNERABILITIES"
    UNQUALIFIED_MIXED = "UNQUALIFIED_MIXED"
    UNQUALIFIED = "UNQUALIFIED"


#: Explicit allowed transitions. Terminal states have no outgoing transitions:
#: RESOLVED and EXCLUDED are final; UNKNOWN stays UNKNOWN.
ALLOWED_TRANSITIONS: dict[OpportunityState, tuple[OpportunityState, ...]] = {
    OpportunityState.PENDING: (
        OpportunityState.RESOLVED,
        OpportunityState.EXCLUDED,
        OpportunityState.UNKNOWN,
    ),
    OpportunityState.RESOLVED: (),
    OpportunityState.EXCLUDED: (),
    OpportunityState.UNKNOWN: (),
}


@dataclass(frozen=True, slots=True)
class OpportunityAnchor:
    """Immutable identity of one preregistered opportunity anchor.

    Content-derived: ``anchor_id`` is the sha256 of the anchor's canonical JSON
    payload, so identical preregistration facts always yield one identity.
    """

    observation_id: str
    source_id: str
    as_of: datetime
    observed_at: datetime
    domain_stratum: DomainStratum
    episode_id_at_resolution: str | None = None
    control_snapshot_id: str | None = None
    control_receipt_id: str | None = None
    schema_version: str = OPPORTUNITY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for label, value in (
            ("as_of", self.as_of),
            ("observed_at", self.observed_at),
        ):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"anchor {label} must be timezone-aware")
        if not self.observation_id.startswith("obs_"):
            raise ValueError("anchor observation id must be a canonical observation id")
        if not self.source_id:
            raise ValueError("anchor source_id must be non-empty")
        if self.observed_at > self.as_of:
            raise ValueError("anchor observed_at cannot be after the as_of boundary")
        if self.episode_id_at_resolution is not None and not self.episode_id_at_resolution:
            raise ValueError("anchor episode id must be non-empty when present")

    @property
    def resolution_at(self) -> datetime:
        return self.observed_at + timedelta(seconds=LABEL_MATURATION_SECONDS)

    def to_canonical(self) -> dict[str, CanonicalValue]:
        return {
            "as_of": canonical_timestamp(self.as_of),
            "control_receipt_id": self.control_receipt_id,
            "control_snapshot_id": self.control_snapshot_id,
            "domain_stratum": self.domain_stratum.value,
            "episode_id_at_resolution": self.episode_id_at_resolution,
            "observation_id": self.observation_id,
            "observed_at": canonical_timestamp(self.observed_at),
            "resolution_at": canonical_timestamp(self.resolution_at),
            "schema_version": self.schema_version,
            "source_id": self.source_id,
        }

    @property
    def anchor_digest_hex(self) -> str:
        return sha256_hex(canonical_json_bytes(self.to_canonical()))

    @property
    def anchor_id(self) -> str:
        return OPPORTUNITY_ANCHOR_ID_PREFIX + self.anchor_digest_hex


@dataclass(frozen=True, slots=True)
class OutcomeResolution:
    """Append-only adjudication of a retained anchor.

    Fail-closed blinding guard: an adjudication without an explicit
    ``BLINDED`` blinding state can never resolve a label. ``PENDING`` rows
    carry no label and no blinding claim. ``UNKNOWN`` stays UNKNOWN.
    """

    resolution_state: OpportunityState
    label: OutcomeLabel | None
    blinding_state: BlindingState | None
    decided_at: datetime | None
    evidence_digest: str | None = None
    lane_health_digest: str | None = None
    schema_version: str = OPPORTUNITY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.decided_at is not None and (
            self.decided_at.tzinfo is None or self.decided_at.utcoffset() is None
        ):
            raise ValueError("resolution decided_at must be timezone-aware")
        if self.resolution_state is OpportunityState.PENDING:
            if self.label is not None:
                raise ValueError("PENDING resolution cannot carry a label")
            if self.blinding_state is not None or self.decided_at is not None:
                raise ValueError("PENDING resolution carries no adjudication claim")
        if self.resolution_state is OpportunityState.RESOLVED:
            if self.label not in (OutcomeLabel.POSITIVE, OutcomeLabel.NEGATIVE):
                raise ValueError("RESOLVED resolution requires POSITIVE or NEGATIVE label")
            if self.blinding_state is not BlindingState.BLINDED:
                raise ValueError(BLINDING_GUARD_MESSAGE)
            if self.decided_at is None or self.evidence_digest is None:
                raise ValueError("RESOLVED resolution requires decided_at and evidence digest")
        if self.resolution_state is OpportunityState.UNKNOWN:
            if self.label is not OutcomeLabel.UNRESOLVED_COVERAGE:
                raise ValueError("UNKNOWN resolution stays UNKNOWN: UNRESOLVED_COVERAGE only")
            if self.decided_at is None or self.evidence_digest is None:
                raise ValueError("UNKNOWN resolution requires decided_at and evidence digest")
        if self.resolution_state is OpportunityState.EXCLUDED:
            if self.label is not None:
                raise ValueError("EXCLUDED resolution carries no outcome label")
            if self.decided_at is None:
                raise ValueError("EXCLUDED resolution requires decided_at")
        if self.lane_health_digest is not None and not self.lane_health_digest.startswith(
            "sha256:"
        ):
            raise ValueError("lane_health_digest must be a sha256 digest")

    def to_canonical(self) -> dict[str, CanonicalValue]:
        return {
            "blinding_state": None if self.blinding_state is None else self.blinding_state.value,
            "decided_at": None if self.decided_at is None else canonical_timestamp(self.decided_at),
            "evidence_digest": self.evidence_digest,
            "label": None if self.label is None else self.label.value,
            "lane_health_digest": self.lane_health_digest,
            "resolution_state": self.resolution_state.value,
            "schema_version": self.schema_version,
        }

    @property
    def resolution_digest_hex(self) -> str:
        return sha256_hex(canonical_json_bytes(self.to_canonical()))


@dataclass(frozen=True, slots=True)
class OpportunityTransition:
    """One append-only event in an anchor's lifecycle log.

    Content-derived: ``transition_id`` is the sha256 of the event's canonical
    payload, so the same event can be re-inserted idempotently and a rewritten
    event always changes identity.
    """

    anchor_id: str
    from_state: OpportunityState | None
    to_state: OpportunityState
    reason: str
    occurred_at: datetime
    schema_version: str = OPPORTUNITY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise ValueError("transition occurred_at must be timezone-aware")
        if not self.reason:
            raise ValueError("transition reason must be non-empty")
        if self.from_state is None:
            if self.to_state is not OpportunityState.PENDING:
                raise ValueError("the genesis transition must enter PENDING")
        else:
            if self.from_state is self.to_state:
                raise ValueError("transition states must differ")
            if self.to_state is OpportunityState.PENDING:
                raise ValueError("PENDING can only be entered from nothing (genesis)")
            if self.to_state not in ALLOWED_TRANSITIONS[self.from_state]:
                raise ValueError(
                    f"transition {self.from_state.value} -> {self.to_state.value} is not allowed"
                )

    def to_canonical(self) -> dict[str, CanonicalValue]:
        return {
            "anchor_id": self.anchor_id,
            "from_state": None if self.from_state is None else self.from_state.value,
            "occurred_at": canonical_timestamp(self.occurred_at),
            "reason": self.reason,
            "schema_version": self.schema_version,
            "to_state": self.to_state.value,
        }

    @property
    def event_digest_hex(self) -> str:
        return sha256_hex(canonical_json_bytes(self.to_canonical()))

    @property
    def transition_id(self) -> str:
        return OPPORTUNITY_TRANSITION_ID_PREFIX + self.event_digest_hex


def genesis_transition(
    anchor: OpportunityAnchor, *, occurred_at: datetime
) -> OpportunityTransition:
    """Create the PENDING genesis event for an anchor."""
    return OpportunityTransition(
        anchor_id=anchor.anchor_id,
        from_state=None,
        to_state=OpportunityState.PENDING,
        reason="anchor recorded prospectively",
        occurred_at=occurred_at,
    )


def advance(
    anchor: OpportunityAnchor,
    current: OpportunityState,
    to_state: OpportunityState,
    *,
    reason: str,
    occurred_at: datetime,
) -> OpportunityTransition:
    """Build the next explicit transition from the current projection state."""
    if to_state not in ALLOWED_TRANSITIONS[current]:
        raise ValueError(f"transition {current.value} -> {to_state.value} is not allowed")
    return OpportunityTransition(
        anchor_id=anchor.anchor_id,
        from_state=current,
        to_state=to_state,
        reason=reason,
        occurred_at=occurred_at,
    )


def fold_transitions(transitions: tuple[OpportunityTransition, ...]) -> OpportunityState:
    """Replay the append-only transition log into the current projection state.

    The log is authoritative: any gap, rewrite, deletion, or illegal
    transition raises instead of being silently accepted. An anchor with no
    events is never projected (an anchor exists only with its genesis event).
    """
    if not transitions:
        raise ValueError("no transition log to fold: opportunity state cannot be guessed")
    state: OpportunityState | None = None
    for transition in transitions:
        if transition.from_state != state:
            raise ValueError(
                "transition log is not contiguous at "
                f"{transition.transition_id}: expected from_state "
                f"{None if state is None else state.value}, found "
                f"{None if transition.from_state is None else transition.from_state.value}"
            )
        if state is None:
            if transition.to_state is not OpportunityState.PENDING:
                raise ValueError("transition log must begin with the PENDING genesis event")
            state = OpportunityState.PENDING
            continue
        if transition.to_state not in ALLOWED_TRANSITIONS[state]:
            raise ValueError(
                f"transition {state.value} -> {transition.to_state.value} is not allowed"
            )
        state = transition.to_state
    if state is None:  # pragma: no cover - unreachable: the loop sets state on the first event
        raise ValueError("transition log did not produce a projection state")
    return state


def transition_log_is_sound(transitions: tuple[OpportunityTransition, ...]) -> bool:
    """True when the log is a valid, gap-free replay (no silent deletion)."""
    try:
        fold_transitions(transitions)
    except ValueError:
        return False
    return True


__all__ = [
    "ALLOWED_TRANSITIONS",
    "BLINDING_GUARD_MESSAGE",
    "LABEL_MATURATION_SECONDS",
    "OPPORTUNITY_ANCHOR_ID_PREFIX",
    "OPPORTUNITY_SCHEMA_VERSION",
    "OPPORTUNITY_TRANSITION_ID_PREFIX",
    "RUN_ATTEMPT_ID_PREFIX",
    "BlindingState",
    "DomainStratum",
    "OpportunityAnchor",
    "OpportunityState",
    "OpportunityTransition",
    "OutcomeLabel",
    "OutcomeResolution",
    "advance",
    "fold_transitions",
    "genesis_transition",
    "transition_log_is_sound",
]
