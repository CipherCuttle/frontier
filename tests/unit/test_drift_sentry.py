"""Unit tests for the PEF_V0 candidate-freeze drift sentry (WP5, G7).

Covers: the OK case over the full identity tuple; every component mutated
independently → DRIFTED with the exact reason; orchestrator confirmatory
SKIPPED; evaluator INVALID_DRIFT; DEV-run immunity; and the fail-closed
guarantee that the sentry never mutates receipts or stored state.
"""

from __future__ import annotations

from dataclasses import fields, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import pytest
from test_evaluation_loaders import (
    DURABLE_AT,
    _default_store,  # pyright: ignore[reportPrivateUsage]
    _paired,  # pyright: ignore[reportPrivateUsage]
    _seed,  # pyright: ignore[reportPrivateUsage]
    _seed_freeze,  # pyright: ignore[reportPrivateUsage]
    _seed_publication,  # pyright: ignore[reportPrivateUsage]
)
from test_experiment_orchestration import (
    FakeAttemptRepository,
    FakeBaselineRepository,
    FakeShadowRunPersistence,
    RecordingRunner,
    StubBindingResolver,
    _observations,  # pyright: ignore[reportPrivateUsage]
)

from frontier.application.candidate_freeze import freeze_candidate
from frontier.application.drift_sentry import DriftSentry
from frontier.application.evaluation import evaluate_shadow_experiment_from_persisted
from frontier.application.evaluation_loaders import PersistedRunRef
from frontier.application.experiment_orchestration import (
    ExperimentCycleAction,
    ExperimentOrchestrator,
    FreezeBinding,
)
from frontier.application.experiment_status import build_experiment_status
from frontier.application.freeze_publication import first_confirmatory_boundary
from frontier.domain.candidate_freeze import (
    CandidateFreezeReceipt,
    FreezeInputs,
    FreezeStatus,
    build_candidate_freeze_receipt,
)
from frontier.domain.digests import Digest
from frontier.domain.drift_sentry import (
    COMPARATOR_BASELINE_PROJECTION_VERSION,
    COMPARATOR_BASELINE_RANKING_POLICY_VERSION,
    DriftComponent,
    DriftReport,
    DriftStatus,
)
from frontier.domain.experiment_status import (
    DRIFT_STATE_INVALID_DRIFT,
    DRIFT_STATE_OK,
    BoundFreezeStatus,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
FROZEN_AT = datetime(2026, 9, 1, 0, 0, tzinfo=UTC)
NOW = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)
FABRICATED_REGISTRY = Digest("sha256:" + "3" * 64)
PEF_CONFIG_DIGEST = Digest(
    "sha256:e2627f62deac24e5f1b09960687761ebbcc61b3fd0c8fec07fec0006dcff7dc1"
)

FULL_IDENTITY_COMPONENTS: frozenset[str] = frozenset(
    {
        "candidate_id",
        "experiment_id",
        "algorithm_version",
        "configuration_digest",
        "preregistration_digest",
        "preregistration_config_digest",
        "implementation_commit",
        "implementation_tree_digest",
        "dependency_lock_digest",
        "source_registry_digest",
        "source_registry_entry_digests",
        "freeze_status",
        "comparator_identity",
    }
)


def _mutated(receipt: CandidateFreezeReceipt, **changes: object) -> CandidateFreezeReceipt:
    """A receipt copy with identity fields replaced (bypassing the frozen PEF
    identity validation on purpose: the sentry must detect tampered values)."""
    clone = CandidateFreezeReceipt.__new__(CandidateFreezeReceipt)
    for field in fields(receipt):  # pyright: ignore[reportUnknownArgumentType, reportAny]
        object.__setattr__(clone, field.name, changes.get(field.name, getattr(receipt, field.name)))  # pyright: ignore[reportUnknownMemberType, reportAny]
    return clone


def _fabricated_frozen() -> CandidateFreezeReceipt:
    return build_candidate_freeze_receipt(
        FreezeInputs(
            preregistration_digest=Digest("sha256:" + "1" * 64),
            preregistration_config_digest=PEF_CONFIG_DIGEST,
            implementation_commit="a" * 64,
            implementation_tree_digest="b" * 64,
            dependency_lock_digest=Digest("sha256:" + "2" * 64),
            source_registry_digest=FABRICATED_REGISTRY,
            registry_entry_digests=(),
        ),
        frozen_at=FROZEN_AT,
    )


def _reason(component: DriftComponent) -> str:
    assert component.reason is not None
    return component.reason


