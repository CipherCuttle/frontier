from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import cast

import pytest

from frontier.application.advanced_intelligence import (
    PefRankingRun,
    run_pef_v0_ranking,
    run_shadow_experiment,
)
from frontier.application.candidate_freeze import (
    collect_freeze_inputs,
    freeze_candidate,
    verify_freeze,
)
from frontier.domain.advanced_intelligence import (
    PEF_CANDIDATE_ID,
    PEF_CONFIGURATION_DIGEST,
    PEF_EXPERIMENT_ID,
    ShadowRunStatus,
    build_shadow_experiment_run,
)
from frontier.domain.candidate_freeze import (
    FREEZE_DEPENDENCY_LOCK_PATH,
    FREEZE_PREREGISTRATION_PATH,
    FREEZE_RECEIPT_ID_PREFIX,
    FREEZE_SCHEMA_VERSION,
    FREEZE_SOURCE_REGISTRY_PATH,
    CandidateFreezeReceipt,
    FreezeInputs,
    FreezeStatus,
    RegistryEntryDigest,
    build_candidate_freeze_receipt,
    verify_candidate_freeze,
)
from frontier.domain.canonical_json import canonical_json_bytes
from frontier.domain.digests import Digest, sha256_digest
from frontier.domain.grouping import EpisodeGroup, GroupingInput, GroupingProjection
from frontier.domain.health import HealthValue
from frontier.domain.intelligence import (
    BaselineHealthInput,
    BaselineObservationInput,
    BaselineSnapshot,
    build_baseline_receipt,
    build_baseline_snapshot,
)
from frontier.domain.receipt import ProjectionReceipt

REPO_ROOT = Path(__file__).resolve().parents[2]
AS_OF = datetime(2026, 9, 5, 12, tzinfo=UTC)
GENERATED_AT = AS_OF
FROZEN_AT = datetime(2026, 9, 5, 12, tzinfo=UTC)
VERIFIED_AT = FROZEN_AT
FAKE_COMMIT = "a" * 40
FAKE_TREE = "b" * 40
REGISTRY = Digest("sha256:" + "1" * 64)


def _live_digest(path: Path) -> Digest:
    return sha256_digest(path.read_bytes())


def _healthy_inputs() -> FreezeInputs:
    return FreezeInputs(
        preregistration_digest=_live_digest(REPO_ROOT / FREEZE_PREREGISTRATION_PATH),
        preregistration_config_digest=PEF_CONFIGURATION_DIGEST,
        implementation_commit=FAKE_COMMIT,
        implementation_tree_digest=FAKE_TREE,
        dependency_lock_digest=_live_digest(REPO_ROOT / FREEZE_DEPENDENCY_LOCK_PATH),
        source_registry_digest=_live_digest(REPO_ROOT / FREEZE_SOURCE_REGISTRY_PATH),
        registry_entry_digests=(
            RegistryEntryDigest(
                path="sources/registry/cisa.kev.v0.json", digest=Digest("sha256:" + "c" * 64)
            ),
            RegistryEntryDigest(
                path="sources/registry/hn.frontpage.v0.json", digest=Digest("sha256:" + "d" * 64)
            ),
        ),
    )


def test_freeze_receipt_is_deterministic_for_identical_inputs() -> None:
    receipt = build_candidate_freeze_receipt(_healthy_inputs(), frozen_at=FROZEN_AT)
    again = build_candidate_freeze_receipt(_healthy_inputs(), frozen_at=FROZEN_AT)
    assert receipt == again
    assert receipt.receipt_digest == again.receipt_digest
    assert receipt.receipt_id == again.receipt_id
    different_time = build_candidate_freeze_receipt(
        _healthy_inputs(), frozen_at=FROZEN_AT.replace(microsecond=1)
    )
    assert different_time.receipt_digest != receipt.receipt_digest
    assert receipt.receipt_id.startswith(FREEZE_RECEIPT_ID_PREFIX)


