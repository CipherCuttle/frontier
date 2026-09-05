from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from frontier.domain.digests import Digest
from frontier.domain.grouping import GroupingRelationInput, build_grouping_projection
from frontier.domain.intelligence import (
    BaselineHealthInput,
    BaselineObservationInput,
    BaselineSnapshot,
    build_baseline_receipt,
    build_baseline_snapshot,
)
from frontier.domain.receipt import ProjectionReceipt


class BaselineIntelligenceRepository(Protocol):
    def list_baseline_observations_as_of(self, as_of: datetime) -> list[BaselineObservationInput]: ...
    def list_grouping_relations_as_of(self, as_of: datetime) -> list[GroupingRelationInput]: ...
    def list_enabled_source_ids(self) -> list[str]: ...
    def list_latest_health_as_of(self, as_of: datetime) -> list[BaselineHealthInput]: ...
    def publish_complete_snapshot(
        self, snapshot: BaselineSnapshot, receipt: ProjectionReceipt
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class BaselineIntelligenceRun:
    snapshot: BaselineSnapshot
    receipt: ProjectionReceipt


def run_baseline_intelligence(
    repository: BaselineIntelligenceRepository,
    *,
    as_of: datetime,
    generated_at: datetime,
    source_registry_version: Digest,
) -> BaselineIntelligenceRun:
    observations = tuple(repository.list_baseline_observations_as_of(as_of))
    relations = tuple(repository.list_grouping_relations_as_of(as_of))
    enabled_source_ids = tuple(repository.list_enabled_source_ids())
    health = tuple(repository.list_latest_health_as_of(as_of))

    grouping_projection = build_grouping_projection(
        (item.grouping for item in observations), relations=relations, as_of=as_of
    )
    snapshot = build_baseline_snapshot(
        observations,
        grouping_projection=grouping_projection,
        enabled_source_ids=enabled_source_ids,
        health=health,
        as_of=as_of,
    )
    receipt = build_baseline_receipt(
        snapshot,
        observations=observations,
        grouping_projection=grouping_projection,
        enabled_source_ids=enabled_source_ids,
        health=health,
        generated_at=generated_at,
        source_registry_version=source_registry_version,
    )
    repository.publish_complete_snapshot(snapshot, receipt)
    return BaselineIntelligenceRun(snapshot=snapshot, receipt=receipt)
