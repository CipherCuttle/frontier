from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID

from frontier.application.acquisition_state import SourceFetchState
from frontier.domain.collection import CollectionRun, CollectionRunStatus
from frontier.domain.digests import Digest
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


class AcquisitionRepository(EvidenceRepository, Protocol):
    def complete_collection_run(
        self,
        run_id: UUID,
        *,
        status: CollectionRunStatus,
        records_received: int,
        records_accepted: int,
        records_rejected: int,
        duplicates: int,
        failure_code: str | None,
    ) -> None: ...

    def get_source_fetch_state(self, source_id: str) -> SourceFetchState | None: ...

    def record_fetch_success(
        self,
        source_id: str,
        *,
        etag: str | None,
        last_modified: str | None,
        body_digest: Digest,
        succeeded_at: datetime,
    ) -> None: ...

    def record_fetch_failure(
        self,
        source_id: str,
        *,
        next_retry_at: datetime | None,
    ) -> None: ...
