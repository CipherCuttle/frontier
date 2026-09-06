"""Offline shadow evaluator for frozen ENTITY_PROVENANCE_SHADOW_EVALUATION_V0."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Final

from .canonical_json import CanonicalValue, canonical_json_bytes
from .digests import sha256_digest
from .entity_provenance_bridge import (
    BRIDGE_ALGORITHM_VERSION,
    BRIDGE_SCHEMA_VERSION,
    BRIDGE_SOURCE_REGISTRY,
    BridgeObservation,
    KnownObservationRelation,
    SourceBridgeCoverage,
    build_entity_provenance_bridge,
)
from .entity_provenance_lab import assess_entity, assess_provenance
from .observation import Observation

PHASE_ID: Final = "ENTITY_PROVENANCE_SHADOW_EVALUATION_V0"
REPORT_SCHEMA_VERSION: Final = "frontier-entity-provenance-shadow-evaluation-report-v0"
FROZEN_SOURCE_REGISTRY_DIGEST: Final = (
    "sha256:c95b29078eb002145b75538b947cfb651cc1d5d7f2921b2347cf68b6065115ee"
)
FROZEN_ENTITY_CANDIDATE: Final = "transparent-entity-hybrid-v0"
FROZEN_PROVENANCE_CANDIDATE: Final = "explicit-reference-v0"
ENTITY_QUALITY_STATUS: Final = "INSUFFICIENT_INDEPENDENT_GROUND_TRUTH"
PROVENANCE_QUALITY_STATUS: Final = "BLOCKED_NO_EXPLICIT_DERIVATION_EVIDENCE"
PROMOTION_STATUS: Final = "UNAVAILABLE"


class ShadowIntegrityStatus(StrEnum):
    COMPLETE_DIAGNOSTIC = "COMPLETE_DIAGNOSTIC"
    INVALID_DRIFT = "INVALID_DRIFT"


@dataclass(frozen=True, slots=True)
class ShadowEvaluationReport:
    as_of: str
    source_registry_digest: str
    entity_candidate: str
    provenance_candidate: str
    integrity_status: ShadowIntegrityStatus
    drift_reasons: tuple[str, ...]
    pit_eligible_observation_count: int
    source_coverage: dict[str, dict[str, int]]
    native_id_signal_count: int
    malformed_identity_field_count: int
    ignored_future_observation_count: int
    ignored_future_observation_by_source: dict[str, int]
    ignored_future_relation_count: int
    eligible_weak_relation_count: int
    entity_decision: str
    provenance_decision: str
    direct_derivation_evidence_count: int
    forbidden_inference_claims: tuple[str, ...] = ()
    entity_quality_status: str = ENTITY_QUALITY_STATUS
    provenance_quality_status: str = PROVENANCE_QUALITY_STATUS
    promotion_status: str = PROMOTION_STATUS
    quality_pass_fail_claim: str | None = None

    @property
    def report_body(self) -> dict[str, CanonicalValue]:
        return {
            "as_of": self.as_of,
            "bridge_algorithm_version": BRIDGE_ALGORITHM_VERSION,
            "bridge_schema_version": BRIDGE_SCHEMA_VERSION,
            "direct_derivation_evidence_count": self.direct_derivation_evidence_count,
            "drift_reasons": list(self.drift_reasons),
            "eligible_weak_relation_count": self.eligible_weak_relation_count,
            "entity_candidate": self.entity_candidate,
            "entity_decision": self.entity_decision,
            "entity_quality_status": self.entity_quality_status,
            "forbidden_inference_claims": list(self.forbidden_inference_claims),
            "ignored_future_observation_by_source": {
                source: self.ignored_future_observation_by_source[source]
                for source in BRIDGE_SOURCE_REGISTRY
            },
            "ignored_future_observation_count": self.ignored_future_observation_count,
            "ignored_future_relation_count": self.ignored_future_relation_count,
            "integrity_status": self.integrity_status.value,
            "malformed_identity_field_count": self.malformed_identity_field_count,
            "native_id_signal_count": self.native_id_signal_count,
            "phase_id": PHASE_ID,
            "pit_eligible_observation_count": self.pit_eligible_observation_count,
            "promotion_status": self.promotion_status,
            "provenance_candidate": self.provenance_candidate,
            "provenance_decision": self.provenance_decision,
            "provenance_quality_status": self.provenance_quality_status,
            "quality_pass_fail_claim": self.quality_pass_fail_claim,
            "schema_version": REPORT_SCHEMA_VERSION,
            "source_coverage": {
                source: self.source_coverage[source] for source in BRIDGE_SOURCE_REGISTRY
            },
            "source_registry_digest": self.source_registry_digest,
        }

    @property
    def report_digest(self) -> str:
        return str(sha256_digest(canonical_json_bytes(self.report_body)))

    def to_canonical(self) -> dict[str, CanonicalValue]:
        return {**self.report_body, "report_digest": self.report_digest}

    @property
    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_canonical())


def _aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


def _report_timestamp(value: datetime) -> str:
    _aware(value, "as_of")
    utc = value.astimezone(UTC)
    if utc.microsecond != 0:
        raise ValueError("shadow evaluation as_of must resolve to a whole second")
    return utc.strftime("%Y-%m-%dT%H:%M:%SZ")


def _coverage_row(value: SourceBridgeCoverage) -> dict[str, int]:
    return {
        "total_pit_eligible_observations": value.total_pit_eligible_observations,
        "entity_bridge_supported": value.entity_bridge_supported,
        "entity_bridge_degraded": value.entity_bridge_degraded,
        "entity_bridge_unsupported": value.entity_bridge_unsupported,
        "native_id_signal_count": value.native_id_signal_count,
        "malformed_identity_field_count": value.malformed_identity_field_count,
        "ignored_future_observation_count": value.ignored_future_observation_count,
    }


def _zero_coverage() -> dict[str, dict[str, int]]:
    return {source: _coverage_row(SourceBridgeCoverage()) for source in BRIDGE_SOURCE_REGISTRY}


def _pair_decisions(
    observations: Sequence[Observation],
    evaluation_pairs: Sequence[tuple[int, int]],
    *,
    bridge_records_by_observation_id: dict[str, BridgeObservation],
    as_of: datetime,
    entity_candidate: str,
    provenance_candidate: str,
) -> tuple[str, str]:
    if not evaluation_pairs:
        return "NO_EVALUATION", "NO_EVALUATION"
    if len(evaluation_pairs) != 1:
        raise ValueError("shadow evaluation v0 freezes at most one evaluation pair per report")

    left_index, right_index = evaluation_pairs[0]
    if left_index == right_index:
        raise ValueError("evaluation pair must contain two distinct observations")
    if not (0 <= left_index < len(observations) and 0 <= right_index < len(observations)):
        raise ValueError("evaluation pair index is outside observation input")

    left_record = bridge_records_by_observation_id.get(observations[left_index].observation_id)
    right_record = bridge_records_by_observation_id.get(observations[right_index].observation_id)
    if left_record is None or right_record is None:
        return "NOT_EVALUABLE", "NOT_EVALUABLE"

    # Unsupported bridge output cannot enter the selected experimental candidates.
    left_lab = left_record.lab_observation
    right_lab = right_record.lab_observation
    if left_lab is None or right_lab is None:
        return "NOT_EVALUABLE", "NOT_EVALUABLE"

    entity = assess_entity(entity_candidate, left_lab, right_lab, as_of=as_of)
    provenance = assess_provenance(provenance_candidate, left_lab, right_lab, as_of=as_of)
    return entity.decision.value, provenance.decision.value


def evaluate_entity_provenance_shadow(
    observations: Sequence[Observation],
    *,
    relations: Sequence[KnownObservationRelation] = (),
    evaluation_pairs: Sequence[tuple[int, int]] = (),
    as_of: datetime,
    source_registry_digest: str,
    entity_candidate: str = FROZEN_ENTITY_CANDIDATE,
    provenance_candidate: str = FROZEN_PROVENANCE_CANDIDATE,
) -> ShadowEvaluationReport:
    """Evaluate one frozen offline shadow input without escalating scientific authority."""

    as_of_text = _report_timestamp(as_of)
    drift_reasons: list[str] = []
    if source_registry_digest != FROZEN_SOURCE_REGISTRY_DIGEST:
        drift_reasons.append("source-registry-digest-mismatch")
    if entity_candidate != FROZEN_ENTITY_CANDIDATE:
        drift_reasons.append("entity-candidate-mismatch")
    if provenance_candidate != FROZEN_PROVENANCE_CANDIDATE:
        drift_reasons.append("provenance-candidate-mismatch")

    if drift_reasons:
        zero = _zero_coverage()
        return ShadowEvaluationReport(
            as_of=as_of_text,
            source_registry_digest=source_registry_digest,
            entity_candidate=entity_candidate,
            provenance_candidate=provenance_candidate,
            integrity_status=ShadowIntegrityStatus.INVALID_DRIFT,
            drift_reasons=tuple(drift_reasons),
            pit_eligible_observation_count=0,
            source_coverage=zero,
            native_id_signal_count=0,
            malformed_identity_field_count=0,
            ignored_future_observation_count=0,
            ignored_future_observation_by_source={source: 0 for source in BRIDGE_SOURCE_REGISTRY},
            ignored_future_relation_count=0,
            eligible_weak_relation_count=0,
            entity_decision="NO_EVALUATION",
            provenance_decision="NO_EVALUATION",
            direct_derivation_evidence_count=0,
        )

    bridge = build_entity_provenance_bridge(observations, relations=relations, as_of=as_of)
    source_coverage = {
        source: _coverage_row(bridge.coverage.by_source[source])
        for source in BRIDGE_SOURCE_REGISTRY
    }
    entity_decision, provenance_decision = _pair_decisions(
        observations,
        evaluation_pairs,
        bridge_records_by_observation_id={
            record.observation_id: record for record in bridge.observations
        },
        as_of=as_of,
        entity_candidate=entity_candidate,
        provenance_candidate=provenance_candidate,
    )

    return ShadowEvaluationReport(
        as_of=as_of_text,
        source_registry_digest=source_registry_digest,
        entity_candidate=entity_candidate,
        provenance_candidate=provenance_candidate,
        integrity_status=ShadowIntegrityStatus.COMPLETE_DIAGNOSTIC,
        drift_reasons=(),
        pit_eligible_observation_count=sum(
            row["total_pit_eligible_observations"] for row in source_coverage.values()
        ),
        source_coverage=source_coverage,
        native_id_signal_count=sum(
            row["native_id_signal_count"] for row in source_coverage.values()
        ),
        malformed_identity_field_count=sum(
            row["malformed_identity_field_count"] for row in source_coverage.values()
        ),
        ignored_future_observation_count=bridge.coverage.ignored_future_observation_count,
        ignored_future_observation_by_source={
            source: source_coverage[source]["ignored_future_observation_count"]
            for source in BRIDGE_SOURCE_REGISTRY
        },
        ignored_future_relation_count=bridge.coverage.ignored_future_relation_count,
        eligible_weak_relation_count=bridge.coverage.eligible_weak_relation_count,
        entity_decision=entity_decision,
        provenance_decision=provenance_decision,
        direct_derivation_evidence_count=bridge.coverage.direct_derivation_evidence_count,
    )
