from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Protocol

from .canonical_json import (
    CanonicalValue,
    canonical_decimal,
    canonical_json_bytes,
    canonical_timestamp,
)
from .digests import Digest, sha256_digest, sha256_hex

OBSERVATION_SCHEMA_VERSION = "observation-v1"
CANONICALIZATION_VERSION = "frontier-canonical-json-v1"
_SOURCE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{1,63}$")


class ObservationKind(StrEnum):
    DOCUMENT = "DOCUMENT"
    ARTIFACT = "ARTIFACT"
    METRIC = "METRIC"


class Payload(Protocol):
    def to_canonical(self) -> dict[str, CanonicalValue]: ...


def _empty_canonical_map() -> dict[str, CanonicalValue]:
    return {}


def _bounded_text(value: str | None, *, name: str, maximum: int) -> None:
    if value is not None and len(value.encode("utf-8")) > maximum:
        raise ValueError(f"{name} exceeds {maximum} bytes")


def _bounded_metadata(value: dict[str, CanonicalValue]) -> None:
    if len(canonical_json_bytes(value)) > 32768:
        raise ValueError("source_metadata exceeds 32768 canonical bytes")


def _require_aware(value: datetime | None, *, name: str) -> None:
    if value is not None and (value.tzinfo is None or value.utcoffset() is None):
        raise ValueError(f"{name} must be timezone-aware")


@dataclass(frozen=True, slots=True)
class DocumentPayload:
    canonical_url: str | None
    title: str | None
    excerpt: str | None
    language: str | None = None
    source_metadata: dict[str, CanonicalValue] = field(default_factory=_empty_canonical_map)

    def __post_init__(self) -> None:
        _bounded_text(self.canonical_url, name="canonical_url", maximum=4096)
        _bounded_text(self.title, name="title", maximum=2048)
        _bounded_text(self.excerpt, name="excerpt", maximum=8192)
        _bounded_text(self.language, name="language", maximum=64)
        _bounded_metadata(self.source_metadata)

    def to_canonical(self) -> dict[str, CanonicalValue]:
        return {
            "canonical_url": self.canonical_url,
            "excerpt": self.excerpt,
            "language": self.language,
            "source_metadata": self.source_metadata,
            "title": self.title,
        }


@dataclass(frozen=True, slots=True)
class ArtifactPayload:
    artifact_type: str
    name: str
    version: str | None = None
    canonical_url: str | None = None
    artifact_digest: str | None = None
    source_metadata: dict[str, CanonicalValue] = field(default_factory=_empty_canonical_map)

    def __post_init__(self) -> None:
        for name, value, maximum in (
            ("artifact_type", self.artifact_type, 128),
            ("name", self.name, 2048),
            ("version", self.version, 512),
            ("canonical_url", self.canonical_url, 4096),
            ("artifact_digest", self.artifact_digest, 256),
        ):
            _bounded_text(value, name=name, maximum=maximum)
        _bounded_metadata(self.source_metadata)

    def to_canonical(self) -> dict[str, CanonicalValue]:
        return {
            "artifact_digest": self.artifact_digest,
            "artifact_type": self.artifact_type,
            "canonical_url": self.canonical_url,
            "name": self.name,
            "source_metadata": self.source_metadata,
            "version": self.version,
        }


