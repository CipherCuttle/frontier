from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from frontier.domain.digests import Digest
from frontier.domain.grouping import (
    GroupingInput,
    GroupingProjection,
    GroupingRelationInput,
    build_grouping_projection,
    build_grouping_receipt,
)
from frontier.domain.receipt import ProjectionReceipt


class GroupingRepository(Protocol):
    def list_grouping_inputs_as_of(self, as_of: datetime) -> list[GroupingInput]: ...
    def list_grouping_relations_as_of(self, as_of: datetime) -> list[GroupingRelationInput]: ...
    def add_projection_receipt(self, receipt: ProjectionReceipt) -> None: ...


@dataclass(frozen=True, slots=True)
class GroupingRun:
    projection: GroupingProjection
    receipt: ProjectionReceipt


def run_grouping_projection(
    repository: GroupingRepository,
    *,
    as_of: datetime,
    generated_at: datetime,
    source_registry_version: Digest,
) -> GroupingRun:
    inputs = tuple(repository.list_grouping_inputs_as_of(as_of))
    relations = tuple(repository.list_grouping_relations_as_of(as_of))
    projection = build_grouping_projection(inputs, relations=relations, as_of=as_of)
    receipt = build_grouping_receipt(
        projection,
        inputs=inputs,
        relations=relations,
        generated_at=generated_at,
        source_registry_version=source_registry_version,
    )
    repository.add_projection_receipt(receipt)
    return GroupingRun(projection=projection, receipt=receipt)
