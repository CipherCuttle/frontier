from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from .canonical_json import canonical_json_bytes, canonical_timestamp
from .digests import Digest, sha256_hex


class ProjectionStatus(StrEnum):
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class ProjectionReceipt:
    receipt_schema_version: str
    projection_name: str
    projection_version: str
    schema_version: str
    configuration_digest: Digest
    source_registry_version: Digest
    as_of: datetime
    generated_at: datetime
    input_digest: Digest
    output_digest: Digest
    status: ProjectionStatus
    algorithm_version: str | None = None
    ranking_policy_version: str | None = None

    @property
    def receipt_id(self) -> str:
        material = {
            "algorithm_version": self.algorithm_version,
            "as_of": canonical_timestamp(self.as_of),
            "configuration_digest": str(self.configuration_digest),
            "input_digest": str(self.input_digest),
            "output_digest": str(self.output_digest),
            "projection_name": self.projection_name,
            "projection_version": self.projection_version,
            "ranking_policy_version": self.ranking_policy_version,
            "receipt_schema_version": self.receipt_schema_version,
            "schema_version": self.schema_version,
            "source_registry_version": str(self.source_registry_version),
            "status": self.status.value,
        }
        return "receipt_" + sha256_hex(canonical_json_bytes(material))
