from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import StrEnum

from .canonical_json import CanonicalValue, canonical_json_bytes, canonical_timestamp
from .digests import Digest, sha256_digest, sha256_hex
from .health import HealthValue
from .intelligence import (
    BASELINE_ALGORITHM_VERSION,
    BASELINE_PROJECTION_NAME,
    BASELINE_PROJECTION_VERSION,
    BASELINE_RANKING_POLICY_VERSION,
    BASELINE_SCHEMA_VERSION,
    BaselineEpisode,
    BaselineObservationInput,
    BaselineSnapshot,
)
from .receipt import ProjectionReceipt, ProjectionStatus

PEF_EXPERIMENT_ID = "advanced-ranking-pef-v0"
PEF_CANDIDATE_ID = "prospective-primary-emission-freshness-v0"
PEF_PROJECTION_NAME = PEF_EXPERIMENT_ID
PEF_PROJECTION_VERSION = PEF_CANDIDATE_ID
PEF_SCHEMA_VERSION = "pef-ranking-artifact-v0"
PEF_ALGORITHM_VERSION = "prospective-primary-emission-freshness-lexicographic-v0"
PEF_RANKING_POLICY_VERSION = PEF_ALGORITHM_VERSION
PEF_RECEIPT_SCHEMA_VERSION = "projection-receipt-v1"
PEF_AUTHORITY_STATE = "EXPERIMENTAL_SHADOW"
PEF_PRIMARY_EMISSION_ROLE = "PRIMARY_EMISSION"

PEF_PREREGISTERED_CONFIG_DIGEST = Digest(
    "sha256:e2627f62deac24e5f1b09960687761ebbcc61b3fd0c8fec07fec0006dcff7dc1"
)

_activity_eligibility: dict[str, CanonicalValue] = {
    "eligible_reasons": ["ACTIVE_ENRICHMENT", "DISCOVERY", "SCHEDULED"],
    "exclude_backfill": True,
    "exclude_recovered_after_gap": True,
}
_feature_definitions: dict[str, CanonicalValue] = {
    "has_any_prospective_evidence": (
        "true iff episode has at least one member BaselineObservationInput "
        "with is_prospective=true at as_of"
    ),
    "has_prospective_primary_emission": (
        "true iff at least one prospective member observation has signal role PRIMARY_EMISSION"
    ),
    "prospective_last_observed_at": (
        "maximum observed_at among prospective member observations; null when none"
    ),
    "prospective_age_seconds": (
        "integer whole seconds from prospective_last_observed_at to as_of; "
        "null when no prospective member"
    ),
    "prospective_source_role_diversity": (
        "count of distinct signal roles across prospective member observations only"
    ),
    "prospective_evidence_count": "count of prospective member observations only",
    "baseline_activity_metrics": (
        "reuse control BaselineEpisode mentions_1h, mentions_6h, mentions_24h, "
        "velocity_6h_delta, acceleration_6h for the exact same current grouping episode"
    ),
}
_ranking_order: list[CanonicalValue] = [
    "has_prospective_primary_emission_desc",
    "has_any_prospective_evidence_desc",
    "prospective_age_seconds_asc_null_last",
    "velocity_6h_delta_desc",
    "mentions_1h_desc",
    "mentions_6h_desc",
    "acceleration_6h_desc",
    "mentions_24h_desc",
    "prospective_source_role_diversity_desc",
    "prospective_evidence_count_desc",
    "episode_id_asc",
]

PEF_CONFIGURATION: dict[str, CanonicalValue] = {
    "algorithm_version": PEF_ALGORITHM_VERSION,
    "input_contract": "same-baseline-observation-and-grouping-inputs-as-control",
    "activity_eligibility": _activity_eligibility,
    "feature_definitions": _feature_definitions,
    "primary_emission_role": PEF_PRIMARY_EMISSION_ROLE,
    "ranking_order": _ranking_order,
    "no_prospective_evidence_policy": "sort_after_any_episode_with_prospective_evidence",
    "score_semantics": "NO_SCALAR_SCORE_LEXICOGRAPHIC_RANK_ONLY",
    "grouping_contract": (
        "candidate uses exact control grouping episode membership at each as_of "
        "and never regroups observations"
    ),
}
PEF_CONFIGURATION_DIGEST = sha256_digest(canonical_json_bytes(PEF_CONFIGURATION))


