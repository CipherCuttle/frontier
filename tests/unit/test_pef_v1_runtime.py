from __future__ import annotations

from datetime import UTC, datetime, timedelta
from hashlib import sha256

from frontier.application.pef_v1 import run_pef_v1_paired
from frontier.domain.advanced_intelligence import PEF_CONFIGURATION_DIGEST
from frontier.domain.canonical_json import canonical_json_bytes
from frontier.domain.digests import Digest, sha256_hex
from frontier.domain.grouping import GroupingInput, GroupingRelationInput
from frontier.domain.grouping_v1 import (
    GROUPING_V1_ALGORITHM_VERSION,
    GROUPING_V1_CONFIGURATION_DIGEST,
    GROUPING_V1_PROJECTION_VERSION,
    CompactGroupingProjection,
)
from frontier.domain.health import HealthValue
from frontier.domain.intelligence import (
    BaselineHealthInput,
    BaselineObservationInput,
    BaselineSnapshot,
)
from frontier.domain.pef_v1 import (
    PEF_V1_CANDIDATE_ID,
    PEF_V1_CONFIGURATION,
    PEF_V1_CONFIGURATION_DIGEST,
    PEF_V1_CONTROL_CONFIGURATION_DIGEST,
    PEF_V1_EXPERIMENT_ID,
    PEF_V1_GROUPING_CONTRACT,
    PEF_V1_PREREGISTERED_CONFIG_DIGEST,
    require_pef_v1_configuration_identity,
)
from frontier.domain.receipt import ProjectionReceipt, ProjectionStatus

AS_OF = datetime(2026, 9, 9, 14, 55, tzinfo=UTC)
REGISTRY = Digest("sha256:" + "1" * 64)


def _obs_id(label: str) -> str:
    return "obs_" + sha256(label.encode()).hexdigest()


def _observation(
    label: str,
    *,
    minutes_ago: int,
    source_id: str,
    role: str,
    canonical_url: str,
    title: str,
) -> BaselineObservationInput:
    return BaselineObservationInput(
        grouping=GroupingInput(
            observation_id=_obs_id(label),
            source_id=source_id,
            source_item_key=label,
            kind="DOCUMENT",
            observed_at=AS_OF - timedelta(minutes=minutes_ago),
            canonical_url=canonical_url,
            title=title,
            text=title,
            signal_roles=(role,),
        ),
        first_reason="SCHEDULED",
        recovered_after_gap=False,
    )


def _health(source_id: str) -> BaselineHealthInput:
    return BaselineHealthInput(
        source_id=source_id,
        as_of=AS_OF - timedelta(seconds=1),
        transport=HealthValue.OK,
        freshness=HealthValue.OK,
        completeness=HealthValue.OK,
        schema=HealthValue.OK,
    )


class _Repository:
    def __init__(self) -> None:
        self.observations = (
            _observation(
                "group-left",
                minutes_ago=3,
                source_id="hn.frontpage",
                role="ATTENTION",
                canonical_url="https://example.test/shared",
                title="Shared deterministic episode title",
            ),
            _observation(
                "group-right",
                minutes_ago=2,
                source_id="hn.frontpage",
                role="ATTENTION",
                canonical_url="https://example.test/shared",
                title="Shared deterministic episode title",
            ),
            _observation(
                "primary",
                minutes_ago=1,
                source_id="pypi.updates",
                role="PRIMARY_EMISSION",
                canonical_url="https://example.test/primary",
                title="Independent primary emission package",
            ),
        )
        self.relations: tuple[GroupingRelationInput, ...] = ()
        self.enabled = ("hn.frontpage", "pypi.updates")
        self.health = tuple(_health(source_id) for source_id in self.enabled)
        self.published: list[tuple[BaselineSnapshot, ProjectionReceipt]] = []

    def list_baseline_observations_as_of(
        self, as_of: datetime
    ) -> list[BaselineObservationInput]:
        return [item for item in self.observations if item.observed_at <= as_of]

    def list_grouping_relations_as_of(self, as_of: datetime) -> list[GroupingRelationInput]:
        return [item for item in self.relations if item.created_at <= as_of]

    def list_enabled_source_ids(self) -> list[str]:
        return list(self.enabled)

    def list_latest_health_as_of(self, as_of: datetime) -> list[BaselineHealthInput]:
        return [item for item in self.health if item.as_of <= as_of]

    def publish_complete_snapshot(
        self,
        snapshot: BaselineSnapshot,
        receipt: ProjectionReceipt,
    ) -> None:
        self.published.append((snapshot, receipt))


