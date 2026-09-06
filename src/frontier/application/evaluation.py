"""Application service: preregistered evaluation of paired shadow runs (slice D).

``evaluate_shadow_experiment`` consumes the paired shadow-run series of a
confirmatory window, model-independent opportunity-anchor inputs, and the
durable candidate freeze receipt, and produces an immutable evaluation receipt
(R8) under the exact rules frozen in
``experiments/advanced_intelligence/pef_v0/preregistration.json``.

Labels are computed from evidence only — never from either arm's outputs (R7).
Unresolved coverage outcomes are explicit and excluded from resolved fractions
(R4). A DRIFTED freeze invalidates confirmatory status (INVALID_DRIFT), and
insufficient sampling is an explicit epistemic state (INSUFFICIENT_SAMPLE),
never a failed hypothesis.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime

from frontier.domain.advanced_intelligence import (
    PEF_ALGORITHM_VERSION,
    PEF_CANDIDATE_ID,
    PEF_CONFIGURATION_DIGEST,
    PEF_EXPERIMENT_ID,
    ShadowExperimentRun,
    ShadowRunStatus,
)
from frontier.domain.candidate_freeze import CandidateFreezeReceipt, FreezeStatus
from frontier.domain.evaluation import (
    GLOBAL_RANK_CUTOFF_K,
    MINIMUM_QUALIFYING_DOMAINS,
    AnchorTracking,
    EvaluationReceipt,
    EvaluationStatus,
    OpportunityGroup,
    RetainedOpportunity,
    ShadowRunBinding,
    build_evaluation_receipt,
    build_retained_opportunities,
    evaluate_domains,
    pooled_lead_time_median,
)


@dataclass(frozen=True, slots=True)
class PairedSnapshot:
    """One paired snapshot of the confirmatory window.

    ``run`` is the durable paired shadow run (control arm ranks bound in the
    run payload). ``candidate_rank_by_episode`` is the candidate arm's global
    rank per episode for the exact same ``as_of`` (from the bound PEF_V0
    candidate artifact). ``episode_memberships`` maps every episode id to its
    member observation ids at the same ``as_of`` — the shared universe both
    arms ranked (used for stable anchor tracking, never for labels).
    """

    run: ShadowExperimentRun
    candidate_rank_by_episode: Mapping[str, int]
    episode_memberships: Mapping[str, Sequence[str]]


def _validate_run_identity(run: ShadowExperimentRun) -> None:
    if run.experiment_id != PEF_EXPERIMENT_ID:
        raise ValueError("shadow run experiment id mismatch")
    if run.candidate_id != PEF_CANDIDATE_ID:
        raise ValueError("shadow run candidate id mismatch")
    if run.algorithm_version != PEF_ALGORITHM_VERSION:
        raise ValueError("shadow run algorithm version mismatch")
    if run.configuration_digest != PEF_CONFIGURATION_DIGEST:
        raise ValueError("shadow run configuration digest mismatch")


def _confirmatory_run_binding_failure(
    runs: Sequence[ShadowExperimentRun],
    freeze_receipt: CandidateFreezeReceipt,
) -> str | None:
    """Return why these runs cannot contribute confirmatory evidence.

    Development shadow runs are allowed to exist before candidate freeze, but
    they must never become confirmatory merely because a FROZEN receipt is
    supplied later. A confirmatory run must bind the exact receipt identity and
    its snapshot boundary must be strictly after the receipt's own frozen_at
    timestamp, which is the strongest freeze-boundary timestamp represented in
    the current receipt contract. The later operational durability/merge gate
    remains responsible for choosing the preregistered first 300-second
    boundary strictly after the durable receipt enters canonical history.
    """
    for run in runs:
        if run.candidate_freeze_receipt_id != freeze_receipt.receipt_id:
            return f"shadow run {run.run_id} does not bind the evaluated candidate freeze receipt"
        if run.as_of <= freeze_receipt.frozen_at:
            return f"shadow run {run.run_id} boundary is not strictly after candidate freeze"
    return None


def build_anchor_tracking(
    opportunity: RetainedOpportunity,
    snapshots: Sequence[PairedSnapshot],
) -> tuple[AnchorTracking, ...]:
    """Locate the current episode of the stable anchor at each paired snapshot.

    Both arms always rank the identical episode universe (verified when each
    run was built), so an anchor observation is a comparison opportunity for
    BOTH arms at every snapshot where its episode exists — the paired design
    is preserved by construction. An observation outside every episode at a
    snapshot yields ``None`` ranks for both arms at that snapshot.
    """
    tracking: list[AnchorTracking] = []
    for snapshot in snapshots:
        episode_id: str | None = None
        for candidate_episode_id, members in snapshot.episode_memberships.items():
            if opportunity.anchor.observation_id in members:
                if episode_id is not None:
                    raise ValueError(
                        "anchor observation occurs in multiple episodes at one snapshot"
                    )
                episode_id = candidate_episode_id
        control_rank: int | None = None
        if episode_id is not None:
            for ranked in snapshot.run.control_ranking:
                if ranked.episode_id == episode_id:
                    control_rank = ranked.rank
                    break
        candidate_rank: int | None = None
        if episode_id is not None:
            candidate_rank = snapshot.candidate_rank_by_episode.get(episode_id)
        tracking.append(
            AnchorTracking(
                as_of=snapshot.run.as_of,
                episode_id=episode_id,
                control_rank=control_rank,
                candidate_rank=candidate_rank,
            )
        )
    return tuple(tracking)


def evaluate_shadow_experiment(
    *,
    snapshots: Sequence[PairedSnapshot],
    opportunity_groups: Sequence[OpportunityGroup],
    freeze_receipt: CandidateFreezeReceipt,
    evaluation_horizon: datetime,
    generated_at: datetime,
    rank_cutoff_k: int = GLOBAL_RANK_CUTOFF_K,
) -> EvaluationReceipt:
    """Evaluate the paired shadow window under the preregistered rules."""
    if not snapshots:
        raise ValueError("evaluation requires at least one paired snapshot")
    if evaluation_horizon.tzinfo is None or evaluation_horizon.utcoffset() is None:
        raise ValueError("evaluation horizon must be timezone-aware")
    if generated_at.tzinfo is None or generated_at.utcoffset() is None:
        raise ValueError("evaluation generated_at must be timezone-aware")

    ordered = sorted(snapshots, key=lambda item: item.run.as_of)
    if len({item.run.run_id for item in ordered}) != len(ordered):
        raise ValueError("duplicate shadow run ids in evaluation window")
    if ordered[-1].run.as_of > evaluation_horizon:
        raise ValueError("evaluation horizon must not precede the last paired snapshot")

    runs = [snapshot.run for snapshot in ordered]
    for run in runs:
        _validate_run_identity(run)

    confirmatory_binding_failure = _confirmatory_run_binding_failure(runs, freeze_receipt)
    failed_runs = [run.run_id for run in runs if run.status is ShadowRunStatus.FAILED]

    opportunities = build_retained_opportunities(opportunity_groups)
    for item in opportunities:
        if item.resolution_at > evaluation_horizon:
            raise ValueError(
                f"opportunity {item.anchor.observation_id} is not mature at the evaluation horizon"
            )

    tracking_by_anchor: dict[str, tuple[AnchorTracking, ...]] = {
        item.anchor.observation_id: build_anchor_tracking(item, ordered) for item in opportunities
    }
    domain_evaluations = evaluate_domains(
        opportunities, tracking_by_anchor, rank_cutoff_k=rank_cutoff_k
    )
    pooled_median = pooled_lead_time_median(
        domain_evaluations, tracking_by_anchor, opportunities, rank_cutoff_k=rank_cutoff_k
    )

    run_bindings = tuple(
        ShadowRunBinding(run_id=run.run_id, run_digest=run.run_digest) for run in runs
    )
    qualifying_domains = [
        evaluation for evaluation in domain_evaluations if evaluation.qualifies_sample_adequacy
    ]

    status = EvaluationStatus.COMPLETE
    status_reason: str | None = None
    verdict: str | None = None

    if freeze_receipt.status is FreezeStatus.DRIFTED:
        # A DRIFTED freeze invalidates confirmatory status (preregistration
        # candidate-freeze requirements): no verdict is emitted.
        status = EvaluationStatus.INVALID_DRIFT
        status_reason = "candidate freeze receipt recorded DRIFTED"
    elif failed_runs:
        status = EvaluationStatus.FAILED
        status_reason = f"shadow runs FAILED: {', '.join(failed_runs)}"
    elif len(qualifying_domains) < MINIMUM_QUALIFYING_DOMAINS:
        # Underpowered development/diagnostic evaluation remains explicitly
        # non-confirmatory. Freeze binding is mandatory before a COMPLETE
        # receipt can ever carry confirmatory evidence.
        status = EvaluationStatus.INSUFFICIENT_SAMPLE
        status_reason = (
            "fewer than two adequately sampled domains: "
            f"{len(qualifying_domains)} qualifying of {len(domain_evaluations)}"
        )
    elif confirmatory_binding_failure is not None:
        status = EvaluationStatus.INVALID_DRIFT
        status_reason = confirmatory_binding_failure
    else:
        all_pass = (
            all(evaluation.promotion_eligible for evaluation in qualifying_domains)
            and pooled_median is not None
            and pooled_median > 0
        )
        verdict = "SUPPORTED" if all_pass else "NOT_SUPPORTED"

    return build_evaluation_receipt(
        as_of=evaluation_horizon,
        generated_at=generated_at,
        shadow_runs=run_bindings,
        candidate_freeze_receipt_id=freeze_receipt.receipt_id,
        freeze_receipt_digest=freeze_receipt.receipt_digest,
        preregistration_digest=freeze_receipt.preregistration_digest,
        freeze_status=freeze_receipt.status,
        opportunities=opportunities,
        tracking_by_anchor=tracking_by_anchor,
        domain_evaluations=domain_evaluations,
        pooled_median=pooled_median,
        status=status,
        status_reason=status_reason,
        verdict=verdict,
    )
