from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from frontier.application.evaluation import (
    _enforce_resolved_sample_floor,  # pyright: ignore[reportPrivateUsage]
)
from frontier.domain.advanced_intelligence import PEF_CONFIGURATION_DIGEST
from frontier.domain.candidate_freeze import (
    FreezeInputs,
    FreezeStatus,
    build_candidate_freeze_receipt,
)
from frontier.domain.digests import Digest
from frontier.domain.evaluation import ArmPrecision, DomainEvaluation

FROZEN_AT = datetime(2026, 9, 7, 17, tzinfo=UTC)


def _freeze_inputs(*, registry_entries_present: bool) -> FreezeInputs:
    return FreezeInputs(
        preregistration_digest=Digest("sha256:" + "1" * 64),
        preregistration_config_digest=PEF_CONFIGURATION_DIGEST,
        implementation_commit="a" * 40,
        implementation_tree_digest="b" * 40,
        dependency_lock_digest=Digest("sha256:" + "2" * 64),
        source_registry_digest=Digest("sha256:" + "3" * 64),
        registry_entry_digests=() if registry_entries_present else None,
    )


def test_freeze_rejects_unavailable_registry_entry_digests() -> None:
    receipt = build_candidate_freeze_receipt(
        _freeze_inputs(registry_entries_present=False), frozen_at=FROZEN_AT
    )
    assert receipt.status is FreezeStatus.DRIFTED
    assert "source registry entry digests unavailable" in receipt.drift_reasons


def _domain_evaluation(*, resolved: int, denominator: int) -> DomainEvaluation:
    return DomainEvaluation(
        domain="SOFTWARE_PACKAGES",
        resolved_label_fraction_denominator=denominator,
        resolved_label_fraction_numerator=resolved,
        unresolved_coverage_count=denominator - resolved,
        positive_count=10,
        negative_count=max(0, resolved - 10),
        candidate_arm=ArmPrecision(surfaced_resolved=20, positive_surfaced_resolved=10),
        control_arm=ArmPrecision(surfaced_resolved=20, positive_surfaced_resolved=10),
        difference_lower_bound=Decimal("0"),
        median_lead_time_advantage_seconds=Decimal("1"),
        qualifies_sample_adequacy=True,
    )


def test_confirmatory_path_rejects_27_resolved_plus_3_unresolved() -> None:
    (evaluation,) = _enforce_resolved_sample_floor(
        (_domain_evaluation(resolved=27, denominator=30),)
    )
    assert evaluation.resolved_label_fraction_bps == 9000
    assert evaluation.qualifies_sample_adequacy is False
    assert evaluation.promotion_eligible is False


def test_confirmatory_path_preserves_exact_30_resolved_floor() -> None:
    original = _domain_evaluation(resolved=30, denominator=30)
    (evaluation,) = _enforce_resolved_sample_floor((original,))
    assert evaluation == original
    assert evaluation.qualifies_sample_adequacy is True