class PefArtifactStatus(StrEnum):
    """Artifact lifecycle status.

    R8: FAILED or partial output must never masquerade as COMPLETE. Only RAN
    artifacts carry a ranked ordering; NOT_RUN means no artifact exists yet and
    FAILED artifacts retain their failure reason without any ranking payload.
    """

    NOT_RUN = "NOT_RUN"
    RAN = "RAN"
    FAILED = "FAILED"


def require_pef_configuration_identity() -> None:
    """Fail closed when the frozen configuration digest drifts from preregistration."""
    if PEF_CONFIGURATION_DIGEST != PEF_PREREGISTERED_CONFIG_DIGEST:
        raise RuntimeError("PEF_V0 configuration digest drifted from preregistration")


@dataclass(frozen=True, slots=True)
class PefEpisodeRanking:
    rank: int
    episode_id: str
    observation_ids: tuple[str, ...]
    has_any_prospective_evidence: bool
    has_prospective_primary_emission: bool
    prospective_last_observed_at: datetime | None
    prospective_age_seconds: int | None
    prospective_source_role_diversity: int
    prospective_evidence_count: int
    mentions_1h: int
    mentions_6h: int
    mentions_24h: int
    velocity_6h_delta: int
    acceleration_6h: int

    def to_canonical(self) -> dict[str, CanonicalValue]:
        last_observed = (
            None
            if self.prospective_last_observed_at is None
            else canonical_timestamp(self.prospective_last_observed_at)
        )
        observation_ids: list[CanonicalValue] = list(self.observation_ids)
        return {
            "acceleration_6h": self.acceleration_6h,
            "episode_id": self.episode_id,
            "has_any_prospective_evidence": self.has_any_prospective_evidence,
            "has_prospective_primary_emission": self.has_prospective_primary_emission,
            "mentions_1h": self.mentions_1h,
            "mentions_24h": self.mentions_24h,
            "mentions_6h": self.mentions_6h,
            "observation_ids": observation_ids,
            "prospective_age_seconds": self.prospective_age_seconds,
            "prospective_evidence_count": self.prospective_evidence_count,
            "prospective_last_observed_at": last_observed,
            "prospective_source_role_diversity": self.prospective_source_role_diversity,
            "rank": self.rank,
            "velocity_6h_delta": self.velocity_6h_delta,
        }


@dataclass(frozen=True, slots=True)
class PefArtifact:
    as_of: datetime
    control_snapshot_id: str
    control_receipt_id: str
    source_registry_version: Digest
    generated_at: datetime
    status: PefArtifactStatus = PefArtifactStatus.RAN
    failure_reason: str | None = None
    episodes: tuple[PefEpisodeRanking, ...] = ()
    experiment_id: str = PEF_EXPERIMENT_ID
    candidate_id: str = PEF_CANDIDATE_ID
    schema_version: str = PEF_SCHEMA_VERSION
    algorithm_version: str = PEF_ALGORITHM_VERSION
    ranking_policy_version: str = PEF_RANKING_POLICY_VERSION
    configuration_digest: Digest = PEF_CONFIGURATION_DIGEST
    authority_state: str = PEF_AUTHORITY_STATE

    def __post_init__(self) -> None:
        if self.as_of.tzinfo is None or self.as_of.utcoffset() is None:
            raise ValueError("pef artifact as_of must be timezone-aware")
        if self.generated_at.tzinfo is None or self.generated_at.utcoffset() is None:
            raise ValueError("pef artifact generated_at must be timezone-aware")
        if self.status is PefArtifactStatus.RAN and self.failure_reason is not None:
            raise ValueError("RAN pef artifact cannot carry a failure reason")
        if self.status is PefArtifactStatus.FAILED and not self.failure_reason:
            raise ValueError("FAILED pef artifact requires an explicit failure reason")
        if self.status is not PefArtifactStatus.RAN and self.episodes:
            raise ValueError("only RAN pef artifacts may carry a ranking payload")

    @property
    def artifact_id(self) -> str:
        return "artifact_" + sha256_hex(canonical_json_bytes(self.to_canonical()))

    @property
    def output_digest(self) -> Digest:
        return sha256_digest(canonical_json_bytes(self.to_canonical()))

    def to_canonical(self) -> dict[str, CanonicalValue]:
        episode_values: list[CanonicalValue] = [episode.to_canonical() for episode in self.episodes]
        return {
            "algorithm_version": self.algorithm_version,
            "as_of": canonical_timestamp(self.as_of),
            "authority_state": self.authority_state,
            "candidate_id": self.candidate_id,
            "configuration_digest": str(self.configuration_digest),
            "control_receipt_id": self.control_receipt_id,
            "control_snapshot_id": self.control_snapshot_id,
            "episodes": episode_values,
            "experiment_id": self.experiment_id,
            "failure_reason": self.failure_reason,
            "ranking_policy_version": self.ranking_policy_version,
            "schema_version": self.schema_version,
            "source_registry_version": str(self.source_registry_version),
            "status": self.status.value,
        }


