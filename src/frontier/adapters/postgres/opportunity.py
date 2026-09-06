"""Append-only PostgreSQL persistence for opportunity/outcome state (WP1).

Projection choice: the current opportunity state is always folded from the
append-only ``opportunity_transitions`` log (no maintained columns), so the
log is the single authority and a rewrite or deletion is detectable at read
time instead of silently accepted.
"""

from __future__ import annotations

from datetime import datetime
from typing import cast

import psycopg
from psycopg.types.json import Jsonb

from frontier.domain.opportunity import (
    OPPORTUNITY_SCHEMA_VERSION,
    OpportunityAnchor,
    OpportunityState,
    OpportunityTransition,
    OutcomeResolution,
    fold_transitions,
)


class PostgresOpportunityRepository:
    """Append-only persistence for preregistered opportunity state."""

    def __init__(self, connection: psycopg.Connection[tuple[object, ...]]) -> None:
        self._connection = connection

    def record_anchor(self, anchor: OpportunityAnchor) -> None:
        if anchor.schema_version != OPPORTUNITY_SCHEMA_VERSION:
            raise ValueError("opportunity anchor schema version mismatch")
        with self._connection.transaction(), self._connection.cursor() as cur:
            cur.execute(
                """
                INSERT INTO opportunity_anchors (
                    anchor_id, schema_version, observation_id, source_id,
                    as_of, observed_at, resolution_at, domain_stratum,
                    episode_id_at_resolution, control_snapshot_id,
                    control_receipt_id, anchor_digest, anchor_json
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (anchor_id) DO NOTHING
                RETURNING anchor_id
                """,
                (
                    anchor.anchor_id,
                    anchor.schema_version,
                    anchor.observation_id,
                    anchor.source_id,
                    anchor.as_of,
                    anchor.observed_at,
                    anchor.resolution_at,
                    anchor.domain_stratum.value,
                    anchor.episode_id_at_resolution,
                    anchor.control_snapshot_id,
                    anchor.control_receipt_id,
                    "sha256:" + anchor.anchor_digest_hex,
                    Jsonb(anchor.to_canonical()),
                ),
            )
            inserted = cur.fetchone()
            if inserted is None:
                cur.execute(
                    "SELECT anchor_digest FROM opportunity_anchors WHERE anchor_id = %s",
                    (anchor.anchor_id,),
                )
                existing = cur.fetchone()
                if existing is None:
                    raise RuntimeError("opportunity anchor conflict without existing row")
                if cast(str, existing[0]) != "sha256:" + anchor.anchor_digest_hex:
                    raise RuntimeError("opportunity anchor identity conflict with different digest")

    def record_transition(self, transition: OpportunityTransition) -> None:
        """Append one lifecycle event; re-inserting the identical event is a no-op."""
        if transition.schema_version != OPPORTUNITY_SCHEMA_VERSION:
            raise ValueError("opportunity transition schema version mismatch")
        with self._connection.transaction(), self._connection.cursor() as cur:
            cur.execute(
                """
                INSERT INTO opportunity_transitions (
                    transition_id, anchor_id, from_state, to_state,
                    reason, occurred_at, event_digest
                ) VALUES (%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (transition_id) DO NOTHING
                RETURNING transition_id
                """,
                (
                    transition.transition_id,
                    transition.anchor_id,
                    None if transition.from_state is None else transition.from_state.value,
                    transition.to_state.value,
                    transition.reason,
                    transition.occurred_at,
                    "sha256:" + transition.event_digest_hex,
                ),
            )
            inserted = cur.fetchone()
            if inserted is None:
                cur.execute(
                    """
                    SELECT anchor_id, event_digest FROM opportunity_transitions
                    WHERE transition_id = %s
                    """,
                    (transition.transition_id,),
                )
                existing = cur.fetchone()
                if existing is None:
                    raise RuntimeError("opportunity transition conflict without existing row")
                if cast(str, existing[0]) != transition.anchor_id or cast(str, existing[1]) != (
                    "sha256:" + transition.event_digest_hex
                ):
                    raise RuntimeError("opportunity transition conflict with different digest")

    def record_resolution(self, anchor_id: str, resolution: OutcomeResolution) -> None:
        """Append the single adjudication row for an anchor (never rewritten)."""
        if resolution.schema_version != OPPORTUNITY_SCHEMA_VERSION:
            raise ValueError("outcome resolution schema version mismatch")
        with self._connection.transaction(), self._connection.cursor() as cur:
            cur.execute(
                """
                INSERT INTO outcome_resolutions (
                    anchor_id, schema_version, resolution_state, label,
                    blinding_state, decided_at, evidence_digest,
                    lane_health_digest, resolution_digest, resolution_json
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (anchor_id) DO NOTHING
                RETURNING anchor_id
                """,
                (
                    anchor_id,
                    resolution.schema_version,
                    resolution.resolution_state.value,
                    None if resolution.label is None else resolution.label.value,
                    None if resolution.blinding_state is None else resolution.blinding_state.value,
                    resolution.decided_at,
                    resolution.evidence_digest,
                    resolution.lane_health_digest,
                    "sha256:" + resolution.resolution_digest_hex,
                    Jsonb(resolution.to_canonical()),
                ),
            )
            inserted = cur.fetchone()
            if inserted is None:
                cur.execute(
                    """
                    SELECT resolution_digest, resolution_state
                    FROM outcome_resolutions WHERE anchor_id = %s
                    """,
                    (anchor_id,),
                )
                existing = cur.fetchone()
                if existing is None:
                    raise RuntimeError("outcome resolution conflict without existing row")
                if (
                    cast(str, existing[0]) != "sha256:" + resolution.resolution_digest_hex
                    or cast(str, existing[1]) != resolution.resolution_state.value
                ):
                    raise RuntimeError("outcome resolution conflict with different digest")

    def read_projection(self, anchor_id: str) -> OpportunityState:
        """Fold the append-only transition log into the current state."""
        transitions = self.list_transitions(anchor_id)
        return fold_transitions(transitions)

    def list_transitions(self, anchor_id: str) -> tuple[OpportunityTransition, ...]:
        with self._connection.cursor() as cur:
            cur.execute(
                """
                SELECT transition_id, anchor_id, from_state, to_state,
                       reason, occurred_at
                FROM opportunity_transitions
                WHERE anchor_id = %s
                ORDER BY occurred_at, transition_id
                """,
                (anchor_id,),
            )
            rows = cur.fetchall()
        return tuple(
            OpportunityTransition(
                anchor_id=cast(str, row[1]),
                from_state=None if row[2] is None else OpportunityState(cast(str, row[2])),
                to_state=OpportunityState(cast(str, row[3])),
                reason=cast(str, row[4]),
                occurred_at=cast(datetime, row[5]),
            )
            for row in rows
        )

    def get_resolution_json(self, anchor_id: str) -> dict[str, object] | None:
        with self._connection.cursor() as cur:
            cur.execute(
                "SELECT resolution_json FROM outcome_resolutions WHERE anchor_id = %s",
                (anchor_id,),
            )
            row = cur.fetchone()
        if row is None:
            return None
        return cast(dict[str, object], row[0])

    def get_anchor_json(self, anchor_id: str) -> dict[str, object] | None:
        with self._connection.cursor() as cur:
            cur.execute(
                "SELECT anchor_json FROM opportunity_anchors WHERE anchor_id = %s",
                (anchor_id,),
            )
            row = cur.fetchone()
        if row is None:
            return None
        return cast(dict[str, object], row[0])

    def count_anchors(self) -> int:
        with self._connection.cursor() as cur:
            cur.execute("SELECT count(*) FROM opportunity_anchors")
            row = cur.fetchone()
        return int(cast(int, row[0])) if row is not None else 0
