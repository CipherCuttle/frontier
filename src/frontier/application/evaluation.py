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
from dataclasses import dataclass, replace
from datetime import datetime
from typing import TYPE_CHECKING, Protocol

from frontier.application.drift_sentry import DriftChecker
from frontier.application.freeze_publication import (
    CandidateFreezePublication,
    first_confirmatory_boundary,
    require_confirmatory_boundary,
)
from frontier.domain.advanced_intelligence import (
    PEF_ALGORITHM_VERSION,
    PEF_CANDIDATE_ID,
    PEF_CONFIGURATION_DIGEST,
    PEF_EXPERIMENT_ID,
    ShadowExperimentRun,
    ShadowRunStatus,
)
from frontier.domain.candidate_freeze import CandidateFreezeReceipt, FreezeStatus
from frontier.domain.digests import Digest
from frontier.domain.drift_sentry import DriftStatus
from frontier.domain.evaluation import (
    GLOBAL_RANK_CUTOFF_K,
    MIN_RESOLVED_OPPORTUNITIES_PER_DOMAIN,
    MINIMUM_QUALIFYING_DOMAINS,
    AnchorTracking,
    DomainEvaluation,
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

if TYPE_CHECKING:  # pragma: no cover - annotations only
    from frontier.application.evaluation_loaders import (
        EvaluationArtifactStore,
        PersistedRunRef,
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
    *,
    durable_freeze_at: datetime | None,
) -> str | None:
    """Return why these runs cannot contribute confirmatory evidence.

    ``frozen_at`` records receipt creation, not canonical durability. The
    caller must therefore supply ``durable_freeze_at`` as stamped by the
    canonical DB insert transaction (migration 0010: ``clock_timestamp()`` at
    insert-commit time, never any external/local clock). Missing or
    inconsistent durability evidence fails closed. Every confirmatory run must
    bind the exact receipt identity and its paired boundary must be strictly
    after that durable-freeze timestamp.
    """
    if durable_freeze_at is None:
        return "durable candidate-freeze main-merge timestamp is required"
    if durable_freeze_at.tzinfo is None or durable_freeze_at.utcoffset() is None:
        return "durable candidate-freeze main-merge timestamp must be timezone-aware"
    if durable_freeze_at < freeze_receipt.frozen_at:
        return "durable candidate-freeze timestamp cannot precede receipt creation"
    for run in runs:
        if run.candidate_freeze_receipt_id != freeze_receipt.receipt_id:
            return f"shadow run {run.run_id} does not bind the evaluated candidate freeze receipt"
        if run.as_of <= durable_freeze_at:
            return (
                f"shadow run {run.run_id} boundary is not strictly after durable candidate freeze"
            )
    return None


def _enforce_resolved_sample_floor(
    evaluations: Sequence[DomainEvaluation],
) -> tuple[DomainEvaluation, ...]:
    """Fail closed on the preregistered minimum resolved-opportunity floor.

    The frozen contract requires at least 30 *resolved* opportunities in a
    qualifying domain. The domain helper historically compared the total
    retained denominator instead, so unresolved coverage could satisfy the
    nominal count. This application boundary cannot permit that stale helper
    result into confirmatory evidence.
    """
    return tuple(
        replace(evaluation, qualifies_sample_adequacy=False)
        if (
            evaluation.qualifies_sample_adequacy
            and evaluation.resolved_label_fraction_numerator < MIN_RESOLVED_OPPORTUNITIES_PER_DOMAIN
        )
        else evaluation
        for evaluation in evaluations
    )


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
    durable_freeze_at: datetime | None = None,
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

    confirmatory_binding_failure = _confirmatory_run_binding_failure(
        runs,
        freeze_receipt,
        durable_freeze_at=durable_freeze_at,
    )
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
    domain_evaluations = _enforce_resolved_sample_floor(
        evaluate_domains(opportunities, tracking_by_anchor, rank_cutoff_k=rank_cutoff_k)
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
        # non-confirmatory. Freeze binding and durable-main evidence are
        # mandatory before a COMPLETE receipt can carry confirmatory evidence.
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


class EvaluationReceiptPersistence(Protocol):
    """Append-only persistence port for evaluation receipts (R8).

    Implementations must be idempotent by construction: a digest-identical
    replay of the same content-derived receipt identity is a no-op and a
    digest-different conflict is an error.
    """

    def record_receipt(self, receipt: EvaluationReceipt) -> None: ...


@dataclass(frozen=True, slots=True)
class _PersistedEvaluationAuthority:
    confirmatory: bool
    durable_freeze_at: datetime | None
    window_start: datetime | None


def _resolve_persisted_evaluation_authority(
    store: EvaluationArtifactStore,
    loaded: Sequence[object],
    *,
    requested_confirmatory: bool,
    canonical_context: bool | None,
    durable_freeze_at_assertion: datetime | None,
    window_start_assertion: datetime | None,
) -> _PersistedEvaluationAuthority:
    from frontier.application.evaluation_loaders import (
        CONFIRMATORY_RUN_CLASS,
        DEV_RUN_CLASS,
        LoadedPairedSnapshot,
        PersistedEvaluationError,
    )

    snapshots = tuple(item for item in loaded if isinstance(item, LoadedPairedSnapshot))
    if len(snapshots) != len(loaded):
        raise TypeError("persisted evaluation authority requires loaded paired snapshots")
    run_classes = {item.run_class for item in snapshots}
    if len(run_classes) != 1:
        raise PersistedEvaluationError(
            "persisted evaluation cannot mix DEV and CONFIRMATORY run classes"
        )
    run_class = next(iter(run_classes))
    if run_class not in (DEV_RUN_CLASS, CONFIRMATORY_RUN_CLASS):
        raise PersistedEvaluationError(f"unknown persisted run class {run_class!r}")
    actual_confirmatory = run_class == CONFIRMATORY_RUN_CLASS
    if requested_confirmatory and not actual_confirmatory:
        raise PersistedEvaluationError(
            "caller cannot escalate a persisted DEV run to CONFIRMATORY evaluation"
        )
    if not actual_confirmatory:
        if durable_freeze_at_assertion is not None or window_start_assertion is not None:
            raise PersistedEvaluationError(
                "DEV persisted evaluation cannot accept confirmatory authority timestamps"
            )
        return _PersistedEvaluationAuthority(False, None, None)

    if canonical_context is False:
        raise ValueError(
            "confirmatory persisted evaluation was explicitly denied canonical DB context"
        )
    receipt_ids = {item.freeze_receipt.receipt_id for item in snapshots}
    if len(receipt_ids) != 1:
        raise PersistedEvaluationError(
            "confirmatory persisted evaluation runs bind different candidate freeze receipts"
        )
    receipt_id = next(iter(receipt_ids))
    freeze_receipt = snapshots[0].freeze_receipt
    freeze_row = store.fetch_freeze_receipt_row(receipt_id)
    if freeze_row is None or freeze_row.receipt_id != receipt_id:
        raise PersistedEvaluationError("confirmatory freeze durability row is unresolvable")
    if freeze_row.durable_freeze_at is None:
        raise PersistedEvaluationError("confirmatory freeze has no canonical DB durability")
    publication_row = store.fetch_freeze_publication_row(receipt_id)
    if publication_row is None:
        raise PersistedEvaluationError(
            "confirmatory freeze has no persisted Git publication authority"
        )
    try:
        publication = CandidateFreezePublication(
            freeze_receipt_id=publication_row.receipt_id,
            freeze_receipt_digest=Digest(publication_row.freeze_receipt_digest),
            implementation_commit=publication_row.implementation_commit,
            implementation_tree_digest=publication_row.implementation_tree_digest,
            publication_commit=publication_row.publication_commit,
            publication_committer_at=publication_row.publication_committer_at,
            schema_version=publication_row.schema_version,
        )
    except ValueError as error:
        raise PersistedEvaluationError(
            f"persisted Git publication authority is invalid: {error}"
        ) from error
    if str(publication.publication_digest) != publication_row.publication_digest:
        raise PersistedEvaluationError("persisted Git publication digest does not bind its payload")
    if publication.freeze_receipt_id != freeze_receipt.receipt_id:
        raise PersistedEvaluationError("Git publication binds a different freeze receipt id")
    if publication.freeze_receipt_digest != freeze_receipt.receipt_digest:
        raise PersistedEvaluationError("Git publication binds a different freeze receipt digest")
    if (
        freeze_receipt.implementation_commit is None
        or freeze_receipt.implementation_tree_digest is None
    ):
        raise PersistedEvaluationError("confirmatory freeze is missing implementation identity")
    if publication.implementation_commit != freeze_receipt.implementation_commit:
        raise PersistedEvaluationError("Git publication binds a different implementation commit")
    if publication.implementation_tree_digest != freeze_receipt.implementation_tree_digest:
        raise PersistedEvaluationError("Git publication binds a different implementation tree")
    if publication.publication_committer_at < freeze_row.durable_freeze_at:
        raise PersistedEvaluationError("Git publication timestamp precedes canonical DB durability")
    window_start = first_confirmatory_boundary(publication.publication_committer_at)
    for item in snapshots:
        try:
            require_confirmatory_boundary(
                as_of=item.run.as_of,
                publication_committer_at=publication.publication_committer_at,
            )
        except ValueError as error:
            raise PersistedEvaluationError(
                f"persisted CONFIRMATORY run is outside Git-publication authority: {error}"
            ) from error
    if (
        durable_freeze_at_assertion is not None
        and durable_freeze_at_assertion != freeze_row.durable_freeze_at
    ):
        raise PersistedEvaluationError(
            "caller durable_freeze_at assertion disagrees with persisted authority"
        )
    if window_start_assertion is not None and window_start_assertion != window_start:
        raise PersistedEvaluationError(
            "caller window_start assertion disagrees with persisted Git publication authority"
        )
    return _PersistedEvaluationAuthority(True, freeze_row.durable_freeze_at, window_start)


def evaluate_shadow_experiment_from_persisted(
    *,
    store: EvaluationArtifactStore,
    runs: Sequence[PersistedRunRef],
    opportunity_groups: Sequence[OpportunityGroup],
    evaluation_horizon: datetime,
    generated_at: datetime,
    confirmatory: bool = False,
    canonical_context: bool | None = None,
    durable_freeze_at: datetime | None = None,
    drift_sentry: DriftChecker | None = None,
    window_start: datetime | None = None,
    feature_batch_id: str | None = None,
    rank_cutoff_k: int = GLOBAL_RANK_CUTOFF_K,
    receipt_repository: EvaluationReceiptPersistence | None = None,
) -> EvaluationReceipt:
    """Evaluate a persisted shadow window end-to-end from durable artifacts.

    Additive operational path (WP4, G2): every paired snapshot is loaded via
    :func:`frontier.application.evaluation_loaders.load_paired_snapshot` with
    strong identity checks (digest recomputation, never trust), then fed
    through the EXISTING frozen :func:`evaluate_shadow_experiment` — the
    algorithm, thresholds and status semantics are unchanged. The produced
    receipt is persisted through the append-only evaluation-receipt
    repository when one is supplied; the content-derived ``evaluation_id``
    makes re-persisting an identical evaluation a no-op.

    ``confirmatory=True`` requires ``canonical_context=True`` (WP2 gate d);
    gates (a)-(c): FROZEN binding, non-NULL durability, strict
    ``as_of > durable_freeze_at`` — are enforced by the existing binding
    failure semantics and surface as ``INVALID_DRIFT`` receipts. When a drift
    sentry is supplied (WP5), the bound freeze receipt is additionally
    recomputed against the live repository BEFORE evaluation; ANY drift
    yields a DRIFTED verification receipt and therefore an ``INVALID_DRIFT``
    evaluation under the EXISTING semantics (no new status). DEV runs are
    unaffected: the sentry only runs on the confirmatory path.
    """
    from frontier.application.evaluation_loaders import (  # runtime import avoids a cycle
        load_paired_snapshot,
    )

    if not runs:
        raise ValueError("persisted evaluation requires at least one persisted run")
    if len({ref.run_id for ref in runs}) != len(runs):
        raise ValueError("duplicate persisted run ids in evaluation request")

    from frontier.application.evaluation_loaders import PersistedEvaluationError

    run_rows = tuple(store.fetch_run_row(ref.run_id) for ref in runs)
    if any(row is None for row in run_rows):
        missing = next(ref.run_id for ref, row in zip(runs, run_rows, strict=True) if row is None)
        raise PersistedEvaluationError(f"missing shadow experiment run row for {missing}")
    persisted_classes = {row.run_class for row in run_rows if row is not None}
    if len(persisted_classes) != 1:
        raise PersistedEvaluationError(
            "persisted evaluation cannot mix DEV and CONFIRMATORY run classes"
        )
    persisted_confirmatory = next(iter(persisted_classes)) == "CONFIRMATORY"
    loaded = tuple(
        load_paired_snapshot(
            store,
            ref.run_id,
            as_of=ref.as_of,
            confirmatory=persisted_confirmatory,
            feature_batch_id=feature_batch_id,
        )
        for ref in runs
    )
    ordered = tuple(sorted(loaded, key=lambda item: item.snapshot.run.as_of))
    authority = _resolve_persisted_evaluation_authority(
        store,
        ordered,
        requested_confirmatory=confirmatory,
        canonical_context=canonical_context,
        durable_freeze_at_assertion=durable_freeze_at,
        window_start_assertion=window_start,
    )
    # The confirmatory binding semantics in ``evaluate_shadow_experiment``
    # compare every run's bound receipt against the evaluated receipt: runs
    # bound to a different freeze therefore surface as INVALID_DRIFT.
    freeze_receipt = ordered[0].freeze_receipt
    if authority.confirmatory and drift_sentry is not None:
        # WP5 drift sentry (fail-closed): ANY drift in the recomputed identity
        # invalidates the receipt BEFORE evaluation, reusing the existing
        # INVALID_DRIFT semantics. The verification receipt is transient —
        # the sentry never mutates or persists stored state.
        drift_report = drift_sentry.check(freeze_receipt, now=generated_at)
        if drift_report.status is DriftStatus.DRIFTED:
            freeze_receipt = drift_sentry.verify_receipt(freeze_receipt, now=generated_at)
    receipt = evaluate_shadow_experiment(
        snapshots=tuple(item.snapshot for item in ordered),
        opportunity_groups=opportunity_groups,
        freeze_receipt=freeze_receipt,
        evaluation_horizon=evaluation_horizon,
        generated_at=generated_at,
        durable_freeze_at=authority.durable_freeze_at,
        rank_cutoff_k=rank_cutoff_k,
    )
    if receipt_repository is not None:
        receipt_repository.record_receipt(receipt)
    return receipt
