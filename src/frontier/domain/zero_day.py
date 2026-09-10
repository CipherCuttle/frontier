from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from .advanced_intelligence import (
    PEF_ALGORITHM_VERSION,
    PEF_AUTHORITY_STATE,
    PEF_RANKING_POLICY_VERSION,
    PEF_RECEIPT_SCHEMA_VERSION,
    PEF_SCHEMA_VERSION,
    PefArtifactStatus,
    ShadowExperimentRun,
    ShadowRunStatus,
)
from .canonical_json import CanonicalValue, canonical_json_bytes, canonical_timestamp
from .digests import Digest, sha256_digest, sha256_hex
from .health import HealthValue
from .intelligence import BaselineObservationInput
from .pef_v1 import (
    PEF_V1_CANDIDATE_ID,
    PEF_V1_CONFIGURATION_DIGEST,
    PEF_V1_EXPERIMENT_ID,
    PEF_V1_PROJECTION_NAME,
    PEF_V1_PROJECTION_VERSION,
    PefV1Artifact,
)
from .receipt import ProjectionReceipt, ProjectionStatus

ZERO_DAY_SCHEMA_VERSION = "frontier-zero-day-seal-v0"
ZERO_DAY_GRADE_SCHEMA_VERSION = "frontier-zero-day-grade-v0"
ZERO_DAY_SELECTION_RULE_VERSION = "pef-v1-top-unnoticed-primary-v0"
ZERO_DAY_AUTHORITY_STATE = "DIAGNOSTIC_ONLY"
ZERO_DAY_RUN_CLASS = "CONFIRMATORY"
ZERO_DAY_COHORT_SIZE = 5
ZERO_DAY_MAX_SEAL_DELAY_SECONDS = 1_800
ZERO_DAY_SEAL_HOURS_UTC = frozenset({0, 6, 12, 18})
ZERO_DAY_FOLLOW_ON_ROLES = frozenset({"ATTENTION", "DISCOVERY"})
ZERO_DAY_GRADE_HORIZONS_SECONDS = (21_600, 86_400, 259_200, 604_800)


