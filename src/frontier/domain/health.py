from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from .canonical_json import CanonicalValue, canonical_json_bytes, canonical_timestamp
from .digests import sha256_hex


class HealthValue(StrEnum):
    OK = "OK"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class SourceHealthObservation:
    source_id: str
    as_of: datetime
    transport: HealthValue
    freshness: HealthValue
    completeness: HealthValue
    schema: HealthValue
    details: dict[str, CanonicalValue]

    @property
    def health_observation_id(self) -> str:
        material = {
            "as_of": canonical_timestamp(self.as_of),
            "completeness": self.completeness.value,
            "details": self.details,
            "freshness": self.freshness.value,
            "schema": self.schema.value,
            "source_id": self.source_id,
            "transport": self.transport.value,
        }
        return "health_" + sha256_hex(canonical_json_bytes(material))