def _prospective_age_seconds(delta: timedelta) -> int:
    if delta < timedelta(0):
        raise ValueError("prospective last observation cannot be after as_of")
    return delta.days * 86400 + delta.seconds


def _episode_ranking(
    episode: BaselineEpisode, members: tuple[BaselineObservationInput, ...], *, as_of: datetime
) -> PefEpisodeRanking:
    prospective = tuple(item for item in members if item.is_prospective)
    if prospective:
        last_observed_at = max(item.observed_at for item in prospective)
        age_seconds: int | None = _prospective_age_seconds(as_of - last_observed_at)
        roles = {role for item in prospective for role in item.grouping.signal_roles}
        has_primary = PEF_PRIMARY_EMISSION_ROLE in roles
        diversity = len(roles)
    else:
        last_observed_at = None
        age_seconds = None
        has_primary = False
        diversity = 0
    return PefEpisodeRanking(
        rank=0,
        episode_id=episode.episode_id,
        observation_ids=episode.observation_ids,
        has_any_prospective_evidence=bool(prospective),
        has_prospective_primary_emission=has_primary,
        prospective_last_observed_at=last_observed_at,
        prospective_age_seconds=age_seconds,
        prospective_source_role_diversity=diversity,
        prospective_evidence_count=len(prospective),
        mentions_1h=episode.mentions_1h,
        mentions_6h=episode.mentions_6h,
        mentions_24h=episode.mentions_24h,
        velocity_6h_delta=episode.velocity_6h_delta,
        acceleration_6h=episode.acceleration_6h,
    )


def _lexicographic_key(episode: PefEpisodeRanking) -> tuple[CanonicalValue, ...]:
    age = episode.prospective_age_seconds
    null_last_age: tuple[CanonicalValue, ...] = (1, 0) if age is None else (0, age)
    return (
        0 if episode.has_prospective_primary_emission else 1,
        0 if episode.has_any_prospective_evidence else 1,
        *null_last_age,
        -episode.velocity_6h_delta,
        -episode.mentions_1h,
        -episode.mentions_6h,
        -episode.acceleration_6h,
        -episode.mentions_24h,
        -episode.prospective_source_role_diversity,
        -episode.prospective_evidence_count,
        episode.episode_id,
    )


def _rank(episode_rankings: list[PefEpisodeRanking]) -> tuple[PefEpisodeRanking, ...]:
    ordered = sorted(episode_rankings, key=_lexicographic_key)
    return tuple(replace(episode, rank=index) for index, episode in enumerate(ordered, start=1))