@dataclass(frozen=True, slots=True)
class MetricPayload:
    metric_name: str
    value: str
    unit: str | None
    measurement_at: datetime
    dimensions: dict[str, CanonicalValue] = field(default_factory=_empty_canonical_map)
    source_metadata: dict[str, CanonicalValue] = field(default_factory=_empty_canonical_map)

    def __post_init__(self) -> None:
        _bounded_text(self.metric_name, name="metric_name", maximum=256)
        _bounded_text(self.value, name="value", maximum=256)
        _bounded_text(self.unit, name="unit", maximum=128)
        _require_aware(self.measurement_at, name="measurement_at")
        _bounded_metadata(self.dimensions)
        _bounded_metadata(self.source_metadata)

    @classmethod
    def from_decimal(
        cls,
        *,
        metric_name: str,
        value: Decimal,
        unit: str | None,
        measurement_at: datetime,
        dimensions: dict[str, CanonicalValue] | None = None,
        source_metadata: dict[str, CanonicalValue] | None = None,
    ) -> MetricPayload:
        return cls(
            metric_name=metric_name,
            value=canonical_decimal(value),
            unit=unit,
            measurement_at=measurement_at,
            dimensions=dimensions or {},
            source_metadata=source_metadata or {},
        )

    def to_canonical(self) -> dict[str, CanonicalValue]:
        return {
            "dimensions": self.dimensions,
            "measurement_at": canonical_timestamp(self.measurement_at),
            "metric_name": self.metric_name,
            "source_metadata": self.source_metadata,
            "unit": self.unit,
            "value": self.value,
        }


@dataclass(frozen=True, slots=True)
class ObservationCandidate:
    source_id: str
    source_item_key: str
    kind: ObservationKind
    payload: DocumentPayload | ArtifactPayload | MetricPayload
    retrieved_at: datetime
    fetch_digest: Digest
    source_published_at: datetime | None = None
    effective_at: datetime | None = None
    schema_version: str = OBSERVATION_SCHEMA_VERSION
    canonicalization_version: str = CANONICALIZATION_VERSION

    def __post_init__(self) -> None:
        if not _SOURCE_ID_RE.fullmatch(self.source_id):
            raise ValueError("invalid source_id")
        if not self.source_item_key or len(self.source_item_key.encode("utf-8")) > 4096:
            raise ValueError("source_item_key must be 1..4096 bytes")
        _require_aware(self.retrieved_at, name="retrieved_at")
        _require_aware(self.source_published_at, name="source_published_at")
        _require_aware(self.effective_at, name="effective_at")
        expected_payload = {
            ObservationKind.DOCUMENT: DocumentPayload,
            ObservationKind.ARTIFACT: ArtifactPayload,
            ObservationKind.METRIC: MetricPayload,
        }[self.kind]
        if not isinstance(self.payload, expected_payload):
            raise ValueError(f"{self.kind.value} observation requires {expected_payload.__name__}")

    def identity_material(self) -> dict[str, CanonicalValue]:
        return {
            "canonicalization_version": self.canonicalization_version,
            "effective_at": canonical_timestamp(self.effective_at) if self.effective_at else None,
            "kind": self.kind.value,
            "payload": self.payload.to_canonical(),
            "schema_version": self.schema_version,
            "source_id": self.source_id,
            "source_item_key": self.source_item_key,
            "source_published_at": canonical_timestamp(self.source_published_at)
            if self.source_published_at
            else None,
        }

    @property
    def observation_id(self) -> str:
        return "obs_" + sha256_hex(canonical_json_bytes(self.identity_material()))

    @property
    def content_digest(self) -> Digest:
        content = {
            "effective_at": canonical_timestamp(self.effective_at) if self.effective_at else None,
            "kind": self.kind.value,
            "payload": self.payload.to_canonical(),
            "source_published_at": canonical_timestamp(self.source_published_at)
            if self.source_published_at
            else None,
        }
        return sha256_digest(canonical_json_bytes(content))


@dataclass(frozen=True, slots=True)
class Observation:
    candidate: ObservationCandidate
    observed_at: datetime

    def __post_init__(self) -> None:
        _require_aware(self.observed_at, name="observed_at")

    @property
    def observation_id(self) -> str:
        return self.candidate.observation_id

    def to_canonical(self) -> dict[str, CanonicalValue]:
        return {
            **self.candidate.identity_material(),
            "content_digest": str(self.candidate.content_digest),
            "fetch_digest": str(self.candidate.fetch_digest),
            "observed_at": canonical_timestamp(self.observed_at),
            "retrieved_at": canonical_timestamp(self.candidate.retrieved_at),
        }