def _drifted_report(reason: str) -> DriftReport:
    return DriftReport(
        checked_at=NOW,
        components=(
            DriftComponent(
                component="dependency_lock_digest",
                expected="sha256:x",
                actual="sha256:y",
                drifted=True,
                reason=reason,
            ),
        ),
    )


_OK_REPORT = DriftReport(checked_at=NOW, components=())


# ---------------------------------------------------------------------------
# OK case.
# ---------------------------------------------------------------------------


class TestSentryOk:
    def test_ok_report_for_a_frozen_receipt_taken_from_the_live_root(self) -> None:
        receipt = freeze_candidate(REPO_ROOT, frozen_at=FROZEN_AT)
        assert receipt.status is FreezeStatus.FROZEN
        report = DriftSentry(REPO_ROOT).check(receipt, now=NOW)
        assert report.status is DriftStatus.OK
        assert report.reasons == ()
        assert not report.drifted

    def test_ok_report_covers_the_full_identity_tuple(self) -> None:
        receipt = freeze_candidate(REPO_ROOT, frozen_at=FROZEN_AT)
        report = DriftSentry(REPO_ROOT).check(receipt, now=NOW)
        names = {component.component for component in report.components}
        assert names >= FULL_IDENTITY_COMPONENTS

    def test_ok_report_compares_the_seven_frozen_registry_entries(self) -> None:
        receipt = freeze_candidate(REPO_ROOT, frozen_at=FROZEN_AT)
        assert receipt.registry_entry_digests is not None
        assert len(receipt.registry_entry_digests) == 7
        report = DriftSentry(REPO_ROOT).check(receipt, now=NOW)
        entry_components = [
            component
            for component in report.components
            if component.component.startswith("registry_entry[")
        ]
        assert len(entry_components) == 7
        assert all(not component.drifted for component in entry_components)

    def test_verify_receipt_is_frozen_when_live_matches(self) -> None:
        receipt = freeze_candidate(REPO_ROOT, frozen_at=FROZEN_AT)
        verified = DriftSentry(REPO_ROOT).verify_receipt(receipt, now=NOW)
        assert verified.status is FreezeStatus.FROZEN
        assert verified.verified_at == NOW
        assert verified.original_receipt_digest == receipt.receipt_digest

    def test_sentry_never_mutates_the_receipt_or_adopts_state(self) -> None:
        receipt = freeze_candidate(REPO_ROOT, frozen_at=FROZEN_AT)
        before = receipt.to_canonical()
        sentry = DriftSentry(REPO_ROOT)
        sentry.check(receipt, now=NOW)
        sentry.verify_receipt(receipt, now=NOW)
        assert receipt.to_canonical() == before
        assert receipt.verified_at is None
        assert receipt.original_receipt_digest is None
        assert receipt.status is FreezeStatus.FROZEN


# ---------------------------------------------------------------------------
# Per-component drift (fabricated FROZEN receipt vs the live repository).
# ---------------------------------------------------------------------------