def build_pef_ranking(
    observations: Iterable[BaselineObservationInput],
    *,
    control_snapshot: BaselineSnapshot,
    as_of: datetime,
) -> tuple[PefEpisodeRanking, ...]:
    """Deterministically rank the exact control grouping episodes (no scalar score)."""
    require_pef_configuration_identity()
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("pef as_of must be timezone-aware")
    if control_snapshot.as_of != as_of:
        raise ValueError("control snapshot as_of must match pef as_of")

    eligible = tuple(
        sorted(
            (item for item in observations if item.observed_at <= as_of),
            key=lambda item: item.observation_id,
        )
    )
    by_id = {item.observation_id: item for item in eligible}
    if len(by_id) != len(eligible):
        raise ValueError("duplicate observation_id in pef inputs")

    episode_rankings: list[PefEpisodeRanking] = []
    for episode in control_snapshot.episodes:
        members: list[BaselineObservationInput] = []
        for observation_id in episode.observation_ids:
            item = by_id.get(observation_id)
            if item is None:
                raise ValueError("control snapshot episode references unknown observation")
            members.append(item)
        episode_rankings.append(_episode_ranking(episode, tuple(members), as_of=as_of))
    return _rank(episode_rankings)


def build_pef_artifact(
    observations: Iterable[BaselineObservationInput],
    *,
    control_snapshot: BaselineSnapshot,
    control_receipt: ProjectionReceipt,
    as_of: datetime,
    generated_at: datetime,
    source_registry_version: Digest,
) -> PefArtifact:
    require_pef_configuration_identity()
    if control_receipt.status is not ProjectionStatus.COMPLETE:
        raise ValueError("pef ranking requires a COMPLETE control snapshot")
    ranking = build_pef_ranking(observations, control_snapshot=control_snapshot, as_of=as_of)
    return PefArtifact(
        as_of=as_of,
        control_snapshot_id=control_snapshot.snapshot_id,
        control_receipt_id=control_receipt.receipt_id,
        source_registry_version=source_registry_version,
        generated_at=generated_at,
        episodes=ranking,
    )


def failed_pef_artifact(
    *,
    control_snapshot: BaselineSnapshot,
    control_receipt: ProjectionReceipt,
    as_of: datetime,
    generated_at: datetime,
    source_registry_version: Digest,
    failure_reason: str,
) -> PefArtifact:
    require_pef_configuration_identity()
    return PefArtifact(
        as_of=as_of,
        control_snapshot_id=control_snapshot.snapshot_id,
        control_receipt_id=control_receipt.receipt_id,
        source_registry_version=source_registry_version,
        generated_at=generated_at,
        status=PefArtifactStatus.FAILED,
        failure_reason=failure_reason,
    )


def pef_input_digest(
    observations: Iterable[BaselineObservationInput],
    *,
    control_snapshot: BaselineSnapshot,
) -> Digest:
    observation_values: list[CanonicalValue] = [
        item.to_canonical() for item in sorted(observations, key=lambda item: item.observation_id)
    ]
    material: dict[str, CanonicalValue] = {
        "control_snapshot_id": control_snapshot.snapshot_id,
        "observations": observation_values,
    }
    return sha256_digest(canonical_json_bytes(material))


def build_pef_receipt(
    artifact: PefArtifact,
    *,
    observations: Iterable[BaselineObservationInput],
    control_snapshot: BaselineSnapshot,
) -> ProjectionReceipt:
    require_pef_configuration_identity()
    receipt_status = ProjectionStatus.COMPLETE
    if artifact.status is PefArtifactStatus.FAILED:
        receipt_status = ProjectionStatus.FAILED
    elif artifact.status is not PefArtifactStatus.RAN:
        raise ValueError("NOT_RUN pef artifacts cannot produce receipts")
    return ProjectionReceipt(
        receipt_schema_version=PEF_RECEIPT_SCHEMA_VERSION,
        projection_name=PEF_PROJECTION_NAME,
        projection_version=PEF_PROJECTION_VERSION,
        schema_version=PEF_SCHEMA_VERSION,
        algorithm_version=PEF_ALGORITHM_VERSION,
        ranking_policy_version=PEF_RANKING_POLICY_VERSION,
        configuration_digest=PEF_CONFIGURATION_DIGEST,
        source_registry_version=artifact.source_registry_version,
        as_of=artifact.as_of,
        generated_at=artifact.generated_at,
        input_digest=pef_input_digest(observations, control_snapshot=control_snapshot),
        output_digest=artifact.output_digest,
        status=receipt_status,
    )


