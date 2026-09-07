from __future__ import annotations

from datetime import UTC, datetime, timedelta
from hashlib import sha256

import pytest

from frontier.domain.opportunity import (
    ALLOWED_TRANSITIONS,
    BLINDING_GUARD_MESSAGE,
    OPPORTUNITY_ANCHOR_ID_PREFIX,
    OPPORTUNITY_TRANSITION_ID_PREFIX,
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
    transition_log_is_sound,
)

OBSERVATION_ID = "obs_" + "a" * 64
SOURCE_ID = "pypi.updates"


def build_anchor(**overrides: object) -> OpportunityAnchor:
    values: dict[str, object] = {
        "observation_id": OBSERVATION_ID,
        "source_id": SOURCE_ID,
        "as_of": _dt(300),
        "observed_at": _dt(0),
        "domain_stratum": DomainStratum.SOFTWARE_PACKAGES,
    }
    values.update(overrides)
    return OpportunityAnchor(**values)  # type: ignore[arg-type]


def _dt(seconds: int) -> datetime:
    return datetime(2026, 9, 1, tzinfo=UTC) + timedelta(seconds=seconds)


def test_anchor_id_is_content_derived_and_deterministic() -> None:
    anchor = build_anchor()
    assert anchor.anchor_id.startswith(OPPORTUNITY_ANCHOR_ID_PREFIX)
    assert anchor.anchor_id == build_anchor().anchor_id
    drifted = build_anchor(observed_at=_dt(1))
    assert drifted.anchor_id != anchor.anchor_id


def test_resolution_at_is_preregistration_maturation_window() -> None:
    anchor = build_anchor()
    assert anchor.resolution_at == _dt(86400)


def test_anchor_requires_timezone_aware_timestamps() -> None:
    from datetime import datetime

    naive = datetime(2026, 9, 1)
    with pytest.raises(ValueError, match="timezone-aware"):
        build_anchor(as_of=naive)


def test_anchor_observed_at_must_be_within_window_at_as_of() -> None:
    with pytest.raises(ValueError, match="after the as_of boundary"):
        build_anchor(as_of=_dt(-1))


def test_state_machine_has_explicit_terminal_states() -> None:
    assert ALLOWED_TRANSITIONS[OpportunityState.PENDING] == (
        OpportunityState.RESOLVED,
        OpportunityState.EXCLUDED,
        OpportunityState.UNKNOWN,
    )
    for terminal in (
        OpportunityState.RESOLVED,
        OpportunityState.EXCLUDED,
        OpportunityState.UNKNOWN,
    ):
        assert ALLOWED_TRANSITIONS[terminal] == ()


def test_illegal_transition_is_rejected() -> None:
    anchor = build_anchor()
    with pytest.raises(ValueError, match="is not allowed"):
        advance(
            anchor,
            OpportunityState.PENDING,
            OpportunityState.PENDING,
            reason="no-op",
            occurred_at=_dt(1),
        )
    with pytest.raises(ValueError, match="is not allowed"):
        advance(
            anchor,
            OpportunityState.RESOLVED,
            OpportunityState.EXCLUDED,
            reason="terminal states never advance",
            occurred_at=_dt(1),
        )


def test_fold_transitions_replays_genesis_and_terminal_transition() -> None:
    anchor = build_anchor()
    log = (
        genesis_transition(anchor, occurred_at=_dt(1)),
        advance(
            anchor,
            OpportunityState.PENDING,
            OpportunityState.RESOLVED,
            reason="positive outcome adjudicated",
            occurred_at=_dt(90000),
        ),
    )
    assert fold_transitions(log) is OpportunityState.RESOLVED


def test_fold_transitions_rejects_gap_in_log() -> None:
    anchor = build_anchor()
    log = (
        genesis_transition(anchor, occurred_at=_dt(1)),
        advance(
            anchor,
            OpportunityState.PENDING,
            OpportunityState.RESOLVED,
            reason="adjudicated",
            occurred_at=_dt(86401),
        ),
    )
    rewritten = (
        *log,
        OpportunityTransition(
            anchor_id=anchor.anchor_id,
            from_state=OpportunityState.PENDING,
            to_state=OpportunityState.EXCLUDED,
            reason="attempted rewrite after RESOLVED",
            occurred_at=_dt(90000),
        ),
    )
    with pytest.raises(ValueError, match="not contiguous"):
        fold_transitions(rewritten)
    assert transition_log_is_sound(rewritten) is False


