"""Persisted-artifact loaders for the preregistered PEF_V0 evaluation (WP4, G2).

Closes Sprint-1 DEBT-5: ``evaluate_shadow_experiment`` previously consumed only
hand-assembled :class:`~frontier.application.evaluation.PairedSnapshot`
payloads. The loaders here reconstruct the paired snapshot DIRECTLY from the
durable stored experiment artifacts (``shadow_experiment_runs``,
``pef_ranking_artifacts``, ``baseline_intelligence_snapshots``,
``projection_receipts``, ``candidate_freeze_receipts``) under the strongest
identity discipline:

- every stored payload is RE-DIGESTED from its canonical JSON and compared
  against the stored digest column AND the content-derived row identity
  (run id / artifact id / snapshot id / receipt id) BEFORE it may contribute
  to a paired snapshot (digest recomputation, never trust);
- every rejection is an explicit :class:`PersistedEvaluationError`
  (fail-closed): missing run/artifact rows, wrong candidate id, wrong
  baseline/control snapshot binding, ``as_of`` mismatch, source-registry
  digest mismatch, unresolvable / digest-mismatched / DRIFTED freeze receipt,
  non-RAN candidate artifacts, candidate/control universe mismatch, and a DEV
  run on a confirmatory evaluation path.

Canonical membership source (documented choice): the paired episode universe
comes from the DIGEST-VERIFIED control snapshot payload (the run binds its
``snapshot_id`` and ``episode_universe_digest``, both recomputed here). WP3
``opportunity_memberships`` rows are per-anchor detection evidence, not the
run universe; the control snapshot is the one canonical structure both arms
provably ranked (``_require_paired_universe`` at run construction).

Feature-vector discipline: when the caller consumes feature vectors for the
run (``feature_batch_id``), every vector digest is recomputed from its stored
payload and every batch row's binding (control snapshot, episode universe,
``as_of``) must equal the run's.

Evaluation window identity: with ``window_start`` supplied, the loader binds
the preregistered ranking window shape (WP3 ``RANKING_WINDOW_SECONDS``) and
requires every run boundary to lie inside
``[window_start, window_start + window]``.

Confirmatory binding: ``confirmatory=True`` requires a CONFIRMATORY run row
(a DEV run is rejected). The remaining WP2 gates — a FROZEN bound receipt,
non-NULL ``durable_freeze_at``, strict ``as_of > durable_freeze_at`` — are
enforced by
:func:`frontier.application.evaluation.evaluate_shadow_experiment` under the
frozen evaluation semantics (they surface as ``INVALID_DRIFT`` receipts).
FAILED runs cannot feed a persisted evaluation: their candidate artifact is
not RAN, so this loader fails closed instead of fabricating an empty arm.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Protocol, cast

from frontier.application.opportunity_outcome import RANKING_WINDOW_SECONDS
from frontier.domain.advanced_intelligence import (
    BASELINE_ALGORITHM_VERSION,
    BASELINE_PROJECTION_NAME,
    BASELINE_PROJECTION_VERSION,
    BASELINE_RANKING_POLICY_VERSION,
    BASELINE_SCHEMA_VERSION,
    PEF_ALGORITHM_VERSION,
    PEF_AUTHORITY_STATE,
    PEF_CANDIDATE_ID,
    PEF_CONFIGURATION_DIGEST,
    PEF_EXPERIMENT_ID,
    PEF_SCHEMA_VERSION,
    SHADOW_RUN_ID_PREFIX,
    ShadowControlArmRanking,
    ShadowExperimentRun,
    ShadowRunStatus,
)
from frontier.domain.candidate_freeze import (
    FREEZE_RECEIPT_ID_PREFIX,
    CandidateFreezeReceipt,
    FreezeStatus,
    RegistryEntryDigest,
)
from frontier.domain.canonical_json import canonical_json_bytes
from frontier.domain.digests import Digest, sha256_digest, sha256_hex
from frontier.domain.health import HealthValue
from frontier.domain.receipt import ProjectionStatus

if TYPE_CHECKING:  # pragma: no cover - annotations only
    from frontier.application.evaluation import PairedSnapshot

CONFIRMATORY_RUN_CLASS = "CONFIRMATORY"
DEV_RUN_CLASS = "DEV"
RUN_CLASSES: tuple[str, ...] = (DEV_RUN_CLASS, CONFIRMATORY_RUN_CLASS)

SNAPSHOT_ID_PREFIX = "snapshot_"
ARTIFACT_ID_PREFIX = "artifact_"


class PersistedEvaluationError(ValueError):
    """A persisted experiment artifact failed a strong identity check (fail-closed)."""


def _require_mapping(value: object, what: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise PersistedEvaluationError(f"{what} payload is not a canonical mapping")
    return cast("Mapping[str, object]", value)


def _require_mapping_list(value: object, what: str) -> list[Mapping[str, object]]:
    if not isinstance(value, list):
        raise PersistedEvaluationError(f"{what} payload is not a list")
    items = cast("list[object]", value)
    return [_require_mapping(item, what) for item in items]


def _require_text(value: object, what: str) -> str:
    if not isinstance(value, str) or not value:
        raise PersistedEvaluationError(f"{what} is missing or not text")
    return value


def _optional_text(value: object, what: str) -> str | None:
    if value is None:
        return None
    return _require_text(value, what)


def _require_int(value: object, what: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise PersistedEvaluationError(f"{what} is not an integer")
    return value


def _parse_canonical_timestamp(value: object, what: str) -> datetime:
    if not isinstance(value, str):
        raise PersistedEvaluationError(f"{what} timestamp is missing")
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=UTC)
    except ValueError as error:
        raise PersistedEvaluationError(
            f"{what} timestamp is not frontier-canonical: {value}"
        ) from error


def _digest_field(value: object, what: str) -> Digest:
    text = _require_text(value, what)
    try:
        return Digest(text)
    except ValueError as error:
        raise PersistedEvaluationError(f"{what} is not a sha256 digest") from error


def _canonical_digest(payload: Mapping[str, object]) -> Digest:
    """Re-digest a stored canonical payload (digest recomputation, never trust)."""
    return sha256_digest(canonical_json_bytes(dict(payload)))


# ---------------------------------------------------------------------------
# Persisted row shapes (filled by the storage adapter; every digest column is
# a TEXT claim the loader recomputes from the payload before trusting it).
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PersistedRunRow:
    run_id: str
    run_digest: str
    run_class: str
    status: str
    run_json: dict[str, object]


@dataclass(frozen=True, slots=True)
class PersistedArtifactRow:
    artifact_id: str
    output_digest: str
    status: str
    receipt_id: str
    artifact_json: dict[str, object]


@dataclass(frozen=True, slots=True)
class PersistedBaselineSnapshotRow:
    snapshot_id: str
    output_digest: str
    receipt_id: str
    snapshot_json: dict[str, object]


@dataclass(frozen=True, slots=True)
class PersistedProjectionReceiptRow:
    receipt_id: str
    projection_name: str
    projection_version: str
    schema_version: str
    algorithm_version: str | None
    ranking_policy_version: str | None
    configuration_digest: str
    source_registry_version: str
    output_digest: str
    status: str


@dataclass(frozen=True, slots=True)
class PersistedFreezeReceiptRow:
    receipt_id: str
    receipt_digest: str
    status: str
    durable_freeze_at: datetime | None
    receipt_json: dict[str, object]


@dataclass(frozen=True, slots=True)
class PersistedFeatureVectorRow:
    vector_id: str
    batch_id: str
    batch_digest: str
    episode_id: str
    control_snapshot_id: str
    episode_universe_digest: str
    as_of: datetime
    vector_digest: str
    vector_json: dict[str, object]


class EvaluationArtifactStore(Protocol):
    """Narrow read-only read-plane over the persisted experiment artifacts."""

    def fetch_run_row(self, run_id: str) -> PersistedRunRow | None: ...
    def fetch_candidate_artifact_row(self, artifact_id: str) -> PersistedArtifactRow | None: ...
    def fetch_baseline_snapshot_row(
        self, snapshot_id: str
    ) -> PersistedBaselineSnapshotRow | None: ...
    def fetch_projection_receipt_row(
        self, receipt_id: str
    ) -> PersistedProjectionReceiptRow | None: ...
    def fetch_freeze_receipt_row(self, receipt_id: str) -> PersistedFreezeReceiptRow | None: ...
    def fetch_feature_batch_rows(self, batch_id: str) -> tuple[PersistedFeatureVectorRow, ...]: ...


@dataclass(frozen=True, slots=True)
class PersistedRunRef:
    """One requested persisted run boundary (run identity + expected ``as_of``)."""

    run_id: str
    as_of: datetime


@dataclass(frozen=True, slots=True)
class LoadedPairedSnapshot:
    """A digest-verified paired snapshot plus its resolved freeze receipt."""

    snapshot: PairedSnapshot
    run: ShadowExperimentRun
    freeze_receipt: CandidateFreezeReceipt
    run_class: str


# ---------------------------------------------------------------------------
# Canonical-payload reconstruction (self-validating dataclass constructors).
# ---------------------------------------------------------------------------


def _ranking_entry(entry: Mapping[str, object], what: str) -> ShadowControlArmRanking:
    rank = _require_int(entry.get("rank"), f"{what} control ranking entry rank")
    episode_id = _require_text(entry.get("episode_id"), f"{what} control ranking episode id")
    return ShadowControlArmRanking(rank=rank, episode_id=episode_id)


def shadow_run_from_canonical(payload: Mapping[str, object]) -> ShadowExperimentRun:
    """Reconstruct a :class:`ShadowExperimentRun` from its canonical JSON."""
    canonical = _require_mapping(payload, "run")
    ranking_payload = _require_mapping_list(
        canonical.get("control_ranking") or [], "run control_ranking"
    )
    return ShadowExperimentRun(
        as_of=_parse_canonical_timestamp(canonical.get("as_of"), "run"),
        generated_at=_parse_canonical_timestamp(canonical.get("generated_at"), "run"),
        control_snapshot_id=_require_text(canonical.get("control_snapshot_id"), "run"),
        control_receipt_id=_require_text(canonical.get("control_receipt_id"), "run"),
        coverage_state=HealthValue(_require_text(canonical.get("control_coverage_state"), "run")),
        freshness_state=HealthValue(_require_text(canonical.get("control_freshness_state"), "run")),
        transport_state=HealthValue(_require_text(canonical.get("control_transport_state"), "run")),
        schema_state=HealthValue(_require_text(canonical.get("control_schema_state"), "run")),
        status=ShadowRunStatus(_require_text(canonical.get("status"), "run status")),
        episode_universe_digest=_digest_field(
            canonical.get("episode_universe_digest"), "run episode universe digest"
        ),
        candidate_artifact_id=_require_text(
            canonical.get("candidate_artifact_id"), "run candidate artifact id"
        ),
        candidate_output_digest=_digest_field(
            canonical.get("candidate_output_digest"), "run candidate output digest"
        ),
        control_ranking=tuple(_ranking_entry(entry, "run") for entry in ranking_payload),
        failure_reason=_optional_text(canonical.get("failure_reason"), "run failure reason"),
        experiment_id=_require_text(canonical.get("experiment_id"), "run experiment id"),
        candidate_id=_require_text(canonical.get("candidate_id"), "run candidate id"),
        schema_version=_require_text(canonical.get("schema_version"), "run schema version"),
        algorithm_version=_require_text(canonical.get("algorithm_version"), "run algorithm"),
        configuration_digest=_digest_field(
            canonical.get("configuration_digest"), "run configuration digest"
        ),
        authority_state=_require_text(canonical.get("authority_state"), "run authority state"),
        candidate_freeze_receipt_id=_optional_text(
            canonical.get("candidate_freeze_receipt_id"), "run freeze receipt binding"
        ),
    )


def candidate_freeze_receipt_from_canonical(
    payload: Mapping[str, object],
) -> CandidateFreezeReceipt:
    """Reconstruct a :class:`CandidateFreezeReceipt` from its canonical JSON."""
    canonical = _require_mapping(payload, "freeze")
    entries_payload = canonical.get("registry_entry_digests")
    entries: tuple[RegistryEntryDigest, ...] | None
    if entries_payload is None:
        entries = None
    else:
        entries = tuple(
            RegistryEntryDigest(
                path=_require_text(entry.get("path"), "freeze entry path"),
                digest=_digest_field(entry.get("digest"), "freeze entry digest"),
            )
            for entry in _require_mapping_list(entries_payload, "freeze registry entries")
        )
    verified_at = canonical.get("verified_at")
    drift_reasons: list[str] = []
    drift_raw = canonical.get("drift_reasons")
    if drift_raw is not None:
        if not isinstance(drift_raw, list):
            raise PersistedEvaluationError("freeze drift reasons are not a list")
        for reason in cast("list[object]", drift_raw):
            if not isinstance(reason, str):
                raise PersistedEvaluationError("freeze drift reason is not text")
            drift_reasons.append(reason)
    original = canonical.get("original_receipt_digest")
    return CandidateFreezeReceipt(
        frozen_at=_parse_canonical_timestamp(canonical.get("frozen_at"), "freeze"),
        status=FreezeStatus(_require_text(canonical.get("status"), "freeze status")),
        drift_reasons=tuple(drift_reasons),
        preregistration_digest=_digest_field(
            canonical.get("preregistration_digest"), "freeze preregistration digest"
        ),
        preregistration_config_digest=(
            None
            if canonical.get("preregistration_config_digest") is None
            else _digest_field(
                canonical.get("preregistration_config_digest"), "freeze prereg config digest"
            )
        ),
        implementation_commit=_optional_text(
            canonical.get("implementation_commit"), "freeze implementation commit"
        ),
        implementation_tree_digest=_optional_text(
            canonical.get("implementation_tree_digest"), "freeze implementation tree digest"
        ),
        dependency_lock_digest=(
            None
            if canonical.get("dependency_lock_digest") is None
            else _digest_field(
                canonical.get("dependency_lock_digest"), "freeze dependency lock digest"
            )
        ),
        source_registry_digest=(
            None
            if canonical.get("source_registry_digest") is None
            else _digest_field(
                canonical.get("source_registry_digest"), "freeze source registry digest"
            )
        ),
        registry_entry_digests=entries,
        candidate_id=_require_text(canonical.get("candidate_id"), "freeze candidate id"),
        experiment_id=_require_text(canonical.get("experiment_id"), "freeze experiment id"),
        algorithm_version=_require_text(canonical.get("algorithm_version"), "freeze algorithm"),
        configuration_digest=_digest_field(
            canonical.get("configuration_digest"), "freeze configuration digest"
        ),
        preregistration_path=_require_text(
            canonical.get("preregistration_path"), "freeze preregistration path"
        ),
        schema_version=_require_text(canonical.get("schema_version"), "freeze schema version"),
        verified_at=(
            None if verified_at is None else _parse_canonical_timestamp(verified_at, "freeze")
        ),
        original_receipt_digest=(
            None if original is None else _digest_field(original, "freeze original digest")
        ),
    )


# ---------------------------------------------------------------------------
# Loader internals.
# ---------------------------------------------------------------------------


def _episode_membership_universe(episodes_payload: object, what: str) -> dict[str, tuple[str, ...]]:
    universe: dict[str, tuple[str, ...]] = {}
    for entry in _require_mapping_list(episodes_payload, what):
        episode_id = _require_text(entry.get("episode_id"), f"{what} episode id")
        observation_ids = entry.get("observation_ids")
        if not isinstance(observation_ids, list):
            raise PersistedEvaluationError(f"{what} episode {episode_id!r} has no member list")
        members: list[str] = []
        for member in cast("list[object]", observation_ids):
            if not isinstance(member, str):
                raise PersistedEvaluationError(f"{what} episode {episode_id!r} member id not text")
            members.append(member)
        if episode_id in universe:
            raise PersistedEvaluationError(f"{what} contains duplicate episode ids")
        universe[episode_id] = tuple(members)
    return universe


def _universe_digest(snapshot_payload: Mapping[str, object], snapshot_id: str) -> Digest:
    """Recompute ``shadow_universe_digest`` from the stored snapshot payload."""
    universe = _episode_membership_universe(snapshot_payload.get("episodes"), "snapshot")
    material: dict[str, object] = {
        "as_of": snapshot_payload.get("as_of"),
        "episodes": [
            {"episode_id": episode_id, "observation_ids": list(universe[episode_id])}
            for episode_id in sorted(universe)
        ],
        "snapshot_id": snapshot_id,
    }
    return sha256_digest(canonical_json_bytes(material))


def _require_control_receipt_identity(
    receipt: PersistedProjectionReceiptRow, snapshot_id: str
) -> None:
    """``_require_control_identity`` semantics against the stored receipt row."""
    if receipt.status != ProjectionStatus.COMPLETE.value:
        raise PersistedEvaluationError("control snapshot receipt is not COMPLETE")
    if receipt.output_digest.removeprefix("sha256:") != snapshot_id.removeprefix(
        SNAPSHOT_ID_PREFIX
    ):
        raise PersistedEvaluationError("control receipt does not bind the given control snapshot")
    if receipt.projection_name != BASELINE_PROJECTION_NAME:
        raise PersistedEvaluationError("control receipt projection name mismatch")
    if receipt.projection_version != BASELINE_PROJECTION_VERSION:
        raise PersistedEvaluationError("control receipt projection version mismatch")
    if receipt.schema_version != BASELINE_SCHEMA_VERSION:
        raise PersistedEvaluationError("control receipt schema version mismatch")
    if receipt.algorithm_version != BASELINE_ALGORITHM_VERSION:
        raise PersistedEvaluationError("control receipt algorithm version mismatch")
    if receipt.ranking_policy_version != BASELINE_RANKING_POLICY_VERSION:
        raise PersistedEvaluationError("control receipt ranking policy version mismatch")


def _load_and_verify_run(
    store: EvaluationArtifactStore, *, run_id: str, as_of: datetime
) -> ShadowExperimentRun:
    row = store.fetch_run_row(run_id)
    if row is None:
        raise PersistedEvaluationError(f"missing shadow experiment run row for {run_id}")
    if row.run_id != run_id:
        raise PersistedEvaluationError("run row identity does not match the requested run id")
    if row.run_class not in RUN_CLASSES:
        raise PersistedEvaluationError(f"run row carries unknown run_class {row.run_class!r}")
    run = shadow_run_from_canonical(row.run_json)
    # Digest recomputation: the canonical payload must re-derive BOTH the
    # stored digest column and the content-derived run id.
    recomputed = _canonical_digest(row.run_json)
    if recomputed != run.run_digest:
        raise PersistedEvaluationError("run payload does not re-digest to its own digest")
    if str(recomputed) != row.run_digest:
        raise PersistedEvaluationError("stored run digest column does not bind the run payload")
    if SHADOW_RUN_ID_PREFIX + sha256_hex(canonical_json_bytes(row.run_json)) != run_id:
        raise PersistedEvaluationError("run payload does not re-derive the requested run id")
    if run.as_of != as_of:
        raise PersistedEvaluationError(
            "run as_of mismatch: persisted run boundary does not equal the requested as_of"
        )
    if run.experiment_id != PEF_EXPERIMENT_ID:
        raise PersistedEvaluationError("run experiment id mismatch")
    if run.candidate_id != PEF_CANDIDATE_ID:
        raise PersistedEvaluationError("run candidate id mismatch")
    if run.algorithm_version != PEF_ALGORITHM_VERSION:
        raise PersistedEvaluationError("run algorithm version mismatch")
    if run.configuration_digest != PEF_CONFIGURATION_DIGEST:
        raise PersistedEvaluationError("run configuration digest mismatch")
    return run


def _load_and_verify_candidate_artifact(
    store: EvaluationArtifactStore, run: ShadowExperimentRun
) -> tuple[
    Mapping[str, object],
    dict[str, tuple[str, ...]],
    dict[str, int],
    PersistedProjectionReceiptRow,
]:
    artifact_row = store.fetch_candidate_artifact_row(run.candidate_artifact_id)
    if artifact_row is None:
        raise PersistedEvaluationError(
            f"missing candidate ranking artifact {run.candidate_artifact_id}"
        )
    if artifact_row.artifact_id != run.candidate_artifact_id:
        raise PersistedEvaluationError("candidate artifact row identity mismatch")
    artifact = _require_mapping(artifact_row.artifact_json, "artifact")
    # Digest recomputation: a tampered payload cannot re-derive the bound
    # artifact id nor the run's candidate output digest.
    recomputed = _canonical_digest(artifact)
    if recomputed != run.candidate_output_digest:
        raise PersistedEvaluationError(
            "artifact payload does not re-digest the run's candidate output digest"
        )
    if str(recomputed) != artifact_row.output_digest:
        raise PersistedEvaluationError(
            "stored artifact digest column does not bind the artifact payload"
        )
    if ARTIFACT_ID_PREFIX + sha256_hex(canonical_json_bytes(artifact)) != artifact_row.artifact_id:
        raise PersistedEvaluationError("artifact payload does not re-derive its id")
    if artifact_row.status != "RAN" or _require_text(artifact.get("status"), "artifact") != "RAN":
        raise PersistedEvaluationError("artifact is not a COMPLETE (RAN) ranking artifact")
    if _require_text(artifact.get("experiment_id"), "artifact") != PEF_EXPERIMENT_ID:
        raise PersistedEvaluationError("artifact experiment id mismatch")
    if _require_text(artifact.get("candidate_id"), "artifact candidate id") != PEF_CANDIDATE_ID:
        raise PersistedEvaluationError("artifact candidate id mismatch")
    if _require_text(artifact.get("schema_version"), "artifact") != PEF_SCHEMA_VERSION:
        raise PersistedEvaluationError("artifact schema version mismatch")
    if _require_text(artifact.get("algorithm_version"), "artifact") != PEF_ALGORITHM_VERSION:
        raise PersistedEvaluationError("artifact algorithm version mismatch")
    if _digest_field(artifact.get("configuration_digest"), "artifact") != PEF_CONFIGURATION_DIGEST:
        raise PersistedEvaluationError("artifact configuration digest mismatch")
    if _require_text(artifact.get("authority_state"), "artifact") != PEF_AUTHORITY_STATE:
        raise PersistedEvaluationError("artifact authority state mismatch")
    if _require_text(artifact.get("control_snapshot_id"), "artifact") != run.control_snapshot_id:
        raise PersistedEvaluationError("artifact does not bind the run's control snapshot")
    if _require_text(artifact.get("control_receipt_id"), "artifact") != run.control_receipt_id:
        raise PersistedEvaluationError("artifact does not bind the run's control receipt")
    artifact_as_of = _parse_canonical_timestamp(artifact.get("as_of"), "artifact")
    if artifact_as_of != run.as_of:
        raise PersistedEvaluationError("artifact as_of mismatch with the run")

    receipt_row = store.fetch_projection_receipt_row(artifact_row.receipt_id)
    if receipt_row is None:
        raise PersistedEvaluationError("candidate artifact projection receipt is unresolvable")
    if receipt_row.status != ProjectionStatus.COMPLETE.value:
        raise PersistedEvaluationError("artifact receipt status is not COMPLETE")
    if receipt_row.output_digest != artifact_row.output_digest:
        raise PersistedEvaluationError("artifact receipt output digest mismatch")
    if receipt_row.schema_version != PEF_SCHEMA_VERSION:
        raise PersistedEvaluationError("artifact receipt schema version mismatch")
    artifact_registry = _digest_field(
        artifact.get("source_registry_version"), "artifact source registry digest"
    )
    if receipt_row.source_registry_version != str(artifact_registry):
        raise PersistedEvaluationError(
            "artifact source registry digest mismatch with its bound receipt"
        )
    episodes_payload = artifact.get("episodes")
    candidate_universe = _episode_membership_universe(episodes_payload, "artifact")
    candidate_ranks: dict[str, int] = {}
    for entry in _require_mapping_list(episodes_payload or [], "artifact episodes"):
        episode_id = _require_text(entry.get("episode_id"), "artifact episode id")
        candidate_ranks[episode_id] = _require_int(entry.get("rank"), "artifact episode rank")
    return artifact, candidate_universe, candidate_ranks, receipt_row


def _load_and_verify_control_snapshot(
    store: EvaluationArtifactStore, run: ShadowExperimentRun
) -> tuple[Mapping[str, object], dict[str, tuple[str, ...]], PersistedProjectionReceiptRow]:
    snapshot_row = store.fetch_baseline_snapshot_row(run.control_snapshot_id)
    if snapshot_row is None:
        raise PersistedEvaluationError(
            f"missing control baseline snapshot {run.control_snapshot_id}"
        )
    if snapshot_row.snapshot_id != run.control_snapshot_id:
        raise PersistedEvaluationError("control snapshot row identity mismatch")
    if snapshot_row.receipt_id != run.control_receipt_id:
        raise PersistedEvaluationError(
            "control snapshot binding mismatch: row binds a different projection receipt"
        )
    snapshot = _require_mapping(snapshot_row.snapshot_json, "snapshot")
    recomputed = _canonical_digest(snapshot)
    if SNAPSHOT_ID_PREFIX + sha256_hex(canonical_json_bytes(snapshot)) != run.control_snapshot_id:
        raise PersistedEvaluationError(
            "snapshot payload does not re-derive the run's control snapshot id"
        )
    if str(recomputed) != snapshot_row.output_digest:
        raise PersistedEvaluationError(
            "stored snapshot digest column does not bind the snapshot payload"
        )
    receipt_row = store.fetch_projection_receipt_row(snapshot_row.receipt_id)
    if receipt_row is None:
        raise PersistedEvaluationError("control snapshot projection receipt is unresolvable")
    _require_control_receipt_identity(receipt_row, run.control_snapshot_id)
    if receipt_row.output_digest != snapshot_row.output_digest:
        raise PersistedEvaluationError("control receipt output digest does not bind the snapshot")
    snapshot_as_of = _parse_canonical_timestamp(snapshot.get("as_of"), "snapshot")
    if snapshot_as_of != run.as_of:
        raise PersistedEvaluationError("control snapshot as_of mismatch with the run boundary")
    universe = _episode_membership_universe(snapshot.get("episodes"), "snapshot")
    if _universe_digest(snapshot, run.control_snapshot_id) != run.episode_universe_digest:
        raise PersistedEvaluationError(
            "control snapshot universe does not re-digest the run's episode universe digest"
        )
    return snapshot, universe, receipt_row


def _load_and_verify_freeze_receipt(
    store: EvaluationArtifactStore, run: ShadowExperimentRun
) -> CandidateFreezeReceipt:
    receipt_id = run.candidate_freeze_receipt_id
    if receipt_id is None:
        raise PersistedEvaluationError(
            "persisted evaluation requires a bound candidate freeze receipt on the run"
        )
    if not receipt_id.startswith(FREEZE_RECEIPT_ID_PREFIX):
        raise PersistedEvaluationError("run binds an invalid candidate freeze receipt id")
    row = store.fetch_freeze_receipt_row(receipt_id)
    if row is None:
        raise PersistedEvaluationError(f"bound freeze receipt {receipt_id} is unresolvable")
    if row.receipt_id != receipt_id:
        raise PersistedEvaluationError("freeze receipt row identity mismatch")
    receipt = candidate_freeze_receipt_from_canonical(row.receipt_json)
    # Digest recomputation: the canonical payload must re-derive both the
    # stored digest column and the content-derived receipt id.
    if receipt.receipt_digest != _canonical_digest(row.receipt_json):
        raise PersistedEvaluationError("freeze receipt payload does not re-digest its own digest")
    if str(receipt.receipt_digest) != row.receipt_digest:
        raise PersistedEvaluationError(
            "stored freeze receipt digest column does not bind the receipt payload"
        )
    if receipt.receipt_id != receipt_id:
        raise PersistedEvaluationError(
            "freeze receipt payload does not re-derive the run's bound receipt id"
        )
    if receipt.status is FreezeStatus.DRIFTED:
        raise PersistedEvaluationError("bound candidate freeze receipt is DRIFTED")
    if receipt.status is not FreezeStatus.FROZEN:
        raise PersistedEvaluationError(
            f"bound freeze receipt status {receipt.status.value} is not FROZEN"
        )
    return receipt


def _verify_feature_batch(
    store: EvaluationArtifactStore, run: ShadowExperimentRun, batch_id: str
) -> None:
    rows = store.fetch_feature_batch_rows(batch_id)
    if not rows:
        raise PersistedEvaluationError(f"feature vector batch {batch_id} is missing or empty")
    if len({row.batch_digest for row in rows}) != 1:
        raise PersistedEvaluationError("feature vector batch rows disagree on the batch digest")
    for row in rows:
        if row.batch_id != batch_id:
            raise PersistedEvaluationError("feature vector row batch binding mismatch")
        if str(_canonical_digest(row.vector_json)) != row.vector_digest:
            raise PersistedEvaluationError(
                "feature vector payload does not re-digest its stored digest (tampered vector)"
            )
        if row.control_snapshot_id != run.control_snapshot_id:
            raise PersistedEvaluationError(
                "feature vector batch does not bind the run's control snapshot"
            )
        if row.episode_universe_digest != str(run.episode_universe_digest):
            raise PersistedEvaluationError(
                "feature vector batch universe digest mismatch with the run's paired universe"
            )
        if row.as_of != run.as_of:
            raise PersistedEvaluationError("feature vector batch as_of mismatch with the run")


def _require_window_identity(run: ShadowExperimentRun, *, window_start: datetime) -> None:
    if window_start.tzinfo is None or window_start.utcoffset() is None:
        raise PersistedEvaluationError("evaluation window start must be timezone-aware")
    window_end = datetime.fromtimestamp(
        int(window_start.timestamp()) + RANKING_WINDOW_SECONDS, tz=UTC
    )
    if not (window_start <= run.as_of <= window_end):
        raise PersistedEvaluationError(
            "run boundary lies outside the bound preregistered evaluation window"
        )


def _mirrored_control_ranking(
    snapshot_payload: Mapping[str, object],
) -> tuple[ShadowControlArmRanking, ...]:
    entries = _require_mapping_list(snapshot_payload.get("episodes") or [], "snapshot episodes")
    ranked = sorted(entries, key=lambda entry: _require_int(entry.get("rank"), "snapshot rank"))
    return tuple(
        ShadowControlArmRanking(
            rank=_require_int(entry.get("rank"), "snapshot rank"),
            episode_id=_require_text(entry.get("episode_id"), "snapshot episode id"),
        )
        for entry in ranked
    )


def load_paired_snapshot(
    store: EvaluationArtifactStore,
    run_id: str,
    *,
    as_of: datetime,
    confirmatory: bool = False,
    window_start: datetime | None = None,
    feature_batch_id: str | None = None,
    expected_registry: Digest | None = None,
) -> LoadedPairedSnapshot:
    """Load one digest-verified paired snapshot from the persisted artifacts.

    ``as_of`` is the expected boundary (e.g. from the orchestration attempt
    record); a mismatch with the run row fails closed. ``confirmatory=True``
    additionally requires a CONFIRMATORY run row (a DEV run is rejected).
    The remaining confirmatory binding gates — FROZEN receipt binding, non-NULL
    ``durable_freeze_at``, strict ``as_of > durable_freeze_at`` — are enforced
    by :func:`frontier.application.evaluation.evaluate_shadow_experiment`
    under the frozen evaluation semantics (they surface as INVALID_DRIFT).
    """
    run_row = store.fetch_run_row(run_id)
    if run_row is None:
        raise PersistedEvaluationError(f"missing shadow experiment run row for {run_id}")
    if run_row.run_class not in RUN_CLASSES:
        raise PersistedEvaluationError(f"run row carries unknown run_class {run_row.run_class!r}")
    if confirmatory and run_row.run_class != CONFIRMATORY_RUN_CLASS:
        raise PersistedEvaluationError(
            f"a DEV run cannot feed a confirmatory persisted evaluation "
            f"(run_class={run_row.run_class!r})"
        )
    run = _load_and_verify_run(store, run_id=run_id, as_of=as_of)
    artifact, candidate_universe, candidate_ranks, candidate_receipt = (
        _load_and_verify_candidate_artifact(store, run)
    )
    snapshot_payload, universe, control_receipt = _load_and_verify_control_snapshot(store, run)
    freeze_receipt = _load_and_verify_freeze_receipt(store, run)
    # Wrong source registry: the control snapshot receipt and the candidate
    # artifact receipt must bind the identical registry version.
    if candidate_receipt.source_registry_version != control_receipt.source_registry_version:
        raise PersistedEvaluationError(
            "wrong source registry: run and candidate artifact bind different registry digests"
        )

    if run.status is not ShadowRunStatus.RAN:
        raise PersistedEvaluationError(
            "persisted evaluation requires a RAN run: a FAILED run carries no candidate arm"
        )
    if candidate_universe != universe:
        raise PersistedEvaluationError("candidate/control episode membership universe mismatch")
    if run.control_ranking != _mirrored_control_ranking(snapshot_payload):
        raise PersistedEvaluationError(
            "run control ranking does not mirror the digest-verified control snapshot"
        )

    if window_start is not None:
        _require_window_identity(run, window_start=window_start)
    if expected_registry is not None:
        artifact_registry = _digest_field(
            artifact.get("source_registry_version"), "artifact source registry digest"
        )
        if artifact_registry != expected_registry:
            raise PersistedEvaluationError(
                "artifact source registry digest mismatch with the expected registry"
            )
    if feature_batch_id is not None:
        _verify_feature_batch(store, run, feature_batch_id)

    from frontier.application.evaluation import PairedSnapshot  # runtime import avoids a cycle

    return LoadedPairedSnapshot(
        snapshot=PairedSnapshot(
            run=run,
            candidate_rank_by_episode=candidate_ranks,
            episode_memberships=universe,
        ),
        run=run,
        freeze_receipt=freeze_receipt,
        run_class=run_row.run_class,
    )


__all__ = [
    "CONFIRMATORY_RUN_CLASS",
    "DEV_RUN_CLASS",
    "RUN_CLASSES",
    "EvaluationArtifactStore",
    "LoadedPairedSnapshot",
    "PersistedArtifactRow",
    "PersistedBaselineSnapshotRow",
    "PersistedEvaluationError",
    "PersistedFeatureVectorRow",
    "PersistedFreezeReceiptRow",
    "PersistedProjectionReceiptRow",
    "PersistedRunRef",
    "PersistedRunRow",
    "candidate_freeze_receipt_from_canonical",
    "load_paired_snapshot",
    "shadow_run_from_canonical",
]