SHADOW_SCHEMA_VERSION = "shadow-experiment-run-v0"
SHADOW_RUN_ID_PREFIX = "shadowrun_"
SHADOW_SOURCE_REGISTRY_VERSION_LABEL = "source_registry_version"


@dataclass(frozen=True, slots=True)
class ShadowControlArmRanking:
    """Control-arm surface of a paired shadow run (R6 permanent comparator)."""

    rank: int
    episode_id: str

    def to_canonical(self) -> dict[str, CanonicalValue]:
        return {"episode_id": self.episode_id, "rank": self.rank}


def shadow_universe_digest(control_snapshot: BaselineSnapshot) -> Digest:
    """Digest the exact paired episode universe both arms must rank.

    R1/R6: the universe is the control grouping's episode membership over the
    eligible evidence at ``as_of``; both arms must see exactly this universe.
    """
    episode_values: list[CanonicalValue] = [
        {
            "episode_id": episode.episode_id,
            "observation_ids": list(episode.observation_ids),
        }
        for episode in sorted(control_snapshot.episodes, key=lambda item: item.episode_id)
    ]
    material: dict[str, CanonicalValue] = {
        "as_of": canonical_timestamp(control_snapshot.as_of),
        "episodes": episode_values,
        "snapshot_id": control_snapshot.snapshot_id,
    }
    return sha256_digest(canonical_json_bytes(material))


class ShadowRunStatus(StrEnum):
    """Paired shadow-run lifecycle status (R8).

    RAN means both arms completed against the identical universe; FAILED runs
    carry an explicit failure reason and never a ranking payload, so a failed
    run can never masquerade as a completed comparison.
    """

    RAN = "RAN"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class ShadowExperimentRun:
    """Paired control-vs-candidate shadow result (EXPERIMENTAL_SHADOW, R7).

    The run is bound to the exact control snapshot id, control receipt id,
    candidate artifact id/digest, configuration digest, episode-universe
    digest, ``as_of``, and the coverage/health states both arms observed (R4,
    R8). It never modifies the control snapshot and carries no scalar score.
    """

    as_of: datetime
    generated_at: datetime
    control_snapshot_id: str
    control_receipt_id: str
    coverage_state: HealthValue
    freshness_state: HealthValue
    transport_state: HealthValue
    schema_state: HealthValue
    status: ShadowRunStatus
    episode_universe_digest: Digest
    candidate_artifact_id: str
    candidate_output_digest: Digest
    control_ranking: tuple[ShadowControlArmRanking, ...] = ()
    failure_reason: str | None = None
    experiment_id: str = PEF_EXPERIMENT_ID
    candidate_id: str = PEF_CANDIDATE_ID
    schema_version: str = SHADOW_SCHEMA_VERSION
    algorithm_version: str = PEF_ALGORITHM_VERSION
    configuration_digest: Digest = PEF_CONFIGURATION_DIGEST
    authority_state: str = PEF_AUTHORITY_STATE

    def __post_init__(self) -> None:
        if self.as_of.tzinfo is None or self.as_of.utcoffset() is None:
            raise ValueError("shadow run as_of must be timezone-aware")
        if self.generated_at.tzinfo is None or self.generated_at.utcoffset() is None:
            raise ValueError("shadow run generated_at must be timezone-aware")
        if self.status is ShadowRunStatus.RAN and self.failure_reason is not None:
            raise ValueError("RAN shadow run cannot carry a failure reason")
        if self.status is ShadowRunStatus.FAILED and not self.failure_reason:
            raise ValueError("FAILED shadow run requires an explicit failure reason")
        if self.status is not ShadowRunStatus.RAN and self.control_ranking:
            raise ValueError("only RAN shadow runs may carry a control ranking payload")

    @property
    def run_id(self) -> str:
        return SHADOW_RUN_ID_PREFIX + sha256_hex(canonical_json_bytes(self.to_canonical()))

    @property
    def run_digest(self) -> Digest:
        return sha256_digest(canonical_json_bytes(self.to_canonical()))

    def to_canonical(self) -> dict[str, CanonicalValue]:
        ranking_values: list[CanonicalValue] = [
            item.to_canonical() for item in self.control_ranking
        ]
        return {
            "algorithm_version": self.algorithm_version,
            "as_of": canonical_timestamp(self.as_of),
            "authority_state": self.authority_state,
            "candidate_artifact_id": self.candidate_artifact_id,
            "candidate_id": self.candidate_id,
            "candidate_output_digest": str(self.candidate_output_digest),
            "configuration_digest": str(self.configuration_digest),
            "control_coverage_state": self.coverage_state.value,
            "control_freshness_state": self.freshness_state.value,
            "control_ranking": ranking_values,
            "control_ranking_policy_version": BASELINE_RANKING_POLICY_VERSION,
            "control_receipt_id": self.control_receipt_id,
            "control_schema_state": self.schema_state.value,
            "control_snapshot_id": self.control_snapshot_id,
            "control_transport_state": self.transport_state.value,
            "episode_universe_digest": str(self.episode_universe_digest),
            "experiment_id": self.experiment_id,
            "failure_reason": self.failure_reason,
            "generated_at": canonical_timestamp(self.generated_at),
            "schema_version": self.schema_version,
            "status": self.status.value,
        }