def _require_aware(value: datetime, label: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")


def require_zero_day_boundary(as_of: datetime) -> None:
    _require_aware(as_of, "ZERO-DAY as_of")
    utc = as_of.astimezone(UTC)
    if (
        utc.hour not in ZERO_DAY_SEAL_HOURS_UTC
        or utc.minute != 0
        or utc.second != 0
        or utc.microsecond != 0
    ):
        raise ValueError("ZERO-DAY seals require an exact 6-hour UTC boundary")


@dataclass(frozen=True, slots=True)
class ZeroDayPefPersistenceBinding:
    """Trusted persistence metadata loaded from the append-only PEF_V1 store.

    The later read-only adapter is responsible for constructing this object
    directly from the persisted artifact/run/receipt rows. The pure domain
    builder verifies the row identities, exact input digest, and persistence
    timestamps before it will create a live seal.
    """

    candidate_receipt: ProjectionReceipt
    artifact_receipt_id: str
    artifact_persisted_at: datetime
    candidate_receipt_persisted_at: datetime
    run_persisted_at: datetime

    def __post_init__(self) -> None:
        if self.artifact_receipt_id != self.candidate_receipt.receipt_id:
            raise ValueError("ZERO-DAY persisted artifact receipt binding mismatch")
        _require_aware(self.artifact_persisted_at, "artifact_persisted_at")
        _require_aware(
            self.candidate_receipt_persisted_at,
            "candidate_receipt_persisted_at",
        )
        _require_aware(self.run_persisted_at, "run_persisted_at")


@dataclass(frozen=True, slots=True)
class ZeroDayCandidate:
    position: int
    episode_id: str
    observation_ids: tuple[str, ...]
    candidate_rank: int
    control_rank: int
    rank_advantage: int
    prospective_last_observed_at: datetime
    prospective_age_seconds: int

    def __post_init__(self) -> None:
        if self.position <= 0:
            raise ValueError("ZERO-DAY candidate position must be positive")
        if not self.episode_id.startswith("episode_"):
            raise ValueError("ZERO-DAY candidate requires an episode id")
        if not self.observation_ids:
            raise ValueError("ZERO-DAY candidate requires sealed observation ids")
        if self.candidate_rank <= 0 or self.control_rank <= 0:
            raise ValueError("ZERO-DAY ranks must be positive")
        if self.rank_advantage != self.control_rank - self.candidate_rank:
            raise ValueError("ZERO-DAY rank advantage does not match paired ranks")
        if self.rank_advantage <= 0:
            raise ValueError("ZERO-DAY candidate must outrank the naive control")
        _require_aware(self.prospective_last_observed_at, "prospective_last_observed_at")
        if self.prospective_age_seconds < 0:
            raise ValueError("ZERO-DAY prospective age cannot be negative")

    def to_canonical(self) -> dict[str, CanonicalValue]:
        return {
            "candidate_rank": self.candidate_rank,
            "control_rank": self.control_rank,
            "episode_id": self.episode_id,
            "observation_ids": list(self.observation_ids),
            "position": self.position,
            "prospective_age_seconds": self.prospective_age_seconds,
            "prospective_last_observed_at": canonical_timestamp(self.prospective_last_observed_at),
            "rank_advantage": self.rank_advantage,
        }


@dataclass(frozen=True, slots=True)
class ZeroDaySeal:
    as_of: datetime
    sealed_at: datetime
    run_id: str
    run_digest: Digest
    run_persisted_at: datetime
    candidate_artifact_id: str
    candidate_output_digest: Digest
    candidate_artifact_persisted_at: datetime
    candidate_receipt_id: str
    candidate_input_digest: Digest
    candidate_receipt_persisted_at: datetime
    candidate_freeze_receipt_id: str
    source_registry_version: Digest
    candidates: tuple[ZeroDayCandidate, ...]
    schema_version: str = ZERO_DAY_SCHEMA_VERSION
    selection_rule_version: str = ZERO_DAY_SELECTION_RULE_VERSION
    authority_state: str = ZERO_DAY_AUTHORITY_STATE

    def __post_init__(self) -> None:
        require_zero_day_boundary(self.as_of)
        _require_aware(self.sealed_at, "ZERO-DAY sealed_at")
        _require_aware(self.run_persisted_at, "run_persisted_at")
        _require_aware(self.candidate_artifact_persisted_at, "candidate_artifact_persisted_at")
        _require_aware(self.candidate_receipt_persisted_at, "candidate_receipt_persisted_at")
        if self.sealed_at < self.as_of:
            raise ValueError("ZERO-DAY cannot be sealed before its source boundary")
        if self.sealed_at > self.as_of + timedelta(seconds=ZERO_DAY_MAX_SEAL_DELAY_SECONDS):
            raise ValueError("ZERO-DAY seal missed its 30-minute live sealing window")
        if any(
            persisted_at > self.sealed_at
            for persisted_at in (
                self.run_persisted_at,
                self.candidate_artifact_persisted_at,
                self.candidate_receipt_persisted_at,
            )
        ):
            raise ValueError("ZERO-DAY source evidence was not persisted by sealed_at")
        if not self.run_id.startswith("shadowrun_"):
            raise ValueError("ZERO-DAY seal requires a shadow run id")
        if not self.candidate_artifact_id.startswith("artifact_"):
            raise ValueError("ZERO-DAY seal requires a candidate artifact id")
        if not self.candidate_receipt_id.startswith("receipt_"):
            raise ValueError("ZERO-DAY seal requires a candidate receipt binding")
        if not self.candidate_freeze_receipt_id.startswith("freezereceipt_"):
            raise ValueError("ZERO-DAY seal requires a bound candidate freeze receipt")
        if len(self.candidates) > ZERO_DAY_COHORT_SIZE:
            raise ValueError("ZERO-DAY cohort exceeds the frozen size")
        expected_positions = tuple(range(1, len(self.candidates) + 1))
        if tuple(item.position for item in self.candidates) != expected_positions:
            raise ValueError("ZERO-DAY cohort positions must be contiguous and ordered")
        if len({item.episode_id for item in self.candidates}) != len(self.candidates):
            raise ValueError("ZERO-DAY cohort contains duplicate episodes")

    @property
    def seal_id(self) -> str:
        return "zeroday_" + sha256_hex(canonical_json_bytes(self.to_canonical()))

    @property
    def seal_digest(self) -> Digest:
        return sha256_digest(canonical_json_bytes(self.to_canonical()))

    def to_canonical(self) -> dict[str, CanonicalValue]:
        candidate_values: list[CanonicalValue] = [item.to_canonical() for item in self.candidates]
        return {
            "as_of": canonical_timestamp(self.as_of),
            "authority_state": self.authority_state,
            "candidate_artifact_id": self.candidate_artifact_id,
            "candidate_artifact_persisted_at": canonical_timestamp(
                self.candidate_artifact_persisted_at
            ),
            "candidate_freeze_receipt_id": self.candidate_freeze_receipt_id,
            "candidate_input_digest": str(self.candidate_input_digest),
            "candidate_output_digest": str(self.candidate_output_digest),
            "candidate_receipt_id": self.candidate_receipt_id,
            "candidate_receipt_persisted_at": canonical_timestamp(
                self.candidate_receipt_persisted_at
            ),
            "candidates": candidate_values,
            "cohort_size_limit": ZERO_DAY_COHORT_SIZE,
            "run_digest": str(self.run_digest),
            "run_id": self.run_id,
            "run_persisted_at": canonical_timestamp(self.run_persisted_at),
            "schema_version": self.schema_version,
            "sealed_at": canonical_timestamp(self.sealed_at),
            "selection_rule_version": self.selection_rule_version,
            "source_registry_version": str(self.source_registry_version),
        }


def _candidate_input_digest(
    observations: tuple[BaselineObservationInput, ...],
    *,
    control_snapshot_id: str,
) -> Digest:
    observation_values: list[CanonicalValue] = [
        item.to_canonical() for item in sorted(observations, key=lambda item: item.observation_id)
    ]
    material: dict[str, CanonicalValue] = {
        "control_snapshot_id": control_snapshot_id,
        "observations": observation_values,
    }
    return sha256_digest(canonical_json_bytes(material))


def _require_candidate_receipt(
    artifact: PefV1Artifact,
    observations: tuple[BaselineObservationInput, ...],
    binding: ZeroDayPefPersistenceBinding,
) -> None:
    receipt = binding.candidate_receipt
    if receipt.status is not ProjectionStatus.COMPLETE:
        raise ValueError("ZERO-DAY requires a COMPLETE persisted PEF_V1 candidate receipt")
    if receipt.receipt_schema_version != PEF_RECEIPT_SCHEMA_VERSION:
        raise ValueError("ZERO-DAY candidate receipt schema identity mismatch")
    if receipt.projection_name != PEF_V1_PROJECTION_NAME:
        raise ValueError("ZERO-DAY candidate receipt projection identity mismatch")
    if receipt.projection_version != PEF_V1_PROJECTION_VERSION:
        raise ValueError("ZERO-DAY candidate receipt version identity mismatch")
    if receipt.schema_version != PEF_SCHEMA_VERSION:
        raise ValueError("ZERO-DAY candidate receipt artifact schema mismatch")
    if receipt.algorithm_version != PEF_ALGORITHM_VERSION:
        raise ValueError("ZERO-DAY candidate receipt algorithm identity mismatch")
    if receipt.ranking_policy_version != PEF_RANKING_POLICY_VERSION:
        raise ValueError("ZERO-DAY candidate receipt ranking identity mismatch")
    if receipt.configuration_digest != PEF_V1_CONFIGURATION_DIGEST:
        raise ValueError("ZERO-DAY candidate receipt configuration identity mismatch")
    if receipt.source_registry_version != artifact.source_registry_version:
        raise ValueError("ZERO-DAY candidate receipt source registry mismatch")
    if receipt.as_of != artifact.as_of:
        raise ValueError("ZERO-DAY candidate receipt boundary mismatch")
    if receipt.generated_at != artifact.generated_at:
        raise ValueError("ZERO-DAY candidate receipt generation time mismatch")
    if receipt.output_digest != artifact.output_digest:
        raise ValueError("ZERO-DAY candidate receipt does not bind candidate output")
    expected_input_digest = _candidate_input_digest(
        observations,
        control_snapshot_id=artifact.control_snapshot_id,
    )
    if receipt.input_digest != expected_input_digest:
        raise ValueError("ZERO-DAY observations do not match persisted PEF_V1 input digest")


def _require_pef_v1_pair(
    artifact: PefV1Artifact,
    run: ShadowExperimentRun,
    *,
    run_class: str,
) -> dict[str, int]:
    if run_class != ZERO_DAY_RUN_CLASS:
        raise ValueError("ZERO-DAY requires a CONFIRMATORY PEF_V1 run")
    if artifact.status is not PefArtifactStatus.RAN or run.status is not ShadowRunStatus.RAN:
        raise ValueError("ZERO-DAY requires complete RAN candidate and paired run artifacts")
    if artifact.experiment_id != PEF_V1_EXPERIMENT_ID or run.experiment_id != PEF_V1_EXPERIMENT_ID:
        raise ValueError("ZERO-DAY requires PEF_V1 experiment identity")
    if artifact.candidate_id != PEF_V1_CANDIDATE_ID or run.candidate_id != PEF_V1_CANDIDATE_ID:
        raise ValueError("ZERO-DAY requires PEF_V1 candidate identity")
    if (
        artifact.configuration_digest != PEF_V1_CONFIGURATION_DIGEST
        or run.configuration_digest != PEF_V1_CONFIGURATION_DIGEST
    ):
        raise ValueError("ZERO-DAY requires frozen PEF_V1 configuration identity")
    if artifact.authority_state != PEF_AUTHORITY_STATE or run.authority_state != PEF_AUTHORITY_STATE:
        raise ValueError("ZERO-DAY requires experimental-shadow PEF_V1 authority")
    if run.candidate_freeze_receipt_id is None:
        raise ValueError("ZERO-DAY forbids freeze-unbound runs")
    if any(
        state is not HealthValue.OK
        for state in (
            run.coverage_state,
            run.freshness_state,
            run.transport_state,
            run.schema_state,
        )
    ):
        raise ValueError("ZERO-DAY requires fully OK seal-time coverage and source health")
    if artifact.as_of != run.as_of:
        raise ValueError("ZERO-DAY candidate and control boundaries differ")
    if artifact.artifact_id != run.candidate_artifact_id:
        raise ValueError("ZERO-DAY run does not bind the supplied candidate artifact")
    if artifact.output_digest != run.candidate_output_digest:
        raise ValueError("ZERO-DAY run candidate digest mismatch")
    if artifact.control_snapshot_id != run.control_snapshot_id:
        raise ValueError("ZERO-DAY control snapshot identity mismatch")
    if artifact.control_receipt_id != run.control_receipt_id:
        raise ValueError("ZERO-DAY control receipt identity mismatch")

    candidate_ids = [item.episode_id for item in artifact.episodes]
    control_ids = [item.episode_id for item in run.control_ranking]
    if len(candidate_ids) != len(set(candidate_ids)):
        raise ValueError("ZERO-DAY candidate ranking contains duplicate episode ids")
    if len(control_ids) != len(set(control_ids)):
        raise ValueError("ZERO-DAY control ranking contains duplicate episode ids")
    if set(candidate_ids) != set(control_ids):
        raise ValueError("ZERO-DAY requires identical candidate/control episode universes")
    candidate_ranks = sorted(item.rank for item in artifact.episodes)
    control_ranks = sorted(item.rank for item in run.control_ranking)
    expected_ranks = list(range(1, len(candidate_ids) + 1))
    if candidate_ranks != expected_ranks or control_ranks != expected_ranks:
        raise ValueError("ZERO-DAY requires complete deterministic rank permutations")
    return {item.episode_id: item.rank for item in run.control_ranking}


def _require_persisted_live_availability(
    artifact: PefV1Artifact,
    run: ShadowExperimentRun,
    binding: ZeroDayPefPersistenceBinding,
    *,
    sealed_at: datetime,
) -> None:
    for generated_at, persisted_at, label in (
        (artifact.generated_at, binding.artifact_persisted_at, "candidate artifact"),
        (
            binding.candidate_receipt.generated_at,
            binding.candidate_receipt_persisted_at,
            "candidate receipt",
        ),
        (run.generated_at, binding.run_persisted_at, "shadow run"),
    ):
        _require_aware(generated_at, f"{label} generated_at")
        if persisted_at < generated_at:
            raise ValueError(f"ZERO-DAY {label} persistence precedes generation")
        if persisted_at > sealed_at:
            raise ValueError(f"ZERO-DAY {label} was not persisted by sealed_at")


def build_zero_day_seal(
    artifact: PefV1Artifact,
    run: ShadowExperimentRun,
    observations: Iterable[BaselineObservationInput],
    persistence: ZeroDayPefPersistenceBinding,
    *,
    run_class: str,
    sealed_at: datetime,
) -> ZeroDaySeal:
    """Derive one deterministic diagnostic cohort from an exact persisted PEF_V1 pair.

    The candidate ordering is never re-ranked. The supplied observations must
    reconstruct the exact persisted candidate-receipt input digest; source
    persistence timestamps must prove that the pair was actually available by
    ``sealed_at``; and any non-OK health state makes the boundary unavailable.
    """
    require_zero_day_boundary(run.as_of)
    _require_aware(sealed_at, "ZERO-DAY sealed_at")
    if sealed_at < run.as_of:
        raise ValueError("ZERO-DAY cannot be sealed before its source boundary")
    if sealed_at > run.as_of + timedelta(seconds=ZERO_DAY_MAX_SEAL_DELAY_SECONDS):
        raise ValueError("ZERO-DAY seal missed its 30-minute live sealing window")

    control_ranks = _require_pef_v1_pair(artifact, run, run_class=run_class)
    observation_items = tuple(observations)
    by_id = {item.observation_id: item for item in observation_items}
    if len(by_id) != len(observation_items):
        raise ValueError("ZERO-DAY observation inputs contain duplicate ids")
    _require_candidate_receipt(artifact, observation_items, persistence)
    _require_persisted_live_availability(
        artifact,
        run,
        persistence,
        sealed_at=sealed_at,
    )

    selected: list[ZeroDayCandidate] = []
    for candidate in sorted(artifact.episodes, key=lambda item: item.rank):
        if not candidate.has_prospective_primary_emission:
            continue
        control_rank = control_ranks[candidate.episode_id]
        if candidate.rank >= control_rank:
            continue

        members: list[BaselineObservationInput] = []
        for observation_id in candidate.observation_ids:
            member = by_id.get(observation_id)
            if member is None:
                raise ValueError(
                    "ZERO-DAY cannot establish seal-time attention state from incomplete inputs"
                )
            if member.observed_at > artifact.as_of:
                raise ValueError("ZERO-DAY seal input contains future member evidence")
            members.append(member)

        roles = {role for member in members for role in member.grouping.signal_roles}
        if roles & ZERO_DAY_FOLLOW_ON_ROLES:
            continue
        if (
            candidate.prospective_last_observed_at is None
            or candidate.prospective_age_seconds is None
        ):
            raise ValueError("ZERO-DAY primary-emission candidate lacks frozen freshness fields")

        selected.append(
            ZeroDayCandidate(
                position=len(selected) + 1,
                episode_id=candidate.episode_id,
                observation_ids=candidate.observation_ids,
                candidate_rank=candidate.rank,
                control_rank=control_rank,
                rank_advantage=control_rank - candidate.rank,
                prospective_last_observed_at=candidate.prospective_last_observed_at,
                prospective_age_seconds=candidate.prospective_age_seconds,
            )
        )
        if len(selected) == ZERO_DAY_COHORT_SIZE:
            break

    freeze_receipt_id = run.candidate_freeze_receipt_id
    if freeze_receipt_id is None:
        raise ValueError("ZERO-DAY forbids freeze-unbound runs")
    return ZeroDaySeal(
        as_of=artifact.as_of,
        sealed_at=sealed_at,
        run_id=run.run_id,
        run_digest=run.run_digest,
        run_persisted_at=persistence.run_persisted_at,
        candidate_artifact_id=artifact.artifact_id,
        candidate_output_digest=artifact.output_digest,
        candidate_artifact_persisted_at=persistence.artifact_persisted_at,
        candidate_receipt_id=persistence.candidate_receipt.receipt_id,
        candidate_input_digest=persistence.candidate_receipt.input_digest,
        candidate_receipt_persisted_at=persistence.candidate_receipt_persisted_at,
        candidate_freeze_receipt_id=freeze_receipt_id,
        source_registry_version=artifact.source_registry_version,
        candidates=tuple(selected),
    )


@dataclass(frozen=True, slots=True)
class ZeroDayFollowOnEvidence:
    """Unverified follow-on evidence placeholder.

    V0 deliberately cannot turn this object into HIT/MISS authority. A later
    adapter/projection must supply an auditable episode-membership and coverage
    binding before positive or negative grading can be enabled.
    """

    episode_id: str
    observation_id: str
    source_id: str
    observed_at: datetime
    signal_roles: tuple[str, ...]
    membership_receipt_id: str

    def __post_init__(self) -> None:
        if not self.episode_id.startswith("episode_"):
            raise ValueError("ZERO-DAY follow-on evidence requires an episode id")
        if not self.observation_id.startswith("obs_"):
            raise ValueError("ZERO-DAY follow-on evidence requires an observation id")
        if not self.source_id:
            raise ValueError("ZERO-DAY follow-on evidence requires a source id")
        _require_aware(self.observed_at, "ZERO-DAY follow-on observed_at")
        if not ZERO_DAY_FOLLOW_ON_ROLES.intersection(self.signal_roles):
            raise ValueError("ZERO-DAY follow-on evidence must carry ATTENTION or DISCOVERY")
        if not self.membership_receipt_id.startswith("receipt_"):
            raise ValueError("ZERO-DAY follow-on evidence requires auditable membership binding")

    def to_canonical(self) -> dict[str, CanonicalValue]:
        return {
            "episode_id": self.episode_id,
            "membership_receipt_id": self.membership_receipt_id,
            "observation_id": self.observation_id,
            "observed_at": canonical_timestamp(self.observed_at),
            "signal_roles": list(sorted(self.signal_roles)),
            "source_id": self.source_id,
        }


class ZeroDayMemberStatus(StrEnum):
    PENDING = "PENDING"
    UNVERIFIED = "UNVERIFIED"


@dataclass(frozen=True, slots=True)
class ZeroDayMemberGrade:
    position: int
    episode_id: str
    status: ZeroDayMemberStatus
    first_follow_on_observed_at: datetime | None
    lead_seconds: int | None
    evidence: tuple[ZeroDayFollowOnEvidence, ...]

    def to_canonical(self) -> dict[str, CanonicalValue]:
        evidence_values: list[CanonicalValue] = [item.to_canonical() for item in self.evidence]
        return {
            "episode_id": self.episode_id,
            "evidence": evidence_values,
            "first_follow_on_observed_at": (
                None
                if self.first_follow_on_observed_at is None
                else canonical_timestamp(self.first_follow_on_observed_at)
            ),
            "lead_seconds": self.lead_seconds,
            "position": self.position,
            "status": self.status.value,
        }


class ZeroDayGradeStatus(StrEnum):
    PENDING = "PENDING"
    UNVERIFIED = "UNVERIFIED"


@dataclass(frozen=True, slots=True)
class ZeroDayGrade:
    seal_id: str
    seal_digest: Digest
    horizon_seconds: int
    cutoff: datetime
    graded_at: datetime
    status: ZeroDayGradeStatus
    members: tuple[ZeroDayMemberGrade, ...]
    schema_version: str = ZERO_DAY_GRADE_SCHEMA_VERSION
    authority_state: str = ZERO_DAY_AUTHORITY_STATE

    @property
    def grade_id(self) -> str:
        return "zerodaygrade_" + sha256_hex(canonical_json_bytes(self.to_canonical()))

    @property
    def grade_digest(self) -> Digest:
        return sha256_digest(canonical_json_bytes(self.to_canonical()))

    def to_canonical(self) -> dict[str, CanonicalValue]:
        member_values: list[CanonicalValue] = [item.to_canonical() for item in self.members]
        return {
            "authority_state": self.authority_state,
            "cutoff": canonical_timestamp(self.cutoff),
            "graded_at": canonical_timestamp(self.graded_at),
            "horizon_seconds": self.horizon_seconds,
            "members": member_values,
            "schema_version": self.schema_version,
            "seal_digest": str(self.seal_digest),
            "seal_id": self.seal_id,
            "status": self.status.value,
        }


def build_zero_day_grade(
    seal: ZeroDaySeal,
    follow_on_evidence: Iterable[ZeroDayFollowOnEvidence],
    *,
    horizon_seconds: int,
    graded_at: datetime,
) -> ZeroDayGrade:
    """Retain the sealed denominator while grading authority remains unavailable.

    V0 intentionally rejects caller-supplied follow-on evidence because there
    is not yet a separately auditable membership/coverage projection that can
    prove it belongs to the sealed episode. Before the cutoff the grade remains
    PENDING; at/after the cutoff it becomes explicitly UNVERIFIED, never HIT or
    MISS.
    """
    if horizon_seconds not in ZERO_DAY_GRADE_HORIZONS_SECONDS:
        raise ValueError("ZERO-DAY grade horizon is not frozen by V0")
    _require_aware(graded_at, "ZERO-DAY graded_at")
    if graded_at < seal.as_of:
        raise ValueError("ZERO-DAY cannot grade before the seal boundary")

    evidence_items = tuple(follow_on_evidence)
    if evidence_items:
        raise ValueError(
            "ZERO-DAY follow-on membership authority is unavailable; evidence remains ungraded"
        )

    cutoff = seal.as_of + timedelta(seconds=horizon_seconds)
    complete = graded_at >= cutoff
    member_status = (
        ZeroDayMemberStatus.UNVERIFIED if complete else ZeroDayMemberStatus.PENDING
    )
    members = tuple(
        ZeroDayMemberGrade(
            position=candidate.position,
            episode_id=candidate.episode_id,
            status=member_status,
            first_follow_on_observed_at=None,
            lead_seconds=None,
            evidence=(),
        )
        for candidate in seal.candidates
    )
    return ZeroDayGrade(
        seal_id=seal.seal_id,
        seal_digest=seal.seal_digest,
        horizon_seconds=horizon_seconds,
        cutoff=cutoff,
        graded_at=graded_at,
        status=ZeroDayGradeStatus.UNVERIFIED if complete else ZeroDayGradeStatus.PENDING,
        members=members,
    )


__all__ = [
    "ZERO_DAY_AUTHORITY_STATE",
    "ZERO_DAY_COHORT_SIZE",
    "ZERO_DAY_FOLLOW_ON_ROLES",
    "ZERO_DAY_GRADE_HORIZONS_SECONDS",
    "ZERO_DAY_GRADE_SCHEMA_VERSION",
    "ZERO_DAY_MAX_SEAL_DELAY_SECONDS",
    "ZERO_DAY_SCHEMA_VERSION",
    "ZERO_DAY_SELECTION_RULE_VERSION",
    "ZeroDayCandidate",
    "ZeroDayFollowOnEvidence",
    "ZeroDayGrade",
    "ZeroDayGradeStatus",
    "ZeroDayMemberGrade",
    "ZeroDayMemberStatus",
    "ZeroDayPefPersistenceBinding",
    "ZeroDaySeal",
    "build_zero_day_grade",
    "build_zero_day_seal",
    "require_zero_day_boundary",
]