class TestPerComponentDrift:
    def test_candidate_id_drift(self) -> None:
        receipt = _mutated(_fabricated_frozen(), candidate_id="drifted-candidate")
        report = DriftSentry(REPO_ROOT).check(receipt, now=NOW)
        component = report.component("candidate_id")
        assert component is not None and component.drifted
        assert "candidate_id mismatch" in _reason(component)
        assert component.actual == "drifted-candidate"

    def test_experiment_id_drift(self) -> None:
        receipt = _mutated(_fabricated_frozen(), experiment_id="drifted-experiment")
        report = DriftSentry(REPO_ROOT).check(receipt, now=NOW)
        component = report.component("experiment_id")
        assert component is not None and component.drifted
        assert "experiment_id mismatch" in _reason(component)

    def test_algorithm_version_drift(self) -> None:
        receipt = _mutated(_fabricated_frozen(), algorithm_version="drifted-algorithm")
        report = DriftSentry(REPO_ROOT).check(receipt, now=NOW)
        component = report.component("algorithm_version")
        assert component is not None and component.drifted
        assert "algorithm_version mismatch" in _reason(component)

    def test_configuration_digest_drift(self) -> None:
        receipt = _mutated(_fabricated_frozen(), configuration_digest=Digest("sha256:" + "9" * 64))
        report = DriftSentry(REPO_ROOT).check(receipt, now=NOW)
        component = report.component("configuration_digest")
        assert component is not None and component.drifted
        assert "configuration digest mismatch" in _reason(component)

    def test_preregistration_digest_drift(self) -> None:
        receipt = _mutated(
            _fabricated_frozen(), preregistration_digest=Digest("sha256:" + "9" * 64)
        )
        report = DriftSentry(REPO_ROOT).check(receipt, now=NOW)
        component = report.component("preregistration_digest")
        assert component is not None and component.drifted
        assert "preregistration_digest drifted from the live repository state" in _reason(component)

    def test_preregistration_config_digest_drift(self) -> None:
        receipt = _mutated(
            _fabricated_frozen(), preregistration_config_digest=Digest("sha256:" + "9" * 64)
        )
        report = DriftSentry(REPO_ROOT).check(receipt, now=NOW)
        component = report.component("preregistration_config_digest")
        assert component is not None and component.drifted
        assert "preregistration_config_digest drifted" in _reason(component)

    def test_implementation_commit_drift(self) -> None:
        receipt = _mutated(_fabricated_frozen(), implementation_commit="0" * 64)
        report = DriftSentry(REPO_ROOT).check(receipt, now=NOW)
        component = report.component("implementation_commit")
        assert component is not None and component.drifted
        assert "implementation_commit drifted" in _reason(component)

    def test_implementation_tree_digest_drift(self) -> None:
        receipt = _mutated(_fabricated_frozen(), implementation_tree_digest="0" * 64)
        report = DriftSentry(REPO_ROOT).check(receipt, now=NOW)
        component = report.component("implementation_tree_digest")
        assert component is not None and component.drifted
        assert "implementation_tree_digest drifted" in _reason(component)

    def test_dependency_lock_digest_drift(self) -> None:
        receipt = _mutated(
            _fabricated_frozen(), dependency_lock_digest=Digest("sha256:" + "9" * 64)
        )
        report = DriftSentry(REPO_ROOT).check(receipt, now=NOW)
        component = report.component("dependency_lock_digest")
        assert component is not None and component.drifted
        assert "dependency_lock_digest drifted" in _reason(component)

    def test_source_registry_digest_drift(self) -> None:
        receipt = _mutated(
            _fabricated_frozen(), source_registry_digest=Digest("sha256:" + "9" * 64)
        )
        report = DriftSentry(REPO_ROOT).check(receipt, now=NOW)
        component = report.component("source_registry_digest")
        assert component is not None and component.drifted
        assert "source_registry_digest drifted" in _reason(component)

    def test_single_registry_entry_digest_drift(self) -> None:
        receipt = freeze_candidate(REPO_ROOT, frozen_at=FROZEN_AT)
        entries = receipt.registry_entry_digests
        assert entries is not None and entries
        first = entries[0]
        mutated_entries = (
            type(first)(path=first.path, digest=Digest("sha256:" + "9" * 64)),
            *entries[1:],
        )
        report = DriftSentry(REPO_ROOT).check(
            _mutated(receipt, registry_entry_digests=mutated_entries), now=NOW
        )
        component = report.component(f"registry_entry[{first.path}]")
        assert component is not None and component.drifted
        assert "drifted from the live source registry entry" in _reason(component)

    def test_missing_registry_entry_path_drift(self) -> None:
        receipt = freeze_candidate(REPO_ROOT, frozen_at=FROZEN_AT)
        entries = receipt.registry_entry_digests
        assert entries is not None and entries
        ghost = type(entries[0])(
            path="sources/registry/ghost.v0.json", digest=Digest("sha256:" + "8" * 64)
        )
        report = DriftSentry(REPO_ROOT).check(
            _mutated(receipt, registry_entry_digests=(*entries, ghost)), now=NOW
        )
        component = report.component("registry_entry[sources/registry/ghost.v0.json]")
        assert component is not None and component.drifted
        assert "missing from the live source registry" in _reason(component)

    def test_unavailable_live_component_is_explicit_drift(self) -> None:
        receipt = freeze_candidate(REPO_ROOT, frozen_at=FROZEN_AT)
        live = DriftSentry(REPO_ROOT).collect()
        inputs = replace(live, dependency_lock_digest=None)
        report = DriftSentry(REPO_ROOT).check(receipt, now=NOW, inputs=inputs)
        component = report.component("dependency_lock_digest")
        assert component is not None and component.drifted
        assert "unavailable in the live repository state" in _reason(component)

    def test_unbound_receipt_component_is_explicit_drift(self) -> None:
        receipt = build_candidate_freeze_receipt(
            FreezeInputs(
                preregistration_digest=Digest("sha256:" + "1" * 64),
                preregistration_config_digest=PEF_CONFIG_DIGEST,
                implementation_commit="a" * 64,
                implementation_tree_digest="b" * 64,
                dependency_lock_digest=None,
                source_registry_digest=FABRICATED_REGISTRY,
                registry_entry_digests=(),
            ),
            frozen_at=FROZEN_AT,
        )
        assert receipt.status is FreezeStatus.DRIFTED
        report = DriftSentry(REPO_ROOT).check(receipt, now=NOW)
        component = report.component("dependency_lock_digest")
        assert component is not None and component.drifted
        assert "was not bound in the original freeze receipt" in _reason(component)
        status_component = report.component("freeze_status")
        assert status_component is not None and status_component.drifted

    def test_drifted_original_receipt_never_renders_ok(self) -> None:
        receipt = _mutated(
            _fabricated_frozen(),
            status=FreezeStatus.DRIFTED,
            drift_reasons=("original freeze receipt recorded DRIFTED",),
        )
        report = DriftSentry(REPO_ROOT).check(receipt, now=NOW)
        assert report.status is DriftStatus.DRIFTED
        assert "bound freeze receipt recorded DRIFTED" in report.reasons


