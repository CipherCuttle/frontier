from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from frontier.domain.intelligence import BaselineSnapshot
from frontier.domain.pef_v1 import PefV1Artifact
from frontier.domain.receipt import ProjectionReceipt


@dataclass(frozen=True, slots=True)
class ExactNaiveBenchmarkBoundary:
    snapshot: BaselineSnapshot
    receipt: ProjectionReceipt


@dataclass(frozen=True, slots=True)
class ExactPefV1BenchmarkBoundary:
    run_id: str
    artifact: PefV1Artifact
    receipt: ProjectionReceipt


class InternalBenchmarkBoundaryResolver(Protocol):
    """Resolve only exact retained internal benchmark boundaries.

    ``None`` means the requested boundary does not exist. Persistence ambiguity or
    integrity drift must raise rather than choosing a latest/nearest substitute.
    """

    def resolve_naive(
        self, knowledge_horizon: datetime
    ) -> ExactNaiveBenchmarkBoundary | None: ...

    def resolve_pef_v1(
        self, knowledge_horizon: datetime
    ) -> ExactPefV1BenchmarkBoundary | None: ...


__all__ = [
    "ExactNaiveBenchmarkBoundary",
    "ExactPefV1BenchmarkBoundary",
    "InternalBenchmarkBoundaryResolver",
]
