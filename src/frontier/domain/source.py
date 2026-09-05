from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from .canonical_json import CanonicalValue, canonical_json_bytes
from .digests import Digest, sha256_digest

_SOURCE_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{1,63}$")


class AcquisitionClass(StrEnum):
    A_AUTHORITATIVE_STRUCTURED = "A_AUTHORITATIVE_STRUCTURED"
    B_OPEN_AGGREGATION = "B_OPEN_AGGREGATION"
    C_PERMITTED_EXTRACTION = "C_PERMITTED_EXTRACTION"
    D_FRAGILE_UI_EXTRACTION = "D_FRAGILE_UI_EXTRACTION"


class SignalRole(StrEnum):
    PRIMARY_EMISSION = "PRIMARY_EMISSION"
    DISCOVERY = "DISCOVERY"
    ATTENTION = "ATTENTION"
    BEHAVIORAL = "BEHAVIORAL"
    CORROBORATION = "CORROBORATION"


class SourceTransport(StrEnum):
    RSS = "RSS"
    ATOM = "ATOM"
    JSON_HTTP = "JSON_HTTP"
    REST = "REST"
    BULK_FILE = "BULK_FILE"
    HTML = "HTML"
    BROWSER = "BROWSER"
    FIXTURE = "FIXTURE"


@dataclass(frozen=True, slots=True)
class SourceContract:
    source_id: str
    display_name: str
    acquisition_class: AcquisitionClass
    signal_roles: tuple[SignalRole, ...]
    transport: SourceTransport
    enabled: bool = True

    def __post_init__(self) -> None:
        if not _SOURCE_RE.fullmatch(self.source_id):
            raise ValueError("invalid source_id")
        if not self.display_name.strip():
            raise ValueError("display_name is required")
        ordered = tuple(sorted(set(self.signal_roles), key=str))
        object.__setattr__(self, "signal_roles", ordered)

    def to_canonical(self) -> dict[str, CanonicalValue]:
        return {
            "acquisition_class": self.acquisition_class.value,
            "display_name": self.display_name,
            "enabled": self.enabled,
            "signal_roles": [role.value for role in self.signal_roles],
            "source_id": self.source_id,
            "transport": self.transport.value,
        }

    @property
    def contract_digest(self) -> Digest:
        return sha256_digest(canonical_json_bytes(self.to_canonical()))


def source_registry_version(contracts: tuple[SourceContract, ...]) -> Digest:
    ordered = sorted(
        (contract.to_canonical() for contract in contracts), key=lambda item: str(item["source_id"])
    )
    return sha256_digest(canonical_json_bytes(ordered))