# ---------------------------------------------------------------------------
# Comparator identity.
# ---------------------------------------------------------------------------


class TestComparatorIdentity:
    def test_comparator_identity_is_ok_for_the_frozen_constants(self) -> None:
        assert COMPARATOR_BASELINE_PROJECTION_VERSION == "baseline-intelligence-v0"
        assert COMPARATOR_BASELINE_RANKING_POLICY_VERSION == "naive-episode-activity-v0"
        receipt = freeze_candidate(REPO_ROOT, frozen_at=FROZEN_AT)
        report = DriftSentry(REPO_ROOT).check(receipt, now=NOW)
        component = report.component("comparator_identity")
        assert component is not None and not component.drifted

    def test_comparator_identity_drifts_when_a_constant_changes(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "frontier.domain.intelligence.BASELINE_PROJECTION_VERSION",
            "baseline-intelligence-DRIFTED",
        )
        receipt = freeze_candidate(REPO_ROOT, frozen_at=FROZEN_AT)
        report = DriftSentry(REPO_ROOT).check(receipt, now=NOW)
        component = report.component("comparator_identity")
        assert component is not None and component.drifted
        assert "comparator_identity drifted" in _reason(component)


# ---------------------------------------------------------------------------
# Fail-closed collection.
# ---------------------------------------------------------------------------


class TestFailClosedCollection:
    def test_uncollectable_inputs_fail_closed_with_an_explicit_reason(self, tmp_path: Path) -> None:
        receipt = freeze_candidate(REPO_ROOT, frozen_at=FROZEN_AT)
        report = DriftSentry(tmp_path).check(receipt, now=NOW)
        assert report.status is DriftStatus.DRIFTED
        component = report.component("live_freeze_inputs")
        assert component is not None and component.drifted
        assert "could not be collected (fail-closed)" in _reason(component)

    def test_verify_receipt_fails_closed_without_adopting_state(self, tmp_path: Path) -> None:
        receipt = freeze_candidate(REPO_ROOT, frozen_at=FROZEN_AT)
        verified = DriftSentry(tmp_path).verify_receipt(receipt, now=NOW)
        assert verified.status is FreezeStatus.DRIFTED
        assert verified.drift_reasons == (
            "live candidate freeze inputs could not be collected (fail-closed)",
        )
        assert receipt.status is FreezeStatus.FROZEN  # untouched


# ---------------------------------------------------------------------------
# Orchestrator hook.
# ---------------------------------------------------------------------------


class _StubDriftChecker:
    def __init__(self, report: DriftReport) -> None:
        self._report = report
        self.calls: list[CandidateFreezeReceipt] = []

    def check(
        self,
        receipt: CandidateFreezeReceipt,
        *,
        now: datetime,
        inputs: FreezeInputs | None = None,
    ) -> DriftReport:
        self.calls.append(receipt)
        return self._report

    def verify_receipt(
        self, receipt: CandidateFreezeReceipt, *, now: datetime
    ) -> CandidateFreezeReceipt:
        return receipt


