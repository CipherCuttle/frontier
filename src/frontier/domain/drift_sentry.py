"""Domain drift-report model for the PEF_V0 candidate freeze sentry (WP5, G7).

The sentry recomputes the FULL candidate identity from the live repository
state and compares it against a bound (or candidate) freeze receipt. The
:class:`DriftReport` is a pure domain projection: it NEVER mutates the
receipt, never re-freezes, and never adopts current state — drift is only
reported with per-component expected/actual detail and exact reasons, so the
caller can halt confirmatory work (fail-closed, R8).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from .advanced_intelligence import (
    PEF_ALGORITHM_VERSION,
    PEF_CANDIDATE_ID,
    PEF_CONFIGURATION_DIGEST,
    PEF_EXPERIMENT_ID,
)
from .candidate_freeze import (
    CandidateFreezeReceipt,
    FreezeInputs,
    FreezeStatus,
    RegistryEntryDigest,
)
from .digests import Digest

# Frozen comparator identity (control-arm authority, ADR-0001). The live
# domain constants are compared against these preregistered strings at sentry
# time, so a changed constant drifts.
COMPARATOR_BASELINE_PROJECTION_VERSION = "baseline-intelligence-v0"
COMPARATOR_BASELINE_RANKING_POLICY_VERSION = "naive-episode-activity-v0"


class DriftStatus(StrEnum):
    """Explicit sentry outcome: OK or DRIFTED (never partial/unknown)."""

    OK = "OK"
    DRIFTED = "DRIFTED"


@dataclass(frozen=True, slots=True)
class DriftComponent:
    """One compared identity component (expected/actual + exact reason)."""

    component: str
    expected: str | None
    actual: str | None
    drifted: bool
    reason: str | None = None

    def __post_init__(self) -> None:
        if not self.component:
            raise ValueError("drift component requires a name")
        if self.drifted and not self.reason:
            raise ValueError("a drifted component requires an explicit reason")
        if not self.drifted and self.reason is not None:
            raise ValueError("a non-drifted component cannot carry a drift reason")


@dataclass(frozen=True, slots=True)
class DriftReport:
    """Fail-closed drift report over the full candidate identity tuple."""

    checked_at: datetime
    components: tuple[DriftComponent, ...]

    def __post_init__(self) -> None:
        if self.checked_at.tzinfo is None or self.checked_at.utcoffset() is None:
            raise ValueError("drift report checked_at must be timezone-aware")

    @property
    def drifted(self) -> bool:
        return any(component.drifted for component in self.components)

    @property
    def status(self) -> DriftStatus:
        return DriftStatus.DRIFTED if self.drifted else DriftStatus.OK

    @property
    def reasons(self) -> tuple[str, ...]:
        reasons: list[str] = []
        for component in self.components:
            if component.drifted and component.reason is not None:
                reasons.append(component.reason)
        return tuple(reasons)

    def component(self, name: str) -> DriftComponent | None:
        return next((item for item in self.components if item.component == name), None)


def _entry_render(entries: tuple[RegistryEntryDigest, ...] | None) -> str | None:
    """Render a registry-entry tuple deterministically (path:digest pairs)."""
    if entries is None:
        return None
    return ";".join(f"{entry.path}:{entry.digest}" for entry in entries)


def compare_freeze_identity(
    receipt: CandidateFreezeReceipt,
    inputs: FreezeInputs,
    *,
    comparator_identity: str,
) -> tuple[DriftComponent, ...]:
    """Component-wise comparison of the frozen identity against live recomputation.

    Mirrors the exact drift semantics of
    :func:`frontier.domain.candidate_freeze.verify_candidate_freeze` (ANY
    mismatch drifts) but keeps per-component expected/actual detail so the
    report is directly actionable. Pure: nothing is mutated or persisted.
    """
    components: list[DriftComponent] = []

    def add(component: DriftComponent) -> None:
        components.append(component)

    def identity(label: str, expected: str | None, actual: str | None, *, reason: str) -> None:
        drifted = actual != expected
        add(
            DriftComponent(
                component=label,
                expected=expected,
                actual=actual,
                drifted=drifted,
                reason=None if not drifted else reason,
            )
        )

    def bound_vs_live(
        label: str,
        frozen: object,
        live: object,
        *,
        render: Callable[[object], str | None] | None = None,
    ) -> None:
        expected = None if frozen is None else (str(frozen) if render is None else render(frozen))
        actual = None if live is None else (str(live) if render is None else render(live))
        if frozen is None:
            add(
                DriftComponent(
                    component=label,
                    expected=None,
                    actual=actual,
                    drifted=True,
                    reason=f"{label} was not bound in the original freeze receipt",
                )
            )
        elif live is None:
            add(
                DriftComponent(
                    component=label,
                    expected=expected,
                    actual=None,
                    drifted=True,
                    reason=f"{label} unavailable in the live repository state",
                )
            )
        else:
            identity(
                label,
                expected,
                actual,
                reason=f"{label} drifted from the live repository state",
            )

    # Candidate identity: the receipt's own fields against the preregistered
    # constants (fail-closed when any bound identity value differs).
    identity(
        "candidate_id",
        PEF_CANDIDATE_ID,
        receipt.candidate_id,
        reason="candidate_id mismatch with the preregistered PEF identity",
    )
    identity(
        "experiment_id",
        PEF_EXPERIMENT_ID,
        receipt.experiment_id,
        reason="experiment_id mismatch with the preregistered PEF identity",
    )
    identity(
        "algorithm_version",
        PEF_ALGORITHM_VERSION,
        receipt.algorithm_version,
        reason="algorithm_version mismatch with the preregistered PEF identity",
    )
    identity(
        "configuration_digest",
        str(PEF_CONFIGURATION_DIGEST),
        str(receipt.configuration_digest),
        reason="configuration digest mismatch with the preregistered PEF configuration",
    )

    # Receipt-bound components against the live repository recomputation.
    bound_vs_live(
        "preregistration_digest", receipt.preregistration_digest, inputs.preregistration_digest
    )
    bound_vs_live(
        "preregistration_config_digest",
        receipt.preregistration_config_digest,
        inputs.preregistration_config_digest,
    )
    bound_vs_live(
        "implementation_commit", receipt.implementation_commit, inputs.implementation_commit
    )
    bound_vs_live(
        "implementation_tree_digest",
        receipt.implementation_tree_digest,
        inputs.implementation_tree_digest,
    )
    bound_vs_live(
        "dependency_lock_digest", receipt.dependency_lock_digest, inputs.dependency_lock_digest
    )
    bound_vs_live(
        "source_registry_digest", receipt.source_registry_digest, inputs.source_registry_digest
    )
    bound_vs_live(
        "source_registry_entry_digests",
        receipt.registry_entry_digests,
        inputs.registry_entry_digests,
        render=_entry_render,  # pyright: ignore[reportArgumentType]
    )

    # Per-entry detail: every bound registry entry is compared individually so
    # a single mutated source contract is named exactly.
    live_by_path: dict[str, Digest] = {}
    if inputs.registry_entry_digests is not None:
        live_by_path = {entry.path: entry.digest for entry in inputs.registry_entry_digests}
    for entry in receipt.registry_entry_digests or ():
        label = f"registry_entry[{entry.path}]"
        if entry.path not in live_by_path:
            add(
                DriftComponent(
                    component=label,
                    expected=str(entry.digest),
                    actual=None,
                    drifted=True,
                    reason=(
                        f"{label} unavailable in the live repository state"
                        if inputs.registry_entry_digests is None
                        else f"{label} missing from the live source registry"
                    ),
                )
            )
        else:
            identity(
                label,
                str(entry.digest),
                str(live_by_path[entry.path]),
                reason=f"{label} drifted from the live source registry entry",
            )

    # Freeze lifecycle: a receipt that was itself recorded DRIFTED never
    # becomes OK just because the live inputs now happen to match again.
    status_ok = receipt.status is FreezeStatus.FROZEN
    add(
        DriftComponent(
            component="freeze_status",
            expected="FROZEN",
            actual=receipt.status.value,
            drifted=not status_ok,
            reason=None if status_ok else "bound freeze receipt recorded DRIFTED",
        )
    )

    # Comparator identity: the live control-arm constants must still equal the
    # frozen baseline comparator identity.
    identity(
        "comparator_identity",
        (f"{COMPARATOR_BASELINE_PROJECTION_VERSION}|{COMPARATOR_BASELINE_RANKING_POLICY_VERSION}"),
        comparator_identity,
        reason="comparator_identity drifted from the frozen baseline comparator",
    )

    return tuple(components)


__all__ = [
    "COMPARATOR_BASELINE_PROJECTION_VERSION",
    "COMPARATOR_BASELINE_RANKING_POLICY_VERSION",
    "DriftComponent",
    "DriftReport",
    "DriftStatus",
    "compare_freeze_identity",
]