def _membership_sets(snapshot: BaselineSnapshot) -> set[frozenset[str]]:
    return {frozenset(episode.observation_ids) for episode in snapshot.episodes}


def _grouping_membership_sets(
    projection: CompactGroupingProjection,
) -> set[frozenset[str]]:
    groups = {frozenset(group.observation_ids) for group in projection.groups}
    singletons = {
        frozenset((observation_id,))
        for observation_id in projection.ungrouped_observation_ids
    }
    return groups | singletons


def _expected_v1_episode_id(observation_ids: tuple[str, ...]) -> str:
    material = {
        "grouping_algorithm_version": GROUPING_V1_ALGORITHM_VERSION,
        "observation_ids": list(observation_ids),
    }
    return "episode_" + sha256_hex(canonical_json_bytes(material))


def test_v1_configuration_digest_is_exact_preregistered_successor_identity() -> None:
    require_pef_v1_configuration_identity()
    assert PEF_V1_CONFIGURATION_DIGEST == PEF_V1_PREREGISTERED_CONFIG_DIGEST
    assert str(PEF_V1_CONFIGURATION_DIGEST) == (
        "sha256:db2305ee0d89ee56b4c0a2837fd7034dad899ec5fc41acc710358b434a52fd67"
    )
    assert PEF_V1_CONFIGURATION["grouping_contract"] == PEF_V1_GROUPING_CONTRACT
    assert PEF_V1_CONFIGURATION_DIGEST != PEF_CONFIGURATION_DIGEST


def test_paired_runtime_uses_v1_grouping_for_exact_same_candidate_control_universe() -> None:
    repository = _Repository()
    result = run_pef_v1_paired(
        repository,
        as_of=AS_OF,
        generated_at=AS_OF,
        source_registry_version=REGISTRY,
    )

    assert len(repository.published) == 1
    control_membership = _membership_sets(result.control.snapshot)
    grouping_membership = _grouping_membership_sets(result.control.grouping_projection)
    assert control_membership == grouping_membership

    assert len(result.shadow.control_ranking) == len(control_membership)
    assert result.shadow.status.value == "RAN"
    assert result.shadow.experiment_id == PEF_V1_EXPERIMENT_ID
    assert result.shadow.candidate_id == PEF_V1_CANDIDATE_ID
    assert result.shadow.configuration_digest == PEF_V1_CONFIGURATION_DIGEST
    assert result.shadow.episode_universe_digest.value.startswith("sha256:")


def test_v1_control_binds_v1_grouping_configuration_and_episode_identity() -> None:
    repository = _Repository()
    result = run_pef_v1_paired(
        repository,
        as_of=AS_OF,
        generated_at=AS_OF,
        source_registry_version=REGISTRY,
    )
    assert result.control.receipt.configuration_digest == PEF_V1_CONTROL_CONFIGURATION_DIGEST
    for episode in result.control.snapshot.episodes:
        assert episode.episode_id == _expected_v1_episode_id(episode.observation_ids)


def test_v1_grouping_receipt_binds_scalable_algorithm_and_complete_output() -> None:
    repository = _Repository()
    result = run_pef_v1_paired(
        repository,
        as_of=AS_OF,
        generated_at=AS_OF,
        source_registry_version=REGISTRY,
    )
    receipt = result.control.grouping_receipt
    assert receipt.status is ProjectionStatus.COMPLETE
    assert receipt.projection_version == GROUPING_V1_PROJECTION_VERSION
    assert receipt.algorithm_version == GROUPING_V1_ALGORITHM_VERSION
    assert receipt.configuration_digest == GROUPING_V1_CONFIGURATION_DIGEST
    assert receipt.source_registry_version == REGISTRY
    assert result.control.grouping_projection.candidate_pair_count < 3


def test_v1_successor_does_not_mutate_frozen_v0_configuration_identity() -> None:
    assert str(PEF_CONFIGURATION_DIGEST) == (
        "sha256:e2627f62deac24e5f1b09960687761ebbcc61b3fd0c8fec07fec0006dcff7dc1"
    )
    assert PEF_V1_EXPERIMENT_ID == "advanced-ranking-pef-v1"
    assert PEF_V1_CANDIDATE_ID == "prospective-primary-emission-freshness-v1"