def _confirmatory_orchestrator(
    checker: object,
    *,
    receipt: CandidateFreezeReceipt,
    durable_freeze_at: datetime,
    runner: object | None = None,
):
    attempts = FakeAttemptRepository()
    persistence = FakeShadowRunPersistence()
    orchestrator = ExperimentOrchestrator(
        attempts=attempts,
        baseline_repository=FakeBaselineRepository(
            (),
            confirmatory_source_registry_version=(
                receipt.source_registry_digest or FABRICATED_REGISTRY
            ),
        ),
        persistence=persistence,
        source_registry_version=receipt.source_registry_digest or FABRICATED_REGISTRY,
        freeze_binding=StubBindingResolver(
            FreezeBinding(
                receipt=receipt,
                durable_freeze_at=durable_freeze_at,
                publication_commit="9" * 40,
                publication_committer_at=durable_freeze_at + timedelta(seconds=1),
            )
        ),
        shadow_runner=runner,  # pyright: ignore[reportArgumentType]
        run_class="CONFIRMATORY",
        canonical_context=True,
        drift_sentry=checker,  # pyright: ignore[reportArgumentType]
        clock=lambda: NOW,
    )
    return orchestrator, attempts, persistence


class TestOrchestratorHook:
    def test_confirmatory_drift_skips_the_attempt_with_drifted_detail(self) -> None:
        orchestrator, attempts, _ = _confirmatory_orchestrator(
            _StubDriftChecker(_drifted_report("dependency_lock_digest drifted")),
            receipt=_fabricated_frozen(),
            durable_freeze_at=NOW - timedelta(seconds=300),
        )
        result = orchestrator.run_cycle()
        assert result.action is ExperimentCycleAction.SKIPPED_CONFIRMATORY_GATES
        assert result.attempt is not None
        assert result.attempt.status.value == "SKIPPED"
        assert result.detail is not None and result.detail.startswith("DRIFTED: ")
        assert attempts.all_attempts()[-1].status.value == "SKIPPED"

    def test_confirmatory_drift_never_launches_a_shadow_run(self) -> None:
        orchestrator, attempts, persistence = _confirmatory_orchestrator(
            _StubDriftChecker(
                _drifted_report("dependency_lock_digest drifted from the live repository state")
            ),
            receipt=_fabricated_frozen(),
            durable_freeze_at=NOW,
        )
        result = orchestrator.run_cycle()
        assert result.action is ExperimentCycleAction.SKIPPED_CONFIRMATORY_GATES
        assert persistence.persisted == []
        assert attempts.all_attempts()[-1].status.value == "SKIPPED"

    def test_confirmatory_ok_sentry_lets_the_run_complete(self) -> None:
        receipt = freeze_candidate(REPO_ROOT, frozen_at=NOW)
        runner = RecordingRunner()
        orchestrator, _, _ = _confirmatory_orchestrator(
            DriftSentry(REPO_ROOT),
            receipt=receipt,
            durable_freeze_at=NOW - timedelta(seconds=300),
            runner=runner,
        )
        result = orchestrator.run_cycle()
        assert result.action is ExperimentCycleAction.RAN
        assert len(runner.calls) == 1

    def test_dev_run_is_unaffected_and_never_invokes_the_sentry(self) -> None:
        checker = _StubDriftChecker(_drifted_report("anything"))
        attempts = FakeAttemptRepository()
        orchestrator = ExperimentOrchestrator(
            attempts=attempts,
            baseline_repository=FakeBaselineRepository(_observations()),
            persistence=FakeShadowRunPersistence(),
            source_registry_version=Digest("sha256:" + "1" * 64),
            run_class="DEV",
            canonical_context=False,
            drift_sentry=cast("object", checker),  # pyright: ignore[reportArgumentType]
            clock=lambda: NOW,
        )
        result = orchestrator.run_cycle()
        assert result.action is ExperimentCycleAction.RAN
        assert checker.calls == []


# ---------------------------------------------------------------------------
# Evaluator hook.
# ---------------------------------------------------------------------------


def _evaluate(
    *,
    store: object,
    run_id: str,
    as_of: datetime,
    confirmatory: bool,
    durable_freeze_at: datetime | None,
    checker: object | None = None,
):
    horizon = as_of + timedelta(hours=1)
    return evaluate_shadow_experiment_from_persisted(
        store=store,  # pyright: ignore[reportArgumentType]
        runs=(PersistedRunRef(run_id=run_id, as_of=as_of),),
        opportunity_groups=(),
        evaluation_horizon=horizon,
        generated_at=horizon,
        confirmatory=confirmatory,
        canonical_context=confirmatory,
        durable_freeze_at=durable_freeze_at,
        drift_sentry=cast("object", checker),  # pyright: ignore[reportArgumentType]
    )