def test_healthy_inputs_freeze_frozen_and_bind_preregistration() -> None:
    receipt = build_candidate_freeze_receipt(_healthy_inputs(), frozen_at=FROZEN_AT)
    assert receipt.status is FreezeStatus.FROZEN
    assert receipt.drift_reasons == ()
    assert receipt.schema_version == FREEZE_SCHEMA_VERSION == "candidate-freeze-receipt-v0"
    assert receipt.candidate_id == PEF_CANDIDATE_ID
    assert receipt.experiment_id == PEF_EXPERIMENT_ID
    assert receipt.configuration_digest == PEF_CONFIGURATION_DIGEST
    assert receipt.preregistration_digest == _live_digest(REPO_ROOT / FREEZE_PREREGISTRATION_PATH)
    assert receipt.preregistration_path == FREEZE_PREREGISTRATION_PATH
    assert receipt.dependency_lock_digest == _live_digest(REPO_ROOT / FREEZE_DEPENDENCY_LOCK_PATH)
    assert receipt.receipt_digest == sha256_digest(canonical_json_bytes(receipt.to_canonical()))
    assert receipt.receipt_id == (
        FREEZE_RECEIPT_ID_PREFIX + sha256(canonical_json_bytes(receipt.to_canonical())).hexdigest()
    )


def test_preregistration_config_digest_mismatch_drifts_fail_closed() -> None:
    drifted = replace(_healthy_inputs(), preregistration_config_digest=Digest("sha256:" + "0" * 64))
    receipt = build_candidate_freeze_receipt(drifted, frozen_at=FROZEN_AT)
    assert receipt.status is FreezeStatus.DRIFTED
    assert any(
        "preregistration configuration digest drifted" in reason for reason in receipt.drift_reasons
    )


def test_missing_preregistration_config_digest_drifts_fail_closed() -> None:
    drifted = replace(_healthy_inputs(), preregistration_config_digest=None)
    receipt = build_candidate_freeze_receipt(drifted, frozen_at=FROZEN_AT)
    assert receipt.status is FreezeStatus.DRIFTED
    assert any("unavailable" in reason for reason in receipt.drift_reasons)


def test_freeze_time_build_records_concrete_components_and_flags_only_absence() -> None:
    # Any concrete component value is recorded at freeze time (the receipt binds
    # what it observed); drift for these components is detection at verification
    # time by recomputation (see test_verify_flags_every_component_drift).
    mutated = replace(
        _healthy_inputs(),
        dependency_lock_digest=Digest("sha256:" + "1" * 64),
        source_registry_digest=Digest("sha256:" + "2" * 64),
        implementation_commit="f" * 40,
    )
    receipt = build_candidate_freeze_receipt(mutated, frozen_at=FROZEN_AT)
    assert receipt.status is FreezeStatus.FROZEN
    assert receipt.dependency_lock_digest == Digest("sha256:" + "1" * 64)
    assert receipt.source_registry_digest == Digest("sha256:" + "2" * 64)
    assert receipt.implementation_commit == "f" * 40


def test_missing_git_metadata_fails_closed_without_fabrication() -> None:
    receipt = build_candidate_freeze_receipt(
        replace(_healthy_inputs(), implementation_commit=None, implementation_tree_digest=None),
        frozen_at=FROZEN_AT,
    )
    assert receipt.status is FreezeStatus.DRIFTED
    assert receipt.implementation_commit is None
    assert receipt.implementation_tree_digest is None
    assert any(
        "implementation commit/tree digest unavailable" in reason
        for reason in receipt.drift_reasons
    )


