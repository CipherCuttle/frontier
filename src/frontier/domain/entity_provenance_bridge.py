"""Bounded canonical -> experimental ENTITY_PROVENANCE_BRIDGE_V0.

This module is deliberately domain-local and ephemeral. It does not persist bridge
records, mutate canonical evidence, or grant entity/provenance truth authority.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Final

from .canonical_json import CanonicalValue, canonical_json_bytes, canonical_timestamp
from .entity_provenance_lab import LabObservation
from .observation import ArtifactPayload, DocumentPayload, Observation, ObservationKind
from .relation import ObservationRelation

BRIDGE_SCHEMA_VERSION: Final = "entity-provenance-bridge-run-v0"
BRIDGE_ALGORITHM_VERSION: Final = "entity-provenance-bridge-v0"
BRIDGE_AUTHORITY_STATE: Final = "EXPERIMENTAL_EPHEMERAL_ONLY"

SUPPORTED_ENTITY_SOURCES: Final = frozenset(
    {"pypi.updates", "cisa.kev", "github.ml-repos", "hf.models"}
)
UNSUPPORTED_ENTITY_SOURCES: Final = frozenset({"arxiv.cs-ai", "gdelt.frontier", "hn.frontpage"})
BRIDGE_SOURCE_REGISTRY: Final = tuple(sorted(SUPPORTED_ENTITY_SOURCES | UNSUPPORTED_ENTITY_SOURCES))
_CVE_RE: Final = re.compile(r"^CVE-\d{4}-\d{4,}$")


class EntityBridgeState(StrEnum):
    SUPPORTED = "SUPPORTED"
    DEGRADED = "DEGRADED"
    UNSUPPORTED = "UNSUPPORTED"


@dataclass(frozen=True, slots=True)
class KnownObservationRelation:
    """Canonical relation plus the time FRONTIER durably knew that relation."""

    relation: ObservationRelation
    known_at: datetime

    def __post_init__(self) -> None:
        _aware(self.known_at, "known_at")


@dataclass(frozen=True, slots=True)
class BridgeObservation:
    observation_id: str
    source_id: str
    source_item_key: str
    observed_at: datetime
    state: EntityBridgeState
    entity_type: str | None
    native_id: str | None
    malformed_identity_fields: int
    reasons: tuple[str, ...]
    lab_observation: LabObservation | None

    @property
    def entity_supported(self) -> bool:
        return self.state is not EntityBridgeState.UNSUPPORTED

    def to_canonical(self) -> dict[str, CanonicalValue]:
        return {
            "authority_state": BRIDGE_AUTHORITY_STATE,
            "entity_supported": self.entity_supported,
            "entity_type": self.entity_type,
            "malformed_identity_fields": self.malformed_identity_fields,
            "native_id": self.native_id,
            "observation_id": self.observation_id,
            "observed_at": canonical_timestamp(self.observed_at),
            "reasons": list(self.reasons),
            "source_id": self.source_id,
            "source_item_key": self.source_item_key,
            "state": self.state.value,
        }


@dataclass(frozen=True, slots=True)
class SourceBridgeCoverage:
    total_pit_eligible_observations: int = 0
    entity_bridge_supported: int = 0
    entity_bridge_degraded: int = 0
    entity_bridge_unsupported: int = 0
    native_id_signal_count: int = 0
    malformed_identity_field_count: int = 0

    def to_canonical(self) -> dict[str, CanonicalValue]:
        return {
            "entity_bridge_degraded": self.entity_bridge_degraded,
            "entity_bridge_supported": self.entity_bridge_supported,
            "entity_bridge_unsupported": self.entity_bridge_unsupported,
            "malformed_identity_field_count": self.malformed_identity_field_count,
            "native_id_signal_count": self.native_id_signal_count,
            "total_pit_eligible_observations": self.total_pit_eligible_observations,
        }


@dataclass(frozen=True, slots=True)
class BridgeCoverageReport:
    by_source: dict[str, SourceBridgeCoverage]
    direct_derivation_evidence_count: int
    eligible_weak_relation_count: int
    ignored_future_observation_count: int
    ignored_future_relation_count: int
    ignored_ineligible_relation_count: int

    def to_canonical(self) -> dict[str, CanonicalValue]:
        return {
            "by_source": {
                source_id: self.by_source[source_id].to_canonical()
                for source_id in sorted(self.by_source)
            },
            "direct_derivation_evidence_count": self.direct_derivation_evidence_count,
            "eligible_weak_relation_count": self.eligible_weak_relation_count,
            "ignored_future_observation_count": self.ignored_future_observation_count,
            "ignored_future_relation_count": self.ignored_future_relation_count,
            "ignored_ineligible_relation_count": self.ignored_ineligible_relation_count,
        }


@dataclass(frozen=True, slots=True)
class EntityProvenanceBridgeRun:
    as_of: datetime
    observations: tuple[BridgeObservation, ...]
    coverage: BridgeCoverageReport

    def __post_init__(self) -> None:
        _aware(self.as_of, "as_of")

    def to_canonical(self) -> dict[str, CanonicalValue]:
        return {
            "algorithm_version": BRIDGE_ALGORITHM_VERSION,
            "as_of": canonical_timestamp(self.as_of),
            "authority_state": BRIDGE_AUTHORITY_STATE,
            "coverage": self.coverage.to_canonical(),
            "observations": [value.to_canonical() for value in self.observations],
            "schema_version": BRIDGE_SCHEMA_VERSION,
        }

    @property
    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_canonical())


@dataclass(slots=True)
class _MutableCoverage:
    total: int = 0
    supported: int = 0
    degraded: int = 0
    unsupported: int = 0
    native: int = 0
    malformed: int = 0

    def freeze(self) -> SourceBridgeCoverage:
        return SourceBridgeCoverage(
            total_pit_eligible_observations=self.total,
            entity_bridge_supported=self.supported,
            entity_bridge_degraded=self.degraded,
            entity_bridge_unsupported=self.unsupported,
            native_id_signal_count=self.native,
            malformed_identity_field_count=self.malformed,
        )


def _aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


def _lab_value(
    observation: Observation,
    *,
    entity_type: str,
    native_id: str | None,
) -> LabObservation:
    """Emit only frozen bridge evidence into the selected lab model.

    canonical_url is intentionally withheld. V0 authority grants native identity
    coordinates only; allowing URL/name fallback would let the selected hybrid
    recover identity after a malformed/missing native signal.
    """

    return LabObservation(
        source_id=observation.candidate.source_id,
        source_item_key=observation.candidate.source_item_key,
        observed_at=observation.observed_at,
        canonical_url=None,
        entity_type=entity_type,
        entity_name=observation.candidate.source_item_key,
        native_ids=() if native_id is None else (native_id,),
        relations=(),
    )


def _unsupported(observation: Observation, reason: str) -> BridgeObservation:
    return BridgeObservation(
        observation_id=observation.observation_id,
        source_id=observation.candidate.source_id,
        source_item_key=observation.candidate.source_item_key,
        observed_at=observation.observed_at,
        state=EntityBridgeState.UNSUPPORTED,
        entity_type=None,
        native_id=None,
        malformed_identity_fields=0,
        reasons=(reason,),
        lab_observation=None,
    )


def _degraded(
    observation: Observation,
    *,
    entity_type: str,
    reason: str,
    malformed: int = 0,
) -> BridgeObservation:
    return BridgeObservation(
        observation_id=observation.observation_id,
        source_id=observation.candidate.source_id,
        source_item_key=observation.candidate.source_item_key,
        observed_at=observation.observed_at,
        state=EntityBridgeState.DEGRADED,
        entity_type=entity_type,
        native_id=None,
        malformed_identity_fields=malformed,
        reasons=(reason,),
        lab_observation=_lab_value(observation, entity_type=entity_type, native_id=None),
    )


def _supported(
    observation: Observation,
    *,
    entity_type: str,
    native_id: str,
    reason: str,
) -> BridgeObservation:
    return BridgeObservation(
        observation_id=observation.observation_id,
        source_id=observation.candidate.source_id,
        source_item_key=observation.candidate.source_item_key,
        observed_at=observation.observed_at,
        state=EntityBridgeState.SUPPORTED,
        entity_type=entity_type,
        native_id=native_id,
        malformed_identity_fields=0,
        reasons=(reason,),
        lab_observation=_lab_value(observation, entity_type=entity_type, native_id=native_id),
    )


def _bridge_pypi(observation: Observation) -> BridgeObservation:
    payload = observation.candidate.payload
    if observation.candidate.kind is not ObservationKind.ARTIFACT or not isinstance(
        payload, ArtifactPayload
    ):
        return _degraded(observation, entity_type="PACKAGE", reason="ineligible-pypi-shape")
    if payload.artifact_type != "python-package-release":
        return _degraded(observation, entity_type="PACKAGE", reason="ineligible-pypi-artifact-type")
    package_name = unicodedata.normalize("NFC", payload.name).casefold()
    if not package_name:
        return _degraded(
            observation,
            entity_type="PACKAGE",
            reason="empty-pypi-package-name",
            malformed=1,
        )
    return _supported(
        observation,
        entity_type="PACKAGE",
        native_id=f"pypi:{package_name}",
        reason="pypi-normalized-package-name",
    )


def _bridge_cisa(observation: Observation) -> BridgeObservation:
    payload = observation.candidate.payload
    if observation.candidate.kind is not ObservationKind.DOCUMENT or not isinstance(
        payload, DocumentPayload
    ):
        return _degraded(observation, entity_type="VULNERABILITY", reason="ineligible-cisa-shape")
    source_key = observation.candidate.source_item_key
    if _CVE_RE.fullmatch(source_key) is None:
        return _degraded(
            observation,
            entity_type="VULNERABILITY",
            reason="malformed-cisa-source-item-cve",
            malformed=1,
        )
    metadata_cve = payload.source_metadata.get("cve_id")
    if metadata_cve is not None and (
        not isinstance(metadata_cve, str) or metadata_cve != source_key
    ):
        return _degraded(
            observation,
            entity_type="VULNERABILITY",
            reason="cisa-cve-metadata-mismatch",
            malformed=1,
        )
    return _supported(
        observation,
        entity_type="VULNERABILITY",
        native_id=f"cve:{source_key}",
        reason="cisa-source-item-cve",
    )


def _bridge_github(observation: Observation) -> BridgeObservation:
    payload = observation.candidate.payload
    if observation.candidate.kind is not ObservationKind.ARTIFACT or not isinstance(
        payload, ArtifactPayload
    ):
        return _degraded(observation, entity_type="REPOSITORY", reason="ineligible-github-shape")
    if payload.artifact_type != "github-repository":
        return _degraded(
            observation, entity_type="REPOSITORY", reason="ineligible-github-artifact-type"
        )
    repository_id = payload.source_metadata.get("github_repository_id")
    if repository_id is None:
        return _degraded(
            observation, entity_type="REPOSITORY", reason="missing-github-repository-id"
        )
    if isinstance(repository_id, bool) or not isinstance(repository_id, int) or repository_id <= 0:
        return _degraded(
            observation,
            entity_type="REPOSITORY",
            reason="malformed-github-repository-id",
            malformed=1,
        )
    return _supported(
        observation,
        entity_type="REPOSITORY",
        native_id=f"github_repo:{repository_id}",
        reason="github-positive-integer-repository-id",
    )


def _bridge_hf(observation: Observation) -> BridgeObservation:
    payload = observation.candidate.payload
    if observation.candidate.kind is not ObservationKind.ARTIFACT or not isinstance(
        payload, ArtifactPayload
    ):
        return _degraded(observation, entity_type="MODEL", reason="ineligible-hf-shape")
    if payload.artifact_type != "huggingface-model-repo":
        return _degraded(observation, entity_type="MODEL", reason="ineligible-hf-artifact-type")
    source_key = observation.candidate.source_item_key
    if not source_key:
        return _degraded(
            observation, entity_type="MODEL", reason="missing-hf-source-item-key", malformed=1
        )
    return _supported(
        observation,
        entity_type="MODEL",
        native_id=f"hf_model:{source_key}",
        reason="hf-stable-source-item-key",
    )


def bridge_observation(observation: Observation) -> BridgeObservation:
    source_id = observation.candidate.source_id
    if source_id not in BRIDGE_SOURCE_REGISTRY:
        raise ValueError(f"source is outside frozen bridge registry: {source_id}")
    if source_id in UNSUPPORTED_ENTITY_SOURCES:
        return _unsupported(observation, "entity-native-identity-unsupported-for-source-v0")
    if source_id == "pypi.updates":
        return _bridge_pypi(observation)
    if source_id == "cisa.kev":
        return _bridge_cisa(observation)
    if source_id == "github.ml-repos":
        return _bridge_github(observation)
    if source_id == "hf.models":
        return _bridge_hf(observation)
    raise AssertionError("frozen bridge registry partition is incomplete")


def _record_coverage(value: BridgeObservation, target: _MutableCoverage) -> None:
    target.total += 1
    target.malformed += value.malformed_identity_fields
    if value.state is EntityBridgeState.SUPPORTED:
        target.supported += 1
        target.native += 1
    elif value.state is EntityBridgeState.DEGRADED:
        target.degraded += 1
    else:
        target.unsupported += 1


def build_entity_provenance_bridge(
    observations: Sequence[Observation],
    *,
    relations: Sequence[KnownObservationRelation] = (),
    as_of: datetime,
) -> EntityProvenanceBridgeRun:
    """Build a deterministic PIT bridge run from already-canonical evidence."""

    _aware(as_of, "as_of")
    mutable = {source_id: _MutableCoverage() for source_id in BRIDGE_SOURCE_REGISTRY}
    bridged: list[BridgeObservation] = []
    ignored_future_observations = 0

    eligible_observation_ids: set[str] = set()
    for observation in observations:
        source_id = observation.candidate.source_id
        if source_id not in mutable:
            raise ValueError(f"source is outside frozen bridge registry: {source_id}")
        if observation.observed_at > as_of:
            ignored_future_observations += 1
            continue
        value = bridge_observation(observation)
        bridged.append(value)
        eligible_observation_ids.add(observation.observation_id)
        _record_coverage(value, mutable[source_id])

    ignored_future_relations = 0
    ignored_ineligible_relations = 0
    eligible_weak_relations = 0
    for known_relation in relations:
        if known_relation.known_at > as_of:
            ignored_future_relations += 1
            continue
        if known_relation.relation.from_observation_id not in eligible_observation_ids:
            ignored_ineligible_relations += 1
            continue
        # V0 intentionally does not project any canonical relation into a direct
        # derivation lab relation. The canonical vocabulary is weaker than the
        # frozen lab derivation vocabulary, so counting it as weak evidence is
        # the strongest authorized action.
        eligible_weak_relations += 1

    records = tuple(sorted(bridged, key=lambda value: (value.source_id, value.observation_id)))
    coverage = BridgeCoverageReport(
        by_source={source_id: mutable[source_id].freeze() for source_id in BRIDGE_SOURCE_REGISTRY},
        direct_derivation_evidence_count=0,
        eligible_weak_relation_count=eligible_weak_relations,
        ignored_future_observation_count=ignored_future_observations,
        ignored_future_relation_count=ignored_future_relations,
        ignored_ineligible_relation_count=ignored_ineligible_relations,
    )
    return EntityProvenanceBridgeRun(as_of=as_of, observations=records, coverage=coverage)
