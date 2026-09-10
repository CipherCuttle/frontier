from __future__ import annotations

import subprocess
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path

import pytest

from frontier.application.freeze_publication import CandidateFreezePublication
from frontier.application.pef_v1_confirmatory import (
    PefV1FreezeBinding,
    build_pef_v1_confirmatory_evidence,
    evaluate_pef_v1_confirmatory_gates,
)
from frontier.cli.pef_v1_confirmatory import (
    require_clean_repository_tree,
    require_direct_session_database_url,
)
from frontier.domain.candidate_freeze import FreezeInputs, RegistryEntryDigest
from frontier.domain.candidate_freeze_v1 import build_candidate_freeze_receipt_v1
from frontier.domain.digests import Digest
from frontier.domain.grouping import GroupingInput, GroupingRelationInput
from frontier.domain.health import HealthValue
from frontier.domain.intelligence import (
    BaselineHealthInput,
    BaselineObservationInput,
    BaselineSnapshot,
)
from frontier.domain.pef_v1 import (
    PEF_V1_CANDIDATE_ID,
    PEF_V1_CONFIGURATION_DIGEST,
    PEF_V1_EXPERIMENT_ID,
)
from frontier.domain.receipt import ProjectionReceipt

FROZEN_AT = datetime(2026, 9, 9, 21, 0, tzinfo=UTC)
DURABLE_AT = FROZEN_AT + timedelta(minutes=1)
PUBLICATION_AT = DURABLE_AT + timedelta(minutes=1, seconds=1)
AS_OF = datetime(2026, 9, 9, 21, 5, tzinfo=UTC)
REGISTRY = Digest("sha256:" + "9" * 64)


def _freeze():
    return build_candidate_freeze_receipt_v1(
        FreezeInputs(
            preregistration_digest=Digest("sha256:" + "1" * 64),
            preregistration_config_digest=PEF_V1_CONFIGURATION_DIGEST,
            implementation_commit="a" * 40,
            implementation_tree_digest="b" * 40,
            dependency_lock_digest=Digest("sha256:" + "2" * 64),
            source_registry_digest=Digest("sha256:" + "3" * 64),
            registry_entry_digests=(
                RegistryEntryDigest(
                    path="sources/registry/pypi.updates.v0.json",
                    digest=Digest("sha256:" + "4" * 64),
                ),
            ),
        ),
        frozen_at=FROZEN_AT,
    )


def _binding() -> PefV1FreezeBinding:
    receipt = _freeze()
    publication = CandidateFreezePublication(
        freeze_receipt_id=receipt.receipt_id,
        freeze_receipt_digest=receipt.receipt_digest,
        implementation_commit="a" * 40,
        implementation_tree_digest="b" * 40,
        publication_commit="c" * 40,
        publication_committer_at=PUBLICATION_AT,
    )
    return PefV1FreezeBinding(
        receipt=receipt,
        durable_freeze_at=DURABLE_AT,
        publication_commit=publication.publication_commit,
        publication_committer_at=publication.publication_committer_at,
        publication_digest=publication.publication_digest,
    )


def _obs_id(label: str) -> str:
    return "obs_" + sha256(label.encode()).hexdigest()


def _observation(
    label: str,
    *,
    minutes_ago: int,
    source_id: str,
    role: str,
    url: str,
) -> BaselineObservationInput:
    return BaselineObservationInput(
        grouping=GroupingInput(
            observation_id=_obs_id(label),
            source_id=source_id,
            source_item_key=label,
            kind="DOCUMENT",
            observed_at=AS_OF - timedelta(minutes=minutes_ago),
            canonical_url=url,
            title=label,
            text=label,
            signal_roles=(role,),
        ),
        first_reason="SCHEDULED",
        recovered_after_gap=False,
    )