def test_missing_files_fail_closed_without_fabrication() -> None:
    receipt = build_candidate_freeze_receipt(
        FreezeInputs(
            preregistration_digest=_live_digest(REPO_ROOT / FREEZE_PREREGISTRATION_PATH),
            preregistration_config_digest=PEF_CONFIGURATION_DIGEST,
            implementation_commit=FAKE_COMMIT,
            implementation_tree_digest=FAKE_TREE,
            dependency_lock_digest=None,
            source_registry_digest=None,
            registry_entry_digests=None,
        ),
        frozen_at=FROZEN_AT,
    )
    assert receipt.status is FreezeStatus.DRIFTED
    assert any("dependency lock digest unavailable" in reason for reason in receipt.drift_reasons)
    assert any("source registry digest unavailable" in reason for reason in receipt.drift_reasons)


def test_verify_clean_recomputation_stays_frozen_and_binds_original() -> None:
    receipt = build_candidate_freeze_receipt(_healthy_inputs(), frozen_at=FROZEN_AT)
    verification = verify_candidate_freeze(
        receipt, inputs=_healthy_inputs(), verified_at=VERIFIED_AT
    )
    assert verification.status is FreezeStatus.FROZEN
    assert verification.drift_reasons == ()
    assert verification.verified_at == VERIFIED_AT
    assert verification.original_receipt_digest == receipt.receipt_digest
    assert verification.preregistration_digest == receipt.preregistration_digest
    assert verification.receipt_id != receipt.receipt_id


@pytest.mark.parametrize(
    ("field", "value", "label"),
    [
        (
            "preregistration_digest",
            Digest("sha256:" + "0" * 64),
            "preregistration file digest",
        ),
        (
            "preregistration_config_digest",
            Digest("sha256:" + "0" * 64),
            "preregistration configuration digest",
        ),
        ("implementation_commit", "f" * 40, "implementation commit"),
        ("implementation_tree_digest", "f" * 40, "implementation tree digest"),
        ("dependency_lock_digest", Digest("sha256:" + "1" * 64), "dependency lock digest"),
        ("source_registry_digest", Digest("sha256:" + "2" * 64), "source registry digest"),
        (
            "registry_entry_digests",
            (
                RegistryEntryDigest(
                    path="sources/registry/cisa.kev.v0.json",
                    digest=Digest("sha256:" + "d" * 64),
                ),
                RegistryEntryDigest(
                    path="sources/registry/hn.frontpage.v0.json",
                    digest=Digest("sha256:" + "c" * 64),
                ),
            ),
            "source registry entry digests",
        ),
    ],
)
def test_verify_flags_every_component_drift(field: str, value: object, label: str) -> None:
    receipt = build_candidate_freeze_receipt(_healthy_inputs(), frozen_at=FROZEN_AT)
    drifted_inputs = _drifted_inputs(field, value)
    verification = verify_candidate_freeze(receipt, inputs=drifted_inputs, verified_at=VERIFIED_AT)
    assert verification.status is FreezeStatus.DRIFTED
    assert any(label in reason for reason in verification.drift_reasons)


def _drifted_inputs(field: str, value: object) -> FreezeInputs:
    healthy = _healthy_inputs()
    if field == "preregistration_digest":
        assert isinstance(value, Digest)
        return replace(healthy, preregistration_digest=value)
    if field == "preregistration_config_digest":
        assert isinstance(value, Digest)
        return replace(healthy, preregistration_config_digest=value)
    if field == "implementation_commit":
        assert isinstance(value, str)
        return replace(healthy, implementation_commit=value)
    if field == "implementation_tree_digest":
        assert isinstance(value, str)
        return replace(healthy, implementation_tree_digest=value)
    if field == "dependency_lock_digest":
        assert isinstance(value, Digest)
        return replace(healthy, dependency_lock_digest=value)
    if field == "source_registry_digest":
        assert isinstance(value, Digest)
        return replace(healthy, source_registry_digest=value)
    assert isinstance(value, tuple)
    return replace(healthy, registry_entry_digests=cast("tuple[RegistryEntryDigest, ...]", value))


