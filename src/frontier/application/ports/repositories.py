from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID

from frontier.domain.collection import CollectionRun
from frontier.domain.health import SourceHealthObservation
from frontier.domain.observation import Observation, ObservationCandidate
from frontier.domain.relation import ObservationRelation
from frontier.domain.source import SourceContract


class EvidenceRepository(Protocol):
    def upsert_source(self, source: SourceContract) -> None: ...
    def start_collection_run(self, run: CollectionRun) -> None: ...
    def append_observation(
        self, candidate: ObservationCandidate, run_id: UUID
    ) -> tuple[Observation, bool]: ...
    def list_observation_ids_as_of(self, as_of: datetime) -> list[str]: ...
    def add_relation(self, relation: ObservationRelation) -> None: ...
    def add_source_health(
        self, health: SourceHealthObservation, run_id: UUID | None = None
    ) -> None: ...
