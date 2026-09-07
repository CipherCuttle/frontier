"""Drift sentry for the PEF_V0 candidate freeze (WP5, G7) — fail-closed.

Given a freeze receipt (bound or candidate), the sentry recomputes the FULL
candidate identity from the live repository state
(:func:`frontier.application.candidate_freeze.collect_freeze_inputs`) and
compares every component against the receipt, cross-checked by the
authoritative freeze-domain verifier
(:func:`frontier.domain.candidate_freeze.verify_candidate_freeze`).

FAIL-CLOSED discipline: the sentry never auto-repairs, never re-freezes, and
never adopts current state. Drift is ONLY reported (a :class:`DriftReport`
with per-component expected/actual and exact reasons); the caller halts
confirmatory work. ``verify_receipt`` returns a transient verification
receipt for callers that must reuse the existing INVALID_DRIFT evaluation
semantics — the sentry itself never persists or mutates any stored state.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Protocol

from frontier.application.candidate_freeze import collect_freeze_inputs
from frontier.domain.candidate_freeze import (
    CandidateFreezeReceipt,
    FreezeInputs,
    FreezeStatus,
    verify_candidate_freeze,
)
from frontier.domain.drift_sentry import (
    DriftComponent,
    DriftReport,
    compare_freeze_identity,
)


def _live_comparator_identity() -> str:
    from frontier.domain import intelligence as comparator_module  # local import avoids a cycle

    return (
        f"{comparator_module.BASELINE_PROJECTION_VERSION}"
        f"|{comparator_module.BASELINE_RANKING_POLICY_VERSION}"
    )


def _explicit_drifted_receipt(
    receipt: CandidateFreezeReceipt, *, now: datetime, reason: str
) -> CandidateFreezeReceipt:
    """Return an explicit DRIFTED verification receipt without adopting state.

    Prefers a domain-consistent copy of the receipt; when the receipt itself
    fails domain validation (tampered identity), a fresh explicit DRIFTED
    receipt is constructed from safe values only — never guessed identity.
    """
    try:
        return replace(receipt, status=FreezeStatus.DRIFTED, drift_reasons=(reason,))
    except ValueError:
        return CandidateFreezeReceipt(
            frozen_at=now,
            status=FreezeStatus.DRIFTED,
            drift_reasons=(reason,),
            preregistration_digest=receipt.preregistration_digest,
            preregistration_config_digest=None,
            implementation_commit=None,
            implementation_tree_digest=None,
            dependency_lock_digest=None,
            source_registry_digest=None,
            registry_entry_digests=None,
        )


class DriftChecker(Protocol):
    """Structural port the orchestrator/evaluator accept (duck-typed sentry)."""

    def check(
        self,
        receipt: CandidateFreezeReceipt,
        *,
        now: datetime,
        inputs: FreezeInputs | None = None,
    ) -> DriftReport: ...

    def verify_receipt(
        self, receipt: CandidateFreezeReceipt, *, now: datetime
    ) -> CandidateFreezeReceipt: ...


@dataclass(frozen=True, slots=True)
class SentryVerification:
    """A sentry verdict plus the transient verification receipt it implies."""

    report: DriftReport
    verified_receipt: CandidateFreezeReceipt


class DriftSentry:
    """Recomputes the frozen candidate identity against the live repository."""

    def __init__(self, root: Path) -> None:
        self._root = root

    @property
    def root(self) -> Path:
        return self._root

    def collect(self) -> FreezeInputs:
        """Collect the live identity components (may raise on hard errors)."""
        return collect_freeze_inputs(self._root)

    def _try_collect(self) -> FreezeInputs | None:
        try:
            return collect_freeze_inputs(self._root)
        except (OSError, subprocess.SubprocessError):
            return None

    def check(
        self,
        receipt: CandidateFreezeReceipt,
        *,
        now: datetime,
        inputs: FreezeInputs | None = None,
    ) -> DriftReport:
        """Recompute the full identity tuple and report ANY drift explicitly.

        ``inputs`` may be supplied (tests, callers that already collected the
        live state); by default the sentry recomputes from the repository
        root. Pure: the receipt is never mutated and nothing is persisted.
        """
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("drift sentry requires a timezone-aware clock")
        live = inputs if inputs is not None else self._try_collect()
        if live is None:
            return DriftReport(
                checked_at=now,
                components=(
                    DriftComponent(
                        component="live_freeze_inputs",
                        expected="collectable",
                        actual=None,
                        drifted=True,
                        reason=(
                            "live candidate freeze inputs could not be collected (fail-closed)"
                        ),
                    ),
                ),
            )
        components = list(
            compare_freeze_identity(receipt, live, comparator_identity=_live_comparator_identity())
        )
        # Cross-check against the authoritative freeze-domain verifier so the
        # report can never be weaker than the frozen freeze semantics. A
        # receipt that fails domain validation outright is itself drift.
        verification_drifted = False
        verification_reason = ""
        try:
            verified = verify_candidate_freeze(receipt, inputs=live, verified_at=now)
        except ValueError as error:
            verification_drifted = True
            verification_reason = f"bound freeze receipt identity is invalid: {error}"
        else:
            verification_drifted = verified.status is FreezeStatus.DRIFTED
            verification_reason = "; ".join(verified.drift_reasons)
        if verification_drifted and not any(component.drifted for component in components):
            components.append(
                DriftComponent(
                    component="freeze_verification",
                    expected="FROZEN",
                    actual="DRIFTED",
                    drifted=True,
                    reason=verification_reason,
                )
            )
        return DriftReport(checked_at=now, components=tuple(components))

    def verify_receipt(
        self, receipt: CandidateFreezeReceipt, *, now: datetime
    ) -> CandidateFreezeReceipt:
        """Return a transient verification receipt (DRIFTED on any drift).

        Never mutates the input receipt and never persists anything. When the
        live inputs cannot be collected at all, an explicit DRIFTED receipt is
        returned (fail-closed) rather than raising into the confirmatory path.
        """
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("drift sentry requires a timezone-aware clock")
        live = self._try_collect()
        if live is None:
            return _explicit_drifted_receipt(
                receipt,
                now=now,
                reason="live candidate freeze inputs could not be collected (fail-closed)",
            )
        try:
            return verify_candidate_freeze(receipt, inputs=live, verified_at=now)
        except ValueError as error:
            # The receipt itself fails domain validation (tampered identity):
            # report drift, never adopt current state.
            return _explicit_drifted_receipt(
                receipt, now=now, reason=f"bound freeze receipt identity is invalid: {error}"
            )

    def verify(self, receipt: CandidateFreezeReceipt, *, now: datetime) -> SentryVerification:
        """Check + transient verification receipt in one pure pass."""
        return SentryVerification(
            report=self.check(receipt, now=now),
            verified_receipt=self.verify_receipt(receipt, now=now),
        )


__all__ = ["DriftChecker", "DriftSentry", "SentryVerification"]