def test_verify_of_previously_drifted_freeze_stays_drifted() -> None:
    drifted = replace(_healthy_inputs(), dependency_lock_digest=None)
    original = build_candidate_freeze_receipt(drifted, frozen_at=FROZEN_AT)
    assert original.status is FreezeStatus.DRIFTED
    verification = verify_candidate_freeze(
        original, inputs=_healthy_inputs(), verified_at=VERIFIED_AT
    )
    assert verification.status is FreezeStatus.DRIFTED
    assert any(
        "original freeze receipt recorded DRIFTED" in reason
        for reason in verification.drift_reasons
    )


def test_frozen_cannot_carry_drift_reasons_and_drifted_requires_them() -> None:
    with pytest.raises(ValueError, match="FROZEN freeze receipt cannot carry drift reasons"):
        _receipt(status=FreezeStatus.FROZEN, drift_reasons=("reason",))
    with pytest.raises(ValueError, match="DRIFTED freeze receipt requires explicit drift reasons"):
        _receipt(status=FreezeStatus.DRIFTED, drift_reasons=())


def _receipt(*, status: FreezeStatus, drift_reasons: tuple[str, ...]) -> CandidateFreezeReceipt:
    return CandidateFreezeReceipt(
        frozen_at=FROZEN_AT,
        status=status,
        drift_reasons=drift_reasons,
        preregistration_digest=Digest("sha256:" + "0" * 64),
        preregistration_config_digest=PEF_CONFIGURATION_DIGEST,
        implementation_commit=FAKE_COMMIT,
        implementation_tree_digest=FAKE_TREE,
        dependency_lock_digest=Digest("sha256:" + "1" * 64),
        source_registry_digest=Digest("sha256:" + "2" * 64),
        registry_entry_digests=(),
    )


def test_collect_freeze_inputs_binds_live_preregistration_and_lock() -> None:
    inputs = collect_freeze_inputs(REPO_ROOT)
    assert inputs.preregistration_digest == _live_digest(REPO_ROOT / FREEZE_PREREGISTRATION_PATH)
    assert inputs.dependency_lock_digest == _live_digest(REPO_ROOT / FREEZE_DEPENDENCY_LOCK_PATH)
    assert inputs.source_registry_digest == _live_digest(REPO_ROOT / FREEZE_SOURCE_REGISTRY_PATH)
    assert inputs.registry_entry_digests is not None and inputs.registry_entry_digests
    assert inputs.implementation_commit is not None
    assert inputs.implementation_tree_digest is not None
    # The live preregistration document must agree with the frozen configuration.
    assert inputs.preregistration_config_digest == PEF_CONFIGURATION_DIGEST
    receipt = freeze_candidate(REPO_ROOT, frozen_at=FROZEN_AT)
    assert receipt.status is FreezeStatus.FROZEN
    assert receipt.preregistration_config_digest == PEF_CONFIGURATION_DIGEST
    assert (
        verify_freeze(receipt, root=REPO_ROOT, verified_at=VERIFIED_AT).status
        is FreezeStatus.FROZEN
    )


def test_run_shadow_experiment_rejects_drifted_freeze_binding() -> None:
    drifted_receipt = build_candidate_freeze_receipt(
        replace(_healthy_inputs(), dependency_lock_digest=None), frozen_at=FROZEN_AT
    )
    assert drifted_receipt.status is FreezeStatus.DRIFTED
    observations = _observations()
    snapshot, control = _control(observations)
    with pytest.raises(ValueError, match="drifted candidate freeze receipt"):
        run_shadow_experiment(
            tuple(observations),
            control_snapshot=snapshot,
            control_receipt=control,
            generated_at=GENERATED_AT,
            source_registry_version=REGISTRY,
            candidate_freeze_receipt=drifted_receipt,
        )