def _store_for_live(paired: object, receipt: CandidateFreezeReceipt, durable: datetime):
    store = _store_double()
    _seed(store, paired, run_class="CONFIRMATORY")  # pyright: ignore[reportPrivateUsage, reportArgumentType]
    _seed_freeze(store, receipt, durable=durable)  # pyright: ignore[reportPrivateUsage]
    _seed_publication(store, receipt, publication_at=durable)  # pyright: ignore[reportPrivateUsage]
    return store


def _store_double():
    from test_evaluation_loaders import FakeStore

    return FakeStore()


class TestEvaluatorHook:
    def test_confirmatory_drift_yields_invalid_drift(self) -> None:
        _, _, freeze = _seeded()
        as_of = first_confirmatory_boundary(DURABLE_AT)
        paired = _paired(as_of, freeze_id=freeze.receipt_id)
        store = _store_double()
        _seed(store, paired, run_class="CONFIRMATORY")  # pyright: ignore[reportPrivateUsage]
        _seed_freeze(store, freeze, durable=DURABLE_AT)  # pyright: ignore[reportPrivateUsage]
        _seed_publication(store, freeze, publication_at=DURABLE_AT)  # pyright: ignore[reportPrivateUsage]
        receipt = _evaluate(
            store=store,
            run_id=paired.run.run_id,
            as_of=as_of,
            confirmatory=True,
            durable_freeze_at=DURABLE_AT,
            checker=DriftSentry(REPO_ROOT),
        )
        assert receipt.status.value == "INVALID_DRIFT"
        assert receipt.confirmatory_evidence is False

    def test_dev_persisted_evaluation_is_unaffected_by_the_sentry(self) -> None:
        store, paired, _ = _seeded()
        checker = _StubDriftChecker(_drifted_report("anything"))
        receipt = _evaluate(
            store=store,
            run_id=paired.run.run_id,
            as_of=paired.run.as_of,
            confirmatory=False,
            durable_freeze_at=None,
            checker=checker,
        )
        assert checker.calls == []
        assert receipt.status.value == "INSUFFICIENT_SAMPLE"

    def test_confirmatory_ok_sentry_keeps_evaluation_non_drift(self) -> None:
        receipt = freeze_candidate(REPO_ROOT, frozen_at=FROZEN_AT)
        durable = FROZEN_AT + timedelta(seconds=120)
        as_of = first_confirmatory_boundary(durable)
        paired = _paired(as_of, freeze_id=receipt.receipt_id)
        store = _store_for_live(paired, receipt, durable)
        evaluated = _evaluate(
            store=store,
            run_id=paired.run.run_id,
            as_of=as_of,
            confirmatory=True,
            durable_freeze_at=durable,
            checker=DriftSentry(REPO_ROOT),
        )
        assert evaluated.status.value == "INSUFFICIENT_SAMPLE"


def _seeded():
    return _default_store()  # pyright: ignore[reportPrivateUsage]


# ---------------------------------------------------------------------------
# Status rendering.
# ---------------------------------------------------------------------------


class TestStatusHook:
    def _status(self, drifted: bool):
        return build_experiment_status(
            freeze=None,
            window=None,
            run=None,
            coverage=None,
            opportunity_counts=(),
            evaluation=None,
            drift_report=_drifted_report("dependency_lock_digest drifted")
            if drifted
            else _OK_REPORT,
        )

    def test_a_drifted_sentry_report_forces_the_invalid_drift_state(self) -> None:
        assert self._status(True).drift_state == DRIFT_STATE_INVALID_DRIFT

    def test_an_ok_sentry_report_keeps_the_ok_drift_state(self) -> None:
        assert self._status(False).drift_state == DRIFT_STATE_OK

    def test_default_pure_projection_is_unchanged_without_a_report(self) -> None:
        status = build_experiment_status(
            freeze=None,
            window=None,
            run=None,
            coverage=None,
            opportunity_counts=(),
            evaluation=None,
        )
        assert status.drift_state == DRIFT_STATE_OK

    def test_drifted_stored_freeze_still_renders_invalid_drift(self) -> None:
        status = build_experiment_status(
            freeze=BoundFreezeStatus(
                receipt_id="freezereceipt_" + "a" * 64,
                status="DRIFTED",
                durable_freeze_at=None,
                implementation_commit=None,
                implementation_tree_digest=None,
                source_registry_digest=None,
                frozen_at=None,
            ),
            window=None,
            run=None,
            coverage=None,
            opportunity_counts=(),
            evaluation=None,
        )
        assert status.drift_state == DRIFT_STATE_INVALID_DRIFT
