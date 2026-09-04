from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .canonical_json import CanonicalValue, canonical_json_bytes
from .digests import sha256_hex


class RelationType(StrEnum):
    CORRECTS = "CORRECTS"
    RETRACTS = "RETRACTS"
    REFERENCES = "REFERENCES"


class RelationAuthority(StrEnum):
    EXPLICIT = "EXPLICIT"
    INFERRED = "INFERRED"


@dataclass(frozen=True, slots=True)
class ObservationRelation:
    relation_type: RelationType
    from_observation_id: str
    authority: RelationAuthority
    evidence: dict[str, CanonicalValue]
    target_observation_id: str | None = None
    target_external_ref: str | None = None
    algorithm_version: str | None = None
    confidence: str | None = None

    def __post_init__(self) -> None:
        if (self.target_observation_id is None) == (self.target_external_ref is None):
            raise ValueError("relation requires exactly one target")
        if self.authority is RelationAuthority.INFERRED and not self.algorithm_version:
            raise ValueError("inferred relation requires algorithm_version")

    @property
    def relation_id(self) -> str:
        material = {
            "algorithm_version": self.algorithm_version,
            "authority": self.authority.value,
            "confidence": self.confidence,
            "evidence": self.evidence,
            "from_observation_id": self.from_observation_id,
            "relation_type": self.relation_type.value,
            "target_external_ref": self.target_external_ref,
            "target_observation_id": self.target_observation_id,
        }
        return "rel_" + sha256_hex(canonical_json_bytes(material))