def _shadow_control_ranking(
    control_snapshot: BaselineSnapshot,
) -> tuple[ShadowControlArmRanking, ...]:
    return tuple(
        ShadowControlArmRanking(rank=episode.rank, episode_id=episode.episode_id)
        for episode in sorted(control_snapshot.episodes, key=lambda item: item.rank)
    )


def _require_paired_universe(
    control_snapshot: BaselineSnapshot, candidate_artifact: PefArtifact
) -> None:
    control_universe = {
        episode.episode_id: tuple(episode.observation_ids) for episode in control_snapshot.episodes
    }
    candidate_universe = {
        episode.episode_id: tuple(episode.observation_ids)
        for episode in candidate_artifact.episodes
    }
    if len(candidate_universe) != len(candidate_artifact.episodes):
        raise ValueError("candidate ranking contains duplicate episode ids")
    if control_universe != candidate_universe:
        raise ValueError("shadow experiment requires an identical episode universe for both arms")


def _require_candidate_identity(
    candidate_artifact: PefArtifact, candidate_receipt: ProjectionReceipt
) -> None:
    if candidate_artifact.experiment_id != PEF_EXPERIMENT_ID:
        raise ValueError("candidate artifact experiment id mismatch")
    if candidate_artifact.candidate_id != PEF_CANDIDATE_ID:
        raise ValueError("candidate artifact candidate id mismatch")
    if candidate_artifact.schema_version != PEF_SCHEMA_VERSION:
        raise ValueError("candidate artifact schema version mismatch")
    if candidate_artifact.configuration_digest != PEF_CONFIGURATION_DIGEST:
        raise ValueError("candidate artifact configuration digest mismatch")
    if candidate_artifact.authority_state != PEF_AUTHORITY_STATE:
        raise ValueError("candidate artifact authority state mismatch")
    if candidate_receipt.output_digest != candidate_artifact.output_digest:
        raise ValueError("candidate receipt does not bind the candidate artifact")
    if candidate_receipt.projection_name != PEF_PROJECTION_NAME:
        raise ValueError("candidate receipt projection name mismatch")
    if candidate_receipt.projection_version != PEF_PROJECTION_VERSION:
        raise ValueError("candidate receipt projection version mismatch")
    if candidate_receipt.schema_version != PEF_SCHEMA_VERSION:
        raise ValueError("candidate receipt schema version mismatch")
    if candidate_receipt.configuration_digest != PEF_CONFIGURATION_DIGEST:
        raise ValueError("candidate receipt configuration digest mismatch")
    if candidate_artifact.status is PefArtifactStatus.RAN:
        if candidate_receipt.status is not ProjectionStatus.COMPLETE:
            raise ValueError("RAN candidate artifact requires a COMPLETE receipt")
    elif candidate_artifact.status is PefArtifactStatus.FAILED:
        if candidate_receipt.status is not ProjectionStatus.FAILED:
            raise ValueError("FAILED candidate artifact requires a FAILED receipt")
    else:
        raise ValueError("NOT_RUN candidate artifacts cannot join a shadow experiment")


