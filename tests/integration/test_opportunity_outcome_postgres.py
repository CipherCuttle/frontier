# ruff: noqa: E402
"""Integration tests: WP3 opportunity/outcome engine on PostgreSQL.

End-to-end anchor + membership + transition persistence against the canonical
database: content-derived ids, append-only membership evidence (trigger
enforced), fold-from-log projections equal to the service projection, and a
restart re-fold producing identical state.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

psycopg = pytest.importorskip("psycopg")

from frontier.adapters.postgres import PostgresEvidenceStore
from frontier.adapters.postgres.opportunity import PostgresOpportunityRepository
from frontier.application.opportunity_outcome import (
    MembershipArm,
    OpportunityMembershipRecord,
    OpportunityOutcomeService,
)
from frontier.domain.collection import CollectionReason, CollectionRun
from frontier.domain.digests import sha256_digest
from frontier.domain.observation import (
    ArtifactPayload,
    Observation,
    ObservationCandidate,
    ObservationKind,
)
from frontier.domain.opportunity import (
    BlindingState,
    DomainStratum,
    OpportunityAnchor,
    OpportunityState,
    OutcomeLabel,
    OutcomeResolution,
    fold_transitions,
)
from frontier.domain.source import (
    AcquisitionClass,
    SignalRole,
    SourceContract,
    SourceTransport,
)

DB_URL = os.getenv("FRONTIER_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="FRONTIER_TEST_DATABASE_URL not set")

SOURCE_ID = "fixture.opportunity.outcome.wp3"
EXPERIMENT_ID = "advanced-ranking-pef-v0"


def _test_source() -> SourceContract:
    return SourceContract(
        source_id=SOURCE_ID,
        display_name="WP3 opportunity outcome fixture anchor source",
        acquisition_class=AcquisitionClass.A_AUTHORITATIVE_STRUCTURED,
        signal_roles=(SignalRole.PRIMARY_EMISSION,),
        transport=SourceTransport.FIXTURE,
    )


def _observation_candidate(*, item_key: str, observed_at: datetime) -> ObservationCandidate:
    body = f"fixture wp3 anchor {item_key}".encode()
    return ObservationCandidate(
        source_id=SOURCE_ID,
        source_item_key=item_key,
        kind=ObservationKind.ARTIFACT,
        payload=ArtifactPayload(
            artifact_type="PYTHON_PACKAGE",
            name=item_key,
            version="1.0.0",
        ),
        retrieved_at=observed_at,
        fetch_digest=sha256_digest(body),
    )


def _append_observation(
    evidence: PostgresEvidenceStore, candidate: ObservationCandidate, observed_at: datetime
) -> Observation:
    run = CollectionRun(
        run_id=uuid4(),
        source_id=SOURCE_ID,
        reason=CollectionReason.SCHEDULED,
        started_at=observed_at,
    )
    evidence.start_collection_run(run)
    # Idempotent evidence substrate: re-processing an identical observation is
    # a no-op returning the existing row, so this test is re-run safe.
    observation, _ = evidence.append_observation(candidate, run.run_id)
    return observation


def _anchor(observation_id: str, observed_at: datetime) -> OpportunityAnchor:
    return OpportunityAnchor(
        observation_id=observation_id,
        source_id=SOURCE_ID,
        as_of=observed_at,
        observed_at=observed_at,
        domain_stratum=DomainStratum.SOFTWARE_PACKAGES,
    )


def test_postgres_anchor_membership_and_outcome_end_to_end_with_replay() -> None:
    assert DB_URL is not None
    observed_at = datetime(2026, 9, 5, 12, 0, tzinfo=UTC)

    with psycopg.connect(DB_URL) as conn:
        evidence = PostgresEvidenceStore(conn)
        evidence.upsert_source(_test_source())
        observation = _append_observation(
            evidence,
            _observation_candidate(
                item_key=f"wp3-anchor-primary-emission-{uuid4().hex[:12]}",
                observed_at=observed_at,
            ),
            observed_at,
        )
        # The canonical authority stamps observed_at with the DB clock: every
        # window coordinate derives from the observation's own observed_at so
        # the test stays deterministic across runs.
        base = observation.observed_at
        resolution_at = base + timedelta(seconds=86400)
        boundary_1 = base + timedelta(seconds=300)
        boundary_2 = base + timedelta(seconds=600)
        anchor = _anchor(observation.observation_id, base)
        repository = PostgresOpportunityRepository(conn)
        service = OpportunityOutcomeService(repository)

        # Deterministic registration: replaying register_anchor is a no-op.
        service.register_anchor(anchor)
        service.register_anchor(anchor)
        assert repository.get_anchor_json(anchor.anchor_id) == anchor.to_canonical()
        assert len(repository.list_transitions(anchor.anchor_id)) == 1
        assert service.project(anchor) is OpportunityState.PENDING

        # Membership history: both arms, append-only evidence.
        first_candidate = OpportunityMembershipRecord(
            anchor_id=anchor.anchor_id,
            experiment_id=EXPERIMENT_ID,
            as_of=boundary_1,
            arm=MembershipArm.CANDIDATE,
            present=True,
            episode_id="ep_wp3",
            rank_position=1,
        )
        absent_control = OpportunityMembershipRecord(
            anchor_id=anchor.anchor_id,
            experiment_id=EXPERIMENT_ID,
            as_of=boundary_1,
            arm=MembershipArm.CONTROL,
            present=False,
        )
        first_control = OpportunityMembershipRecord(
            anchor_id=anchor.anchor_id,
            experiment_id=EXPERIMENT_ID,
            as_of=boundary_2,
            arm=MembershipArm.CONTROL,
            present=True,
            episode_id="ep_wp3",
            rank_position=20,
        )
        for _ in range(2):
            service.record_membership(first_candidate)
            service.record_membership(absent_control)
            service.record_membership(first_control)
        stored = repository.list_memberships(anchor.anchor_id)
        assert {item.membership_id for item in stored} == {
            first_candidate.membership_id,
            absent_control.membership_id,
            first_control.membership_id,
        }

        # Window state: first eligible detection is the minimum as_of per arm.
        state = service.window_state(anchor)
        assert state.binding.window_start == anchor.observed_at
        assert state.binding.window_end == anchor.resolution_at
        assert state.first_candidate_detection_at == boundary_1
        assert state.first_control_detection_at == boundary_2

        # Append-only memberships: UPDATE/DELETE/TRUNCATE rejected by trigger.
        with (
            pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState),
            conn.transaction(),
            conn.cursor() as cur,
        ):
            cur.execute(
                "UPDATE opportunity_memberships SET present = NOT present WHERE anchor_id = %s",
                (anchor.anchor_id,),
            )
        with (
            pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState),
            conn.transaction(),
            conn.cursor() as cur,
        ):
            cur.execute(
                "DELETE FROM opportunity_memberships WHERE anchor_id = %s",
                (anchor.anchor_id,),
            )
        with (
            pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState),
            conn.transaction(),
            conn.cursor() as cur,
        ):
            cur.execute("TRUNCATE opportunity_memberships")

        # Digest-different membership at the same identity is a conflict.
        with pytest.raises(RuntimeError, match="conflict with different digest"):
            service.record_membership(
                OpportunityMembershipRecord(
                    anchor_id=anchor.anchor_id,
                    experiment_id=EXPERIMENT_ID,
                    as_of=boundary_1,
                    arm=MembershipArm.CANDIDATE,
                    present=True,
                    episode_id="ep_wp3",
                    rank_position=2,
                )
            )

        # Outcome resolution ONLY through the WP1 state machine + blinding guard.
        resolution = OutcomeResolution(
            resolution_state=OpportunityState.RESOLVED,
            label=OutcomeLabel.POSITIVE,
            blinding_state=BlindingState.BLINDED,
            decided_at=resolution_at,
            evidence_digest="sha256:" + "c" * 64,
        )
        transition = service.resolve(
            anchor, resolution, reason="blinded automated adjudication resolved POSITIVE"
        )
        assert transition is not None
        assert transition.to_state is OpportunityState.RESOLVED
        assert service.project(anchor) is OpportunityState.RESOLVED
        assert repository.get_resolution_json(anchor.anchor_id) == resolution.to_canonical()

        # Idempotent re-processing: identical resolution replays as a no-op.
        replay = service.resolve(anchor, resolution, reason="blinded automated adjudication")
        assert replay is None
        assert len(repository.list_transitions(anchor.anchor_id)) == 2

        # Fold-from-log replay equals the service projection (and survives a
        # fresh adapter, i.e. a restart).
        assert fold_transitions(repository.list_transitions(anchor.anchor_id)) is (
            OpportunityState.RESOLVED
        )
        fresh = PostgresOpportunityRepository(conn)
        assert fresh.read_projection(anchor.anchor_id) is OpportunityState.RESOLVED
        assert {item.membership_id for item in fresh.list_memberships(anchor.anchor_id)} == {
            first_candidate.membership_id,
            absent_control.membership_id,
            first_control.membership_id,
        }


def test_postgres_unknown_coverage_stays_unknown_across_restart() -> None:
    assert DB_URL is not None
    observed_at = datetime(2026, 9, 5, 12, 30, tzinfo=UTC)
    resolution_at = observed_at + timedelta(seconds=86400)

    with psycopg.connect(DB_URL) as conn:
        evidence = PostgresEvidenceStore(conn)
        evidence.upsert_source(_test_source())
        observation = _append_observation(
            evidence,
            _observation_candidate(
                item_key=f"wp3-anchor-unknown-coverage-{uuid4().hex[:12]}",
                observed_at=observed_at,
            ),
            observed_at,
        )
        resolution_at = observation.observed_at + timedelta(seconds=86400)
        anchor = _anchor(observation.observation_id, observation.observed_at)
        service = OpportunityOutcomeService(PostgresOpportunityRepository(conn))
        service.register_anchor(anchor)

        # Missing/unresolvable evidence: UNKNOWN/UNRESOLVED_COVERAGE, never
        # coerced into POSITIVE/NEGATIVE.
        service.record_unknown_coverage(
            anchor,
            decided_at=resolution_at,
            evidence_digest="sha256:" + "e" * 64,
            lane_health_digest="sha256:" + "f" * 64,
        )
        repository = PostgresOpportunityRepository(conn)
        assert repository.read_projection(anchor.anchor_id) is OpportunityState.UNKNOWN
        stored = repository.get_resolution_json(anchor.anchor_id)
        assert stored is not None
        assert stored["label"] == "UNRESOLVED_COVERAGE"

        # UNKNOWN is terminal: a later blinded label attempt is rejected.
        fresh_service = OpportunityOutcomeService(PostgresOpportunityRepository(conn))
        with pytest.raises(ValueError, match="terminal"):
            fresh_service.resolve(
                anchor,
                OutcomeResolution(
                    resolution_state=OpportunityState.RESOLVED,
                    label=OutcomeLabel.NEGATIVE,
                    blinding_state=BlindingState.BLINDED,
                    decided_at=resolution_at,
                    evidence_digest="sha256:" + "d" * 64,
                ),
                reason="late coercion attempt",
            )
        # Restart re-fold produces the identical projection state.
        fresh_repository = PostgresOpportunityRepository(conn)
        assert fresh_repository.read_projection(anchor.anchor_id) is OpportunityState.UNKNOWN
