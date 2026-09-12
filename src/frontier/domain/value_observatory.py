from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from .canonical_json import CanonicalValue, canonical_json_bytes, canonical_timestamp
from .digests import Digest, sha256_digest, sha256_hex
from .health import HealthValue

VALUE_OBSERVATORY_OPPORTUNITY_SCHEMA_VERSION = "frontier-value-observatory-opportunity-v0"
VALUE_OBSERVATORY_CAPTURE_SCHEMA_VERSION = "frontier-value-observatory-capture-v0"
VALUE_OBSERVATORY_OUTCOME_SCHEMA_VERSION = "frontier-value-observatory-outcome-v0"
VALUE_OBSERVATORY_AUTHORITY_STATE = "DIAGNOSTIC_OBSERVATORY"
VALUE_OBSERVATORY_OPPORTUNITY_ID_PREFIX = "valueopportunity_"
VALUE_OBSERVATORY_CAPTURE_ID_PREFIX = "valuecapture_"
VALUE_OBSERVATORY_OUTCOME_ID_PREFIX = "valueoutcome_"

_HEALTH_ID_RE = re.compile(r"^health_[0-9a-f]{64}$")
_OPPORTUNITY_ID_RE = re.compile(r"^valueopportunity_[0-9a-f]{64}$")


def _require_aware(value: datetime, label: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")


def _require_nonempty(value: str, label: str) -> None:
    if not value.strip():
        raise ValueError(f"{label} must be non-empty")


def _canonical_health_bindings(
    bindings: tuple[SourceHealthBinding, ...],
) -> list[CanonicalValue]:
    return [
        item.to_canonical()
        for item in sorted(
            bindings,
            key=lambda item: (item.source_id, item.as_of, item.health_observation_id),
        )
    ]


class ObservatoryArm(StrEnum):
    FRONTIER_NAIVE_CONTROL = "FRONTIER_NAIVE_CONTROL"
    FRONTIER_EXISTING_EXPERIMENTAL = "FRONTIER_EXISTING_EXPERIMENTAL"
    ORDINARY_AGGREGATION = "ORDINARY_AGGREGATION"
    WEB_LLM_BENCHMARK = "WEB_LLM_BENCHMARK"


class CaptureStatus(StrEnum):
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"


class OutcomeState(StrEnum):
    POSITIVE = "POSITIVE"
    NEGATIVE_WITH_ADEQUATE_COVERAGE = "NEGATIVE_WITH_ADEQUATE_COVERAGE"
    UNRESOLVED_COVERAGE = "UNRESOLVED_COVERAGE"


class ExposureState(StrEnum):
    SHADOW_UNEXPOSED = "SHADOW_UNEXPOSED"
    PUBLICLY_EXPOSED = "PUBLICLY_EXPOSED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class BenchmarkExecutorIdentity:
    executor_id: str
    executor_version: str
    configuration_digest: Digest
    provider: str | None = None
    model: str | None = None
    prompt_digest: Digest | None = None

    def __post_init__(self) -> None:
        _require_nonempty(self.executor_id, "executor_id")
        _require_nonempty(self.executor_version, "executor_version")
        if self.provider is not None:
            _require_nonempty(self.provider, "provider")
        if self.model is not None:
            _require_nonempty(self.model, "model")

    def to_canonical(self) -> dict[str, CanonicalValue]:
        return {
            "configuration_digest": str(self.configuration_digest),
            "executor_id": self.executor_id,
            "executor_version": self.executor_version,
            "model": self.model,
            "prompt_digest": None if self.prompt_digest is None else str(self.prompt_digest),
            "provider": self.provider,
        }


@dataclass(frozen=True, slots=True)
class SourceHealthBinding:
    health_observation_id: str
    source_id: str
    as_of: datetime
    transport: HealthValue
    freshness: HealthValue
    completeness: HealthValue
    schema: HealthValue

    def __post_init__(self) -> None:
        if not _HEALTH_ID_RE.fullmatch(self.health_observation_id):
            raise ValueError("source health binding requires a canonical health observation id")
        _require_nonempty(self.source_id, "source_id")
        _require_aware(self.as_of, "source health as_of")

    def to_canonical(self) -> dict[str, CanonicalValue]:
        return {
            "as_of": canonical_timestamp(self.as_of),
            "completeness": self.completeness.value,
            "freshness": self.freshness.value,
            "health_observation_id": self.health_observation_id,
            "schema": self.schema.value,
            "source_id": self.source_id,
            "transport": self.transport.value,
        }


@dataclass(frozen=True, slots=True)
class ValueObservatoryOpportunity:
    domain: str
    anchor_at: datetime
    recorded_at: datetime
    opportunity_protocol_digest: Digest
    anchor_payload_digest: Digest
    anchor_refs: tuple[str, ...]
    canonical_urls: tuple[str, ...]
    source_health_bindings: tuple[SourceHealthBinding, ...]
    schema_version: str = VALUE_OBSERVATORY_OPPORTUNITY_SCHEMA_VERSION
    authority_state: str = VALUE_OBSERVATORY_AUTHORITY_STATE

    def __post_init__(self) -> None:
        _require_nonempty(self.domain, "opportunity domain")
        _require_aware(self.anchor_at, "opportunity anchor_at")
        _require_aware(self.recorded_at, "opportunity recorded_at")
        if self.recorded_at < self.anchor_at:
            raise ValueError("opportunity cannot be recorded before its anchor")
        if self.schema_version != VALUE_OBSERVATORY_OPPORTUNITY_SCHEMA_VERSION:
            raise ValueError("opportunity schema version mismatch")
        if self.authority_state != VALUE_OBSERVATORY_AUTHORITY_STATE:
            raise ValueError("opportunity authority state mismatch")
        if not self.anchor_refs:
            raise ValueError("opportunity requires at least one anchor reference")
        if len(set(self.anchor_refs)) != len(self.anchor_refs):
            raise ValueError("opportunity anchor references contain duplicates")
        if any(not value.strip() for value in self.anchor_refs):
            raise ValueError("opportunity anchor references must be non-empty")
        if len(set(self.canonical_urls)) != len(self.canonical_urls):
            raise ValueError("opportunity canonical urls contain duplicates")
        if any(not value.strip() for value in self.canonical_urls):
            raise ValueError("opportunity canonical urls must be non-empty strings")
        if not self.source_health_bindings:
            raise ValueError("opportunity requires explicit source health bindings")
        if len({item.source_id for item in self.source_health_bindings}) != len(
            self.source_health_bindings
        ):
            raise ValueError("opportunity source health bindings contain duplicate sources")
        if any(item.as_of > self.anchor_at for item in self.source_health_bindings):
            raise ValueError("opportunity source health binding is after the anchor horizon")

    @property
    def opportunity_digest(self) -> Digest:
        return sha256_digest(canonical_json_bytes(self.to_canonical()))

    @property
    def opportunity_id(self) -> str:
        return VALUE_OBSERVATORY_OPPORTUNITY_ID_PREFIX + sha256_hex(
            canonical_json_bytes(self.to_canonical())
        )

    def to_canonical(self) -> dict[str, CanonicalValue]:
        return {
            "anchor_at": canonical_timestamp(self.anchor_at),
            "anchor_payload_digest": str(self.anchor_payload_digest),
            "anchor_refs": sorted(self.anchor_refs),
            "authority_state": self.authority_state,
            "canonical_urls": sorted(self.canonical_urls),
            "domain": self.domain,
            "opportunity_protocol_digest": str(self.opportunity_protocol_digest),
            "recorded_at": canonical_timestamp(self.recorded_at),
            "schema_version": self.schema_version,
            "source_health_bindings": _canonical_health_bindings(self.source_health_bindings),
        }


@dataclass(frozen=True, slots=True)
class CaptureItem:
    position: int
    item_key: str
    raw_item_digest: Digest
    title: str | None = None
    canonical_urls: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.position <= 0:
            raise ValueError("capture item position must be positive")
        _require_nonempty(self.item_key, "item_key")
        if self.title is not None:
            _require_nonempty(self.title, "title")
        if len(set(self.canonical_urls)) != len(self.canonical_urls):
            raise ValueError("capture item canonical urls contain duplicates")
        if len(set(self.evidence_refs)) != len(self.evidence_refs):
            raise ValueError("capture item evidence refs contain duplicates")
        if any(not value.strip() for value in self.canonical_urls):
            raise ValueError("capture item canonical urls must be non-empty strings")
        if any(not value.strip() for value in self.evidence_refs):
            raise ValueError("capture item evidence refs must be non-empty strings")

    def to_canonical(self) -> dict[str, CanonicalValue]:
        return {
            "canonical_urls": sorted(self.canonical_urls),
            "evidence_refs": sorted(self.evidence_refs),
            "item_key": self.item_key,
            "position": self.position,
            "raw_item_digest": str(self.raw_item_digest),
            "title": self.title,
        }


@dataclass(frozen=True, slots=True)
class ValueObservatoryCapture:
    arm: ObservatoryArm
    captured_at: datetime
    knowledge_horizon: datetime
    selection_window_start: datetime
    selection_window_end: datetime
    alert_budget: int
    domain_scope: tuple[str, ...]
    executor: BenchmarkExecutorIdentity
    protocol_digest: Digest
    input_digest: Digest
    source_health_bindings: tuple[SourceHealthBinding, ...]
    items: tuple[CaptureItem, ...]
    status: CaptureStatus
    raw_response_digest: Digest | None = None
    failure_reason: str | None = None
    schema_version: str = VALUE_OBSERVATORY_CAPTURE_SCHEMA_VERSION
    authority_state: str = VALUE_OBSERVATORY_AUTHORITY_STATE

    def __post_init__(self) -> None:
        _require_aware(self.captured_at, "capture captured_at")
        _require_aware(self.knowledge_horizon, "capture knowledge_horizon")
        _require_aware(self.selection_window_start, "capture selection_window_start")
        _require_aware(self.selection_window_end, "capture selection_window_end")
        if self.knowledge_horizon > self.captured_at:
            raise ValueError("capture knowledge horizon cannot be after captured_at")
        if self.selection_window_start > self.selection_window_end:
            raise ValueError("capture selection window start cannot be after end")
        if self.selection_window_end > self.knowledge_horizon:
            raise ValueError("capture selection window cannot extend beyond knowledge horizon")
        if self.alert_budget <= 0:
            raise ValueError("capture alert budget must be positive")
        if self.schema_version != VALUE_OBSERVATORY_CAPTURE_SCHEMA_VERSION:
            raise ValueError("capture schema version mismatch")
        if self.authority_state != VALUE_OBSERVATORY_AUTHORITY_STATE:
            raise ValueError("capture authority state mismatch")
        if not self.domain_scope:
            raise ValueError("capture requires at least one domain scope")
        if len(set(self.domain_scope)) != len(self.domain_scope):
            raise ValueError("capture domain scope contains duplicates")
        if any(not value.strip() for value in self.domain_scope):
            raise ValueError("capture domain scope values must be non-empty")
        if len({item.item_key for item in self.items}) != len(self.items):
            raise ValueError("capture items contain duplicate item keys")
        if len({item.position for item in self.items}) != len(self.items):
            raise ValueError("capture items contain duplicate positions")
        expected_positions = tuple(range(1, len(self.items) + 1))
        if tuple(item.position for item in self.items) != expected_positions:
            raise ValueError("capture item positions must be contiguous and ordered")
        if len(self.items) > self.alert_budget:
            raise ValueError("capture item count exceeds the frozen alert budget")
        if not self.source_health_bindings:
            raise ValueError("capture requires explicit source health bindings")
        if len({item.source_id for item in self.source_health_bindings}) != len(
            self.source_health_bindings
        ):
            raise ValueError("capture source health bindings contain duplicate sources")
        if any(item.as_of > self.knowledge_horizon for item in self.source_health_bindings):
            raise ValueError("capture source health binding is after the knowledge horizon")
        if self.status is CaptureStatus.COMPLETE and self.raw_response_digest is None:
            raise ValueError("complete capture requires raw_response_digest")
        if self.status is CaptureStatus.COMPLETE and self.failure_reason is not None:
            raise ValueError("complete capture cannot carry a failure reason")
        if self.status is CaptureStatus.FAILED and self.items:
            raise ValueError("failed capture cannot carry surfaced items")
        if self.status is CaptureStatus.FAILED and (
            self.failure_reason is None or not self.failure_reason.strip()
        ):
            raise ValueError("failed capture requires an explicit failure reason")

    @property
    def capture_digest(self) -> Digest:
        return sha256_digest(canonical_json_bytes(self.to_canonical()))

    @property
    def capture_id(self) -> str:
        return VALUE_OBSERVATORY_CAPTURE_ID_PREFIX + sha256_hex(
            canonical_json_bytes(self.to_canonical())
        )

    def to_canonical(self) -> dict[str, CanonicalValue]:
        item_values: list[CanonicalValue] = [item.to_canonical() for item in self.items]
        return {
            "alert_budget": self.alert_budget,
            "arm": self.arm.value,
            "authority_state": self.authority_state,
            "captured_at": canonical_timestamp(self.captured_at),
            "domain_scope": sorted(self.domain_scope),
            "executor": self.executor.to_canonical(),
            "failure_reason": self.failure_reason,
            "input_digest": str(self.input_digest),
            "items": item_values,
            "knowledge_horizon": canonical_timestamp(self.knowledge_horizon),
            "protocol_digest": str(self.protocol_digest),
            "raw_response_digest": (
                None if self.raw_response_digest is None else str(self.raw_response_digest)
            ),
            "schema_version": self.schema_version,
            "selection_window_end": canonical_timestamp(self.selection_window_end),
            "selection_window_start": canonical_timestamp(self.selection_window_start),
            "source_health_bindings": _canonical_health_bindings(self.source_health_bindings),
            "status": self.status.value,
        }


@dataclass(frozen=True, slots=True)
class OutcomeEvidenceRef:
    evidence_key: str
    source_id: str
    role: str
    observed_at: datetime
    payload_digest: Digest

    def __post_init__(self) -> None:
        _require_nonempty(self.evidence_key, "outcome evidence_key")
        _require_nonempty(self.source_id, "outcome source_id")
        _require_nonempty(self.role, "outcome role")
        _require_aware(self.observed_at, "outcome evidence observed_at")

    def to_canonical(self) -> dict[str, CanonicalValue]:
        return {
            "evidence_key": self.evidence_key,
            "observed_at": canonical_timestamp(self.observed_at),
            "payload_digest": str(self.payload_digest),
            "role": self.role,
            "source_id": self.source_id,
        }


@dataclass(frozen=True, slots=True)
class ValueObservatoryOutcome:
    opportunity_id: str
    opportunity_anchor_at: datetime
    opportunity_recorded_at: datetime
    outcome_definition_id: str
    outcome_protocol_digest: Digest
    horizon_seconds: int
    resolution_at: datetime
    evaluated_at: datetime
    state: OutcomeState
    exposure_state: ExposureState
    evidence: tuple[OutcomeEvidenceRef, ...]
    coverage_bindings: tuple[SourceHealthBinding, ...]
    exposure_at: datetime | None = None
    coverage_reason: str | None = None
    schema_version: str = VALUE_OBSERVATORY_OUTCOME_SCHEMA_VERSION
    authority_state: str = VALUE_OBSERVATORY_AUTHORITY_STATE

    def __post_init__(self) -> None:
        if not _OPPORTUNITY_ID_RE.fullmatch(self.opportunity_id):
            raise ValueError("outcome requires a value observatory opportunity id")
        _require_aware(self.opportunity_anchor_at, "outcome opportunity_anchor_at")
        _require_aware(self.opportunity_recorded_at, "outcome opportunity_recorded_at")
        _require_nonempty(self.outcome_definition_id, "outcome_definition_id")
        _require_aware(self.resolution_at, "outcome resolution_at")
        _require_aware(self.evaluated_at, "outcome evaluated_at")
        if self.opportunity_recorded_at < self.opportunity_anchor_at:
            raise ValueError("outcome opportunity cannot be recorded before its anchor")
        if self.horizon_seconds <= 0:
            raise ValueError("outcome horizon_seconds must be positive")
        expected_resolution = self.opportunity_anchor_at + timedelta(seconds=self.horizon_seconds)
        if self.resolution_at != expected_resolution:
            raise ValueError(
                "outcome resolution_at must equal opportunity_anchor_at + horizon_seconds"
            )
        if self.opportunity_recorded_at >= self.resolution_at:
            raise ValueError("outcome opportunity must be registered before its resolution horizon")
        if self.evaluated_at < self.resolution_at:
            raise ValueError("outcome cannot be evaluated before its resolution horizon")
        if self.schema_version != VALUE_OBSERVATORY_OUTCOME_SCHEMA_VERSION:
            raise ValueError("outcome schema version mismatch")
        if self.authority_state != VALUE_OBSERVATORY_AUTHORITY_STATE:
            raise ValueError("outcome authority state mismatch")
        if len({item.evidence_key for item in self.evidence}) != len(self.evidence):
            raise ValueError("outcome evidence contains duplicate evidence keys")
        if any(
            item.observed_at <= self.opportunity_recorded_at
            or item.observed_at > self.resolution_at
            for item in self.evidence
        ):
            raise ValueError("outcome evidence must be future-only and within the outcome horizon")
        if len({item.health_observation_id for item in self.coverage_bindings}) != len(
            self.coverage_bindings
        ):
            raise ValueError("outcome coverage bindings contain duplicate health observations")
        if len({(item.source_id, item.as_of) for item in self.coverage_bindings}) != len(
            self.coverage_bindings
        ):
            raise ValueError("outcome coverage bindings contain duplicate source boundaries")
        if any(
            item.as_of < self.opportunity_recorded_at or item.as_of > self.resolution_at
            for item in self.coverage_bindings
        ):
            raise ValueError("outcome coverage binding is outside the prospective outcome window")
        if self.state is OutcomeState.POSITIVE and not self.evidence:
            raise ValueError("positive outcome requires supporting future evidence")
        if (
            self.state is OutcomeState.NEGATIVE_WITH_ADEQUATE_COVERAGE
            and not self.coverage_bindings
        ):
            raise ValueError("negative outcome requires explicit adequate-coverage bindings")
        if (
            self.state is OutcomeState.NEGATIVE_WITH_ADEQUATE_COVERAGE
            and self.coverage_reason is not None
        ):
            raise ValueError("negative outcome cannot carry an unresolved coverage reason")
        if self.state is OutcomeState.UNRESOLVED_COVERAGE and (
            self.coverage_reason is None or not self.coverage_reason.strip()
        ):
            raise ValueError("unresolved outcome requires an explicit coverage reason")
        if (
            self.exposure_state is ExposureState.SHADOW_UNEXPOSED
            and self.exposure_at is not None
        ):
            raise ValueError("shadow-unexposed outcome cannot carry exposure_at")
        if self.exposure_state is ExposureState.PUBLICLY_EXPOSED and self.exposure_at is None:
            raise ValueError("publicly exposed outcome requires exposure_at")
        if self.exposure_state is ExposureState.PUBLICLY_EXPOSED and self.exposure_at is not None:
            _require_aware(self.exposure_at, "outcome exposure_at")
            if self.exposure_at < self.opportunity_recorded_at:
                raise ValueError("outcome exposure_at cannot predate opportunity registration")
            if self.exposure_at > self.evaluated_at:
                raise ValueError("outcome exposure_at cannot be after evaluated_at")
        if self.exposure_state is ExposureState.UNKNOWN and self.exposure_at is not None:
            raise ValueError("unknown exposure state cannot carry exposure_at")

    @property
    def outcome_digest(self) -> Digest:
        return sha256_digest(canonical_json_bytes(self.to_canonical()))

    @property
    def outcome_id(self) -> str:
        return VALUE_OBSERVATORY_OUTCOME_ID_PREFIX + sha256_hex(
            canonical_json_bytes(self.to_canonical())
        )

    def to_canonical(self) -> dict[str, CanonicalValue]:
        evidence_values: list[CanonicalValue] = [
            item.to_canonical()
            for item in sorted(
                self.evidence,
                key=lambda item: (
                    item.observed_at,
                    item.source_id,
                    item.role,
                    item.evidence_key,
                ),
            )
        ]
        return {
            "authority_state": self.authority_state,
            "coverage_bindings": _canonical_health_bindings(self.coverage_bindings),
            "coverage_reason": self.coverage_reason,
            "evaluated_at": canonical_timestamp(self.evaluated_at),
            "evidence": evidence_values,
            "exposure_at": (
                None if self.exposure_at is None else canonical_timestamp(self.exposure_at)
            ),
            "exposure_state": self.exposure_state.value,
            "horizon_seconds": self.horizon_seconds,
            "opportunity_anchor_at": canonical_timestamp(self.opportunity_anchor_at),
            "opportunity_id": self.opportunity_id,
            "opportunity_recorded_at": canonical_timestamp(self.opportunity_recorded_at),
            "outcome_definition_id": self.outcome_definition_id,
            "outcome_protocol_digest": str(self.outcome_protocol_digest),
            "resolution_at": canonical_timestamp(self.resolution_at),
            "schema_version": self.schema_version,
            "state": self.state.value,
        }


def require_outcome_opportunity_binding(
    opportunity: ValueObservatoryOpportunity,
    outcome: ValueObservatoryOutcome,
) -> None:
    if outcome.opportunity_id != opportunity.opportunity_id:
        raise ValueError("outcome opportunity id does not match opportunity artifact")
    if outcome.opportunity_anchor_at != opportunity.anchor_at:
        raise ValueError("outcome anchor does not match opportunity artifact")
    if outcome.opportunity_recorded_at != opportunity.recorded_at:
        raise ValueError("outcome registration time does not match opportunity artifact")


__all__ = [
    "VALUE_OBSERVATORY_AUTHORITY_STATE",
    "VALUE_OBSERVATORY_CAPTURE_SCHEMA_VERSION",
    "VALUE_OBSERVATORY_OPPORTUNITY_SCHEMA_VERSION",
    "VALUE_OBSERVATORY_OUTCOME_SCHEMA_VERSION",
    "BenchmarkExecutorIdentity",
    "CaptureItem",
    "CaptureStatus",
    "ExposureState",
    "ObservatoryArm",
    "OutcomeEvidenceRef",
    "OutcomeState",
    "SourceHealthBinding",
    "ValueObservatoryCapture",
    "ValueObservatoryOpportunity",
    "ValueObservatoryOutcome",
    "require_outcome_opportunity_binding",
]