def build_shadow_experiment_run(
    *,
    control_snapshot: BaselineSnapshot,
    control_receipt: ProjectionReceipt,
    candidate_artifact: PefArtifact,
    candidate_receipt: ProjectionReceipt,
    as_of: datetime,
    generated_at: datetime,
) -> ShadowExperimentRun:
    """Pair a control arm and a PEF_V0 candidate arm over an identical universe.

    Both arms are read-only with respect to the baseline snapshot (R6): this
    builder only reads the snapshot and the candidate artifact. Point-in-time
    discipline (R1) and backfill safety (R3) are inherited from both arms by
    construction: each arm was computed from evidence with
    ``observed_at <= as_of`` and prospective-only momentum semantics.
    """
    require_pef_configuration_identity()
    if control_receipt.status is not ProjectionStatus.COMPLETE:
        raise ValueError("shadow experiment requires a COMPLETE control snapshot")
    if (
        control_receipt.output_digest.value.removeprefix("sha256:")
        != (control_snapshot.snapshot_id.split("snapshot_")[-1])
    ):
        raise ValueError("control receipt does not bind the given control snapshot")
    if control_receipt.projection_name != BASELINE_PROJECTION_NAME:
        raise ValueError("control receipt projection name mismatch")
    if control_receipt.projection_version != BASELINE_PROJECTION_VERSION:
        raise ValueError("control receipt projection version mismatch")
    if control_receipt.schema_version != BASELINE_SCHEMA_VERSION:
        raise ValueError("control receipt schema version mismatch")
    if control_receipt.algorithm_version != BASELINE_ALGORITHM_VERSION:
        raise ValueError("control receipt algorithm version mismatch")
    if control_receipt.ranking_policy_version != BASELINE_RANKING_POLICY_VERSION:
        raise ValueError("control receipt ranking policy version mismatch")
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("shadow run as_of must be timezone-aware")
    if as_of != control_snapshot.as_of:
        raise ValueError("shadow experiment requires identical as_of for both arms")
    if candidate_artifact.as_of != as_of:
        raise ValueError("candidate artifact as_of must match the shadow experiment as_of")
    if candidate_artifact.control_snapshot_id != control_snapshot.snapshot_id:
        raise ValueError("candidate artifact must bind the control snapshot")
    _require_candidate_identity(candidate_artifact, candidate_receipt)

    if candidate_artifact.status is PefArtifactStatus.RAN:
        # Only a completed candidate arm can prove it ranked the paired universe;
        # FAILED candidate arms carry no ranking payload to pair against (R8).
        _require_paired_universe(control_snapshot, candidate_artifact)
        return ShadowExperimentRun(
            as_of=as_of,
            generated_at=generated_at,
            control_snapshot_id=control_snapshot.snapshot_id,
            control_receipt_id=control_receipt.receipt_id,
            coverage_state=control_snapshot.coverage_state,
            freshness_state=control_snapshot.freshness_state,
            transport_state=control_snapshot.transport_state,
            schema_state=control_snapshot.schema_state,
            status=ShadowRunStatus.RAN,
            episode_universe_digest=shadow_universe_digest(control_snapshot),
            candidate_artifact_id=candidate_artifact.artifact_id,
            candidate_output_digest=candidate_artifact.output_digest,
            control_ranking=_shadow_control_ranking(control_snapshot),
        )
    return ShadowExperimentRun(
        as_of=as_of,
        generated_at=generated_at,
        control_snapshot_id=control_snapshot.snapshot_id,
        control_receipt_id=control_receipt.receipt_id,
        coverage_state=control_snapshot.coverage_state,
        freshness_state=control_snapshot.freshness_state,
        transport_state=control_snapshot.transport_state,
        schema_state=control_snapshot.schema_state,
        status=ShadowRunStatus.FAILED,
        episode_universe_digest=shadow_universe_digest(control_snapshot),
        candidate_artifact_id=candidate_artifact.artifact_id,
        candidate_output_digest=candidate_artifact.output_digest,
        failure_reason=candidate_artifact.failure_reason,
    )