def test_run_shadow_experiment_binds_frozen_freeze_receipt() -> None:
    receipt = build_candidate_freeze_receipt(_healthy_inputs(), frozen_at=FROZEN_AT)
    observations = _observations()
    snapshot, control = _control(observations)
    candidate = _candidate(observations, snapshot, control)
    run = run_shadow_experiment(
        tuple(observations),
        control_snapshot=snapshot,
        control_receipt=control,
        generated_at=GENERATED_AT,
        source_registry_version=REGISTRY,
        candidate_freeze_receipt=receipt,
    )
    assert run.status is ShadowRunStatus.RAN
    assert run.candidate_freeze_receipt_id == receipt.receipt_id
    without_freeze = build_shadow_experiment_run(
        control_snapshot=snapshot,
        control_receipt=control,
        candidate_artifact=candidate.artifact,
        candidate_receipt=candidate.receipt,
        as_of=snapshot.as_of,
        generated_at=GENERATED_AT,
    )
    assert without_freeze.candidate_freeze_receipt_id is None
    assert without_freeze.run_id != run.run_id


def test_shadow_run_rejects_malformed_freeze_receipt_id() -> None:
    observations = _observations()
    snapshot, control = _control(observations)
    candidate = _candidate(observations, snapshot, control)
    with pytest.raises(ValueError, match="invalid candidate freeze receipt id"):
        build_shadow_experiment_run(
            control_snapshot=snapshot,
            control_receipt=control,
            candidate_artifact=candidate.artifact,
            candidate_receipt=candidate.receipt,
            as_of=snapshot.as_of,
            generated_at=GENERATED_AT,
            candidate_freeze_receipt_id="not-a-freeze-receipt-id",
        )


def _obs_id(label: str) -> str:
    return "obs_" + sha256(label.encode()).hexdigest()


def _observations() -> list[BaselineObservationInput]:
    live = BaselineObservationInput(
        grouping=GroupingInput(
            observation_id=_obs_id("freeze-live"),
            source_id="fixture.primary",
            source_item_key="freeze-live",
            kind="DOCUMENT",
            observed_at=AS_OF - timedelta(minutes=1),
            canonical_url="https://example.test/freeze-live",
            title="Freeze fixture episode title",
            text=None,
            signal_roles=("PRIMARY_EMISSION",),
        ),
        first_reason="SCHEDULED",
        recovered_after_gap=False,
    )
    return [live]


def _health() -> BaselineHealthInput:
    return BaselineHealthInput(
        source_id="fixture.primary",
        as_of=AS_OF - timedelta(minutes=1),
        transport=HealthValue.OK,
        freshness=HealthValue.OK,
        completeness=HealthValue.OK,
        schema=HealthValue.OK,
    )


def _control(
    observations: list[BaselineObservationInput],
) -> tuple[BaselineSnapshot, ProjectionReceipt]:
    eligible = [item for item in observations if item.observed_at <= AS_OF]
    projection = GroupingProjection(
        as_of=AS_OF,
        groups=(
            EpisodeGroup(
                group_id="grp_" + "0" * 64,
                observation_ids=tuple(sorted(item.observation_id for item in eligible)),
            ),
        ),
        ambiguous_pairs=(),
        ungrouped_observation_ids=(),
    )
    snapshot = build_baseline_snapshot(
        observations,
        grouping_projection=projection,
        enabled_source_ids=("fixture.primary",),
        health=(_health(),),
        as_of=AS_OF,
    )
    receipt = build_baseline_receipt(
        snapshot,
        observations=observations,
        grouping_projection=projection,
        enabled_source_ids=("fixture.primary",),
        health=(_health(),),
        generated_at=GENERATED_AT,
        source_registry_version=REGISTRY,
    )
    return snapshot, receipt


def _candidate(
    observations: list[BaselineObservationInput],
    snapshot: BaselineSnapshot,
    control: ProjectionReceipt,
) -> PefRankingRun:
    return run_pef_v0_ranking(
        tuple(observations),
        control_snapshot=snapshot,
        control_receipt=control,
        generated_at=GENERATED_AT,
        source_registry_version=REGISTRY,
    )