class _Repository:
    def __init__(self) -> None:
        self.observations = (
            _observation(
                "package emission",
                minutes_ago=1,
                source_id="pypi.updates",
                role="PRIMARY_EMISSION",
                url="https://example.test/package",
            ),
            _observation(
                "attention",
                minutes_ago=2,
                source_id="hn.frontpage",
                role="ATTENTION",
                url="https://example.test/attention",
            ),
        )
        self.enabled = ("hn.frontpage", "pypi.updates")
        self.health = tuple(
            BaselineHealthInput(
                source_id=source_id,
                as_of=AS_OF - timedelta(seconds=1),
                transport=HealthValue.OK,
                freshness=HealthValue.OK,
                completeness=HealthValue.OK,
                schema=HealthValue.OK,
            )
            for source_id in self.enabled
        )
        self.published: list[tuple[BaselineSnapshot, ProjectionReceipt]] = []

    def list_baseline_observations_as_of(self, as_of: datetime) -> list[BaselineObservationInput]:
        return [item for item in self.observations if item.observed_at <= as_of]

    def list_grouping_relations_as_of(self, as_of: datetime) -> list[GroupingRelationInput]:
        del as_of
        return []

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


def test_confirmatory_gate_requires_exact_published_v1_authority() -> None:
    allowed, reason = evaluate_pef_v1_confirmatory_gates(
        _binding(),
        as_of=AS_OF,
        canonical_context=True,
    )
    assert allowed is True
    assert reason == "all PEF_V1 confirmatory binding gates hold"

    no_publication = PefV1FreezeBinding(
        receipt=_freeze(),
        durable_freeze_at=DURABLE_AT,
        publication_commit=None,
        publication_committer_at=None,
        publication_digest=None,
    )
    allowed, reason = evaluate_pef_v1_confirmatory_gates(
        no_publication,
        as_of=AS_OF,
        canonical_context=True,
    )
    assert allowed is False
    assert "no verified Git publication" in reason


def test_confirmatory_boundary_cannot_precede_first_post_publication_boundary() -> None:
    allowed, reason = evaluate_pef_v1_confirmatory_gates(
        _binding(),
        as_of=datetime(2026, 9, 9, 21, 0, tzinfo=UTC),
        canonical_context=True,
    )
    assert allowed is False
    assert "outside the fixed preregistered ranking window" in reason


def test_confirmatory_evidence_binds_freeze_without_publishing_public_baseline() -> None:
    repository = _Repository()
    freeze = _freeze()
    evidence = build_pef_v1_confirmatory_evidence(
        repository,
        as_of=AS_OF,
        generated_at=AS_OF,
        source_registry_version=REGISTRY,
        freeze_receipt=freeze,
    )
    assert repository.published == []
    assert evidence.run.experiment_id == PEF_V1_EXPERIMENT_ID
    assert evidence.run.candidate_id == PEF_V1_CANDIDATE_ID
    assert evidence.run.configuration_digest == PEF_V1_CONFIGURATION_DIGEST
    assert evidence.run.candidate_freeze_receipt_id == freeze.receipt_id
    assert evidence.candidate_artifact.grouping_receipt_id == evidence.grouping_receipt.receipt_id
    assert evidence.candidate_artifact.control_receipt_id == evidence.control_receipt.receipt_id


def test_direct_session_endpoint_guard_rejects_neon_transaction_pooler() -> None:
    with pytest.raises(ValueError, match="forbids transaction-pooler"):
        require_direct_session_database_url(
            "postgresql://user:pass@ep-example-pooler.eu-central-1.aws.neon.tech/frontier"
        )
    host = require_direct_session_database_url(
        "postgresql://user:pass@ep-example.eu-central-1.aws.neon.tech/frontier?sslmode=require"
    )
    assert host == "ep-example.eu-central-1.aws.neon.tech"


def test_confirmatory_operator_rejects_dirty_git_worktree(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-b", "main"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "frontier@example.test"],
        cwd=tmp_path,
        check=True,
    )
    subprocess.run(["git", "config", "user.name", "Frontier Test"], cwd=tmp_path, check=True)
    tracked = tmp_path / "tracked.txt"
    tracked.write_text("frozen\n", encoding="utf-8")
    subprocess.run(["git", "add", "tracked.txt"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "frozen"], cwd=tmp_path, check=True, capture_output=True)

    require_clean_repository_tree(tmp_path)

    tracked.write_text("dirty\n", encoding="utf-8")
    with pytest.raises(ValueError, match="forbids a dirty Git worktree"):
        require_clean_repository_tree(tmp_path)

    subprocess.run(["git", "restore", "tracked.txt"], cwd=tmp_path, check=True)
    (tmp_path / "untracked.txt").write_text("dirty\n", encoding="utf-8")
    with pytest.raises(ValueError, match="forbids a dirty Git worktree"):
        require_clean_repository_tree(tmp_path)