def test_fold_transitions_rejects_silent_deletion() -> None:
    anchor = build_anchor()
    genesis = genesis_transition(anchor, occurred_at=_dt(1))
    terminal = advance(
        anchor,
        OpportunityState.PENDING,
        OpportunityState.EXCLUDED,
        reason="excluded by deduplication",
        occurred_at=_dt(86400),
    )
    deleted_log = (terminal,)
    with pytest.raises(ValueError, match="not contiguous"):
        fold_transitions(deleted_log)
    assert fold_transitions((genesis,)) is OpportunityState.PENDING
    assert transition_log_is_sound(deleted_log) is False


def test_fold_transitions_requires_a_log() -> None:
    with pytest.raises(ValueError, match="cannot be guessed"):
        fold_transitions(())


def test_unknown_stays_unknown() -> None:
    anchor = build_anchor()
    log = (
        genesis_transition(anchor, occurred_at=_dt(1)),
        advance(
            anchor,
            OpportunityState.PENDING,
            OpportunityState.UNKNOWN,
            reason="unresolved coverage; unknown stays unknown",
            occurred_at=_dt(86400),
        ),
    )
    assert fold_transitions(log) is OpportunityState.UNKNOWN


def test_transition_id_is_content_derived() -> None:
    anchor = build_anchor()
    transition = genesis_transition(anchor, occurred_at=_dt(1))
    assert transition.transition_id.startswith(OPPORTUNITY_TRANSITION_ID_PREFIX)
    same_event = genesis_transition(anchor, occurred_at=_dt(1))
    assert same_event.transition_id == transition.transition_id


def test_blinding_guard_blocks_unblinded_label_resolution() -> None:
    with pytest.raises(ValueError) as exc:
        OutcomeResolution(
            resolution_state=OpportunityState.RESOLVED,
            label=OutcomeLabel.POSITIVE,
            blinding_state=None,
            decided_at=_dt(86400),
            evidence_digest="sha256:" + "b" * 64,
        )
    assert BLINDING_GUARD_MESSAGE in str(exc.value)
    with pytest.raises(ValueError, match="BLINDED state"):
        OutcomeResolution(
            resolution_state=OpportunityState.RESOLVED,
            label=OutcomeLabel.NEGATIVE,
            blinding_state=BlindingState.OPEN,
            decided_at=_dt(86400),
            evidence_digest="sha256:" + "b" * 64,
        )


def test_blinded_resolution_is_accepted() -> None:
    resolution = OutcomeResolution(
        resolution_state=OpportunityState.RESOLVED,
        label=OutcomeLabel.POSITIVE,
        blinding_state=BlindingState.BLINDED,
        decided_at=_dt(86400),
        evidence_digest="sha256:" + "b" * 64,
    )
    assert resolution.resolution_digest_hex.startswith("")


def test_pending_resolution_carries_no_label_or_blinding_claim() -> None:
    resolution = OutcomeResolution(
        resolution_state=OpportunityState.PENDING,
        label=None,
        blinding_state=None,
        decided_at=None,
    )
    assert resolution.resolution_state is OpportunityState.PENDING
    with pytest.raises(ValueError, match="cannot carry a label"):
        OutcomeResolution(
            resolution_state=OpportunityState.PENDING,
            label=OutcomeLabel.POSITIVE,
            blinding_state=None,
            decided_at=None,
        )


def test_unknown_resolution_stays_unknown_and_carries_coverage_label() -> None:
    resolution = OutcomeResolution(
        resolution_state=OpportunityState.UNKNOWN,
        label=OutcomeLabel.UNRESOLVED_COVERAGE,
        blinding_state=BlindingState.BLINDED,
        decided_at=_dt(86400),
        evidence_digest="sha256:" + "b" * 64,
    )
    assert resolution.label is OutcomeLabel.UNRESOLVED_COVERAGE
    with pytest.raises(ValueError, match="stays UNKNOWN"):
        OutcomeResolution(
            resolution_state=OpportunityState.UNKNOWN,
            label=OutcomeLabel.NEGATIVE,
            blinding_state=BlindingState.BLINDED,
            decided_at=_dt(86400),
            evidence_digest="sha256:" + "b" * 64,
        )


def test_resolution_identity_is_content_derived() -> None:
    from frontier.domain.canonical_json import canonical_json_bytes

    resolution = OutcomeResolution(
        resolution_state=OpportunityState.EXCLUDED,
        label=None,
        blinding_state=BlindingState.BLINDED,
        decided_at=_dt(86400),
    )
    payload = resolution.to_canonical()
    assert resolution.resolution_digest_hex == sha256(canonical_json_bytes(payload)).hexdigest()
