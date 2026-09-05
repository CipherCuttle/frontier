"""EXPERIMENTAL richer experimental analysis artifacts (sprint slice F).

Six artifact kinds over the shared control-grouping episode universe:

- ``GROUPING_HYPOTHESES`` — candidate merge/split suggestions with reasons,
  NEVER authoritative; the frozen grouping baseline is untouched.
- ``ENTITY_PROVENANCE`` — candidate entity links and provenance hypotheses,
  explicitly HYPOTHESIS; earliest observed is never true origin.
- ``CORROBORATION`` — structured cross-source corroboration descriptors
  (distinct sources, lane diversity, time spread). The forbidden mapping
  ``source_count → independent_confirmation`` is structurally impossible:
  no such key can appear (enforced by :func:`forbid_truth_keys` and tests).
- ``PROPAGATION_GRAPH`` — deterministic directed adjacency graph of episode
  observation flow across source/lane endpoints within the observation
  window; descriptor only, no truth semantics.
- ``INDICATORS`` — interpretable manipulation/reflexivity indicators with
  explicit UNKNOWN; never a manipulation verdict.
- ``TRAJECTORY`` — per-episode trajectory projection across stored
  EXPERIMENTAL_SHADOW artifacts (feature-vector batches and optional PEF
  candidate artifacts); read-only projection, labelled EXPERIMENTAL_SHADOW.

Hard properties (ZOOCODE_SPRINT1.md):

- R1 point-in-time: everything is computed from member observations with
  ``observed_at <= as_of`` only.
- R3 backfill safety: only prospective-eligible member observations
  (``BaselineObservationInput.is_prospective``) feed any analysis.
- R4 coverage: unobservable descriptors are explicit UNKNOWN/None and are
  never silently coerced to zero or a healthy value.
- R7 epistemic non-escalation: every artifact carries a hypothesis-level
  status (HYPOTHESIS / DESCRIPTOR / INDICATORS / PROJECTION) and
  authority_state EXPERIMENTAL_SHADOW. No artifact can carry a
  truth-escalation key: :func:`forbid_truth_keys` rejects payloads that
  contain ``independent_confirmation``, confirmation counts, true-origin
  verdicts, or manipulation verdicts at any nesting depth.
- R8 replay: artifacts are deterministic, canonical-JSON serialized,
  digest-bound to the exact evidence, configuration, and snapshot identity.
  Builders fail closed: invalid inputs raise, no partial artifact exists.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from itertools import combinations, pairwise

from .advanced_intelligence import (
    PefArtifact,
    PefArtifactStatus,
    pef_input_digest,
    shadow_universe_digest,
)
from .canonical_json import CanonicalValue, canonical_json_bytes, canonical_timestamp
from .digests import Digest, sha256_digest, sha256_hex
from .features import (
    FeatureStatus,
    FeatureValue,
    FeatureVectorBatch,
    FeatureVectorStatus,
)
from .intelligence import BaselineObservationInput, BaselineSnapshot
from .receipt import ProjectionReceipt, ProjectionStatus

EXPERIMENTAL_ANALYSIS_SCHEMA_VERSION = "experimental-analysis-v0"
EXPERIMENTAL_ANALYSIS_ALGORITHM_VERSION = "experimental-analysis-v0"
EXPERIMENTAL_ANALYSIS_AUTHORITY_STATE = "EXPERIMENTAL_SHADOW"
EXPERIMENTAL_ANALYSIS_ID_PREFIX = "expanalysis_"
EXPERIMENTAL_ANALYSIS_INTERPRETATION = (
    "EXPERIMENTAL analysis artifact; hypothesis-level descriptors only; never "
    "evidence of truth, factual confidence, independent confirmation, provenance "
    "origin, entity certainty, a manipulation verdict, or importance"
)

PRIMARY_EMISSION_ROLE = "PRIMARY_EMISSION"
ANALYSIS_OBSERVATION_WINDOW_SECONDS = 86400
PROPAGATION_GRAPH_WINDOW_SECONDS = 86400
ENTITY_LINK_WINDOW_SECONDS = 259200
INDICATOR_BURST_WINDOW_SECONDS = 3600

_INDICATOR_ORDER: tuple[str, ...] = (
    "burst_rate_excess",
    "same_source_adjacency",
    "identical_timing_gap_run",
)

_EXPERIMENTAL_STATUSES: list[CanonicalValue] = [
    "HYPOTHESIS",
    "DESCRIPTOR",
    "INDICATORS",
    "PROJECTION",
]

EXPERIMENTAL_ANALYSIS_CONFIGURATION: dict[str, CanonicalValue] = {
    "algorithm_version": EXPERIMENTAL_ANALYSIS_ALGORITHM_VERSION,
    "authority_state": EXPERIMENTAL_ANALYSIS_AUTHORITY_STATE,
    "baseline_relationship": "BASELINE_GROUPING_AND_RANKING_NEVER_MODIFIED",
    "corroboration_semantics": (
        "DESCRIPTOR_ONLY; cross-source multiplicity is not independent "
        "confirmation and no confirmation field can exist"
    ),
    "entity_link_window_seconds": ENTITY_LINK_WINDOW_SECONDS,
    "forbidden_truth_mappings": [
        "source_count_to_independent_confirmation",
        "earliest_observed_to_true_origin",
        "indicator_to_manipulation_verdict",
    ],
    "hypothesis_status": "HYPOTHESIS",
    "indicator_burst_window_seconds": INDICATOR_BURST_WINDOW_SECONDS,
    "indicator_order": [order for order in _INDICATOR_ORDER],
    "interpretation": EXPERIMENTAL_ANALYSIS_INTERPRETATION,
    "observation_window_seconds": ANALYSIS_OBSERVATION_WINDOW_SECONDS,
    "primary_emission_role": PRIMARY_EMISSION_ROLE,
    "propagation_graph_window_seconds": PROPAGATION_GRAPH_WINDOW_SECONDS,
    "score_semantics": "NO_SCALAR_SCORE_INTERPRETABLE_HYPOTHESES_AND_DESCRIPTORS_ONLY",
    "statuses": _EXPERIMENTAL_STATUSES,
}
EXPERIMENTAL_ANALYSIS_CONFIGURATION_DIGEST = sha256_digest(
    canonical_json_bytes(EXPERIMENTAL_ANALYSIS_CONFIGURATION)
)

FORBIDDEN_TRUTH_KEYS: frozenset[str] = frozenset(
    {
        "confirmation",
        "confirmation_count",
        "confirmations",
        "confirmed_by",
        "entity_certainty",
        "factual_confidence",
        "independent_confirmation",
        "independent_confirmation_count",
        "independent_confirmations",
        "manipulation_verdict",
        "origin_verdict",
        "true_origin",
        "true_origin_at",
        "true_origin_source",
        "truth_probability",
    }
)

_ORIGIN_INTERPRETATION = (
    "earliest-observed-within-point-in-time-evidence; coverage-limited; "
    "NEVER a factual origin claim (earliest observed is not true origin)"
)
_SAME_ENTITY_INTERPRETATION = (
    "same-entity SUSPECTED because of shared identifiers within the evidence "
    "window; hypothesis only, never entity certainty"
)
_CORROBORATION_SEMANTICS = (
    "cross-source multiplicity descriptor only; source multiplicity is not "
    "independent confirmation and no confirmation field exists in this artifact"
)
_PROPAGATION_SEMANTICS = (
    "directed adjacency of prospective-eligible windowed member observations "
    "within each control grouping episode; observational flow descriptor "
    "with no truth semantics"
)
_GROUPING_BASELINE_RELATIONSHIP = (
    "EXPERIMENTAL_SUGGESTIONS_ONLY; the frozen grouping baseline is never "
    "touched and these hypotheses are never authoritative grouping"
)


class ExperimentalAnalysisKind(StrEnum):
    """Kind of an EXPERIMENTAL analysis artifact (persistence CHECK value)."""

    GROUPING_HYPOTHESES = "GROUPING_HYPOTHESES"
    ENTITY_PROVENANCE = "ENTITY_PROVENANCE"
    CORROBORATION = "CORROBORATION"
    PROPAGATION_GRAPH = "PROPAGATION_GRAPH"
    INDICATORS = "INDICATORS"
    TRAJECTORY = "TRAJECTORY"


class ExperimentalAnalysisStatus(StrEnum):
    """Explicit hypothesis-level epistemic status of an analysis artifact (R7).

    None of these statuses grant factual authority: HYPOTHESIS is a candidate
    suggestion, DESCRIPTOR is a structured description of evidence, INDICATORS
    are interpretable indicator values, and PROJECTION is a read-only view
    over stored EXPERIMENTAL_SHADOW artifacts.
    """

    HYPOTHESIS = "HYPOTHESIS"
    DESCRIPTOR = "DESCRIPTOR"
    INDICATORS = "INDICATORS"
    PROJECTION = "PROJECTION"


_KIND_STATUS: dict[ExperimentalAnalysisKind, ExperimentalAnalysisStatus] = {
    ExperimentalAnalysisKind.GROUPING_HYPOTHESES: ExperimentalAnalysisStatus.HYPOTHESIS,
    ExperimentalAnalysisKind.ENTITY_PROVENANCE: ExperimentalAnalysisStatus.HYPOTHESIS,
    ExperimentalAnalysisKind.CORROBORATION: ExperimentalAnalysisStatus.DESCRIPTOR,
    ExperimentalAnalysisKind.PROPAGATION_GRAPH: ExperimentalAnalysisStatus.DESCRIPTOR,
    ExperimentalAnalysisKind.INDICATORS: ExperimentalAnalysisStatus.INDICATORS,
    ExperimentalAnalysisKind.TRAJECTORY: ExperimentalAnalysisStatus.PROJECTION,
}

_SNAPSHOT_BOUND_KINDS = frozenset(ExperimentalAnalysisKind) - {
    ExperimentalAnalysisKind.TRAJECTORY,
}


def forbid_truth_keys(value: CanonicalValue) -> None:
    """Recursively reject forbidden truth-escalation keys (R7, structural).

    This makes the forbidden mappings (``source_count →
    independent_confirmation``, ``earliest observed → true origin``,
    ``indicator → manipulation verdict``) structurally impossible: no
    serialized analysis payload may contain such a key at any depth.
    """
    if isinstance(value, dict):
        for key, item in value.items():
            if key in FORBIDDEN_TRUTH_KEYS:
                raise ValueError(f"forbidden truth-mapping key in analysis payload: {key}")
            forbid_truth_keys(item)
    elif isinstance(value, list):
        for item in value:
            forbid_truth_keys(item)


def scan_truth_keys(value: CanonicalValue) -> list[str]:
    """Return every forbidden truth-escalation key present (test helper)."""
    found: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key in FORBIDDEN_TRUTH_KEYS:
                found.append(key)
            found.extend(scan_truth_keys(item))
    elif isinstance(value, list):
        for item in value:
            found.extend(scan_truth_keys(item))
    return found


@dataclass(frozen=True, slots=True)
class TrajectoryFrame:
    """One stored EXPERIMENTAL_SHADOW snapshot feeding a trajectory projection.

    The feature batch is mandatory and must be RAN; the PEF candidate artifact
    is optional and must cover the same ``as_of`` when present.
    """

    feature_batch: FeatureVectorBatch
    pef_artifact: PefArtifact | None = None

    def __post_init__(self) -> None:
        if self.feature_batch.status is not FeatureVectorStatus.RAN:
            raise ValueError("trajectory frames require RAN feature batches")
        if self.pef_artifact is not None:
            if self.pef_artifact.status is not PefArtifactStatus.RAN:
                raise ValueError("trajectory frames require RAN pef artifacts")
            if self.pef_artifact.as_of != self.feature_batch.as_of:
                raise ValueError("trajectory pef artifact as_of must match its frame batch")


@dataclass(frozen=True, slots=True)
class ExperimentalAnalysisArtifact:
    """Digest-bound EXPERIMENTAL analysis artifact envelope (R7, R8).

    Snapshot-bound kinds (all except TRAJECTORY) bind the exact control
    snapshot identity, receipt id, episode-universe digest, and source
    registry version. The TRAJECTORY kind binds stored frame digests and
    carries no control snapshot identity.
    """

    kind: ExperimentalAnalysisKind
    as_of: datetime
    generated_at: datetime
    status: ExperimentalAnalysisStatus
    payload: dict[str, CanonicalValue]
    control_snapshot_id: str | None = None
    control_receipt_id: str | None = None
    source_registry_version: Digest | None = None
    episode_universe_digest: Digest | None = None
    schema_version: str = EXPERIMENTAL_ANALYSIS_SCHEMA_VERSION
    algorithm_version: str = EXPERIMENTAL_ANALYSIS_ALGORITHM_VERSION
    configuration_digest: Digest = EXPERIMENTAL_ANALYSIS_CONFIGURATION_DIGEST
    authority_state: str = EXPERIMENTAL_ANALYSIS_AUTHORITY_STATE
    interpretation: str = EXPERIMENTAL_ANALYSIS_INTERPRETATION

    def __post_init__(self) -> None:
        if self.as_of.tzinfo is None or self.as_of.utcoffset() is None:
            raise ValueError("experimental analysis as_of must be timezone-aware")
        if self.generated_at.tzinfo is None or self.generated_at.utcoffset() is None:
            raise ValueError("experimental analysis generated_at must be timezone-aware")
        if self.status is ExperimentalAnalysisStatus.PROJECTION and (
            self.kind is not ExperimentalAnalysisKind.TRAJECTORY
        ):
            raise ValueError("PROJECTION status is only valid for TRAJECTORY artifacts")
        if self.kind in _SNAPSHOT_BOUND_KINDS:
            if self.control_snapshot_id is None or self.control_receipt_id is None:
                raise ValueError("snapshot-bound analysis artifacts require control identity")
            if self.source_registry_version is None or self.episode_universe_digest is None:
                raise ValueError(
                    "snapshot-bound analysis artifacts require registry and universe binding"
                )
        elif self.control_snapshot_id is not None or self.control_receipt_id is not None:
            raise ValueError("TRAJECTORY artifacts must not carry control snapshot identity")
        forbid_truth_keys(self.payload)

    @property
    def analysis_id(self) -> str:
        return EXPERIMENTAL_ANALYSIS_ID_PREFIX + sha256_hex(
            canonical_json_bytes(self.to_canonical())
        )

    @property
    def analysis_digest(self) -> Digest:
        return sha256_digest(canonical_json_bytes(self.to_canonical()))

    def to_canonical(self) -> dict[str, CanonicalValue]:
        return {
            "algorithm_version": self.algorithm_version,
            "as_of": canonical_timestamp(self.as_of),
            "authority_state": self.authority_state,
            "configuration_digest": str(self.configuration_digest),
            "control_receipt_id": self.control_receipt_id,
            "control_snapshot_id": self.control_snapshot_id,
            "episode_universe_digest": (
                None if self.episode_universe_digest is None else str(self.episode_universe_digest)
            ),
            "generated_at": canonical_timestamp(self.generated_at),
            "interpretation": self.interpretation,
            "kind": self.kind.value,
            "payload": self.payload,
            "schema_version": self.schema_version,
            "source_registry_version": (
                None if self.source_registry_version is None else str(self.source_registry_version)
            ),
            "status": self.status.value,
        }


def _seconds(delta: timedelta) -> int:
    """Whole seconds of a non-negative timedelta (integer, never float)."""
    if delta < timedelta(0):
        raise ValueError("experimental analysis time delta cannot be negative")
    return delta.days * 86400 + delta.seconds


def _require_control_compatibility(
    control_snapshot: BaselineSnapshot, control_receipt: ProjectionReceipt, *, as_of: datetime
) -> None:
    if control_receipt.status is not ProjectionStatus.COMPLETE:
        raise ValueError("experimental analysis requires a COMPLETE control snapshot")
    if control_snapshot.as_of != as_of:
        raise ValueError("control snapshot as_of must match experimental analysis as_of")


def _eligible_by_episode(
    observations: Iterable[BaselineObservationInput],
    *,
    control_snapshot: BaselineSnapshot,
    as_of: datetime,
) -> dict[str, tuple[BaselineObservationInput, ...]]:
    """Prospective-eligible episode members at ``as_of`` (R1, R3)."""
    eligible = sorted(
        (item for item in observations if item.observed_at <= as_of),
        key=lambda item: item.observation_id,
    )
    by_id = {item.observation_id: item for item in eligible}
    if len(by_id) != len(eligible):
        raise ValueError("duplicate observation_id in experimental analysis inputs")
    members_by_episode: dict[str, tuple[BaselineObservationInput, ...]] = {}
    for episode in control_snapshot.episodes:
        members: list[BaselineObservationInput] = []
        for observation_id in episode.observation_ids:
            item = by_id.get(observation_id)
            if item is None:
                raise ValueError("control snapshot episode references unknown observation")
            members.append(item)
        members_by_episode[episode.episode_id] = tuple(
            sorted(members, key=lambda item: (item.observed_at, item.observation_id))
        )
    return members_by_episode


def _windowed_members(
    members: tuple[BaselineObservationInput, ...], *, as_of: datetime
) -> tuple[BaselineObservationInput, ...]:
    window_start = as_of - timedelta(seconds=ANALYSIS_OBSERVATION_WINDOW_SECONDS)
    return tuple(
        item
        for item in members
        if item.is_prospective and window_start <= item.observed_at <= as_of
    )


def _artifact_identity(item: BaselineObservationInput) -> str | None:
    name = item.grouping.artifact_name
    version = item.grouping.artifact_version
    if name is None or version is None:
        return None
    return f"{name}@{version}"


# --- GROUPING_HYPOTHESES ----------------------------------------------------


def build_grouping_hypotheses_payload(
    observations: Iterable[BaselineObservationInput],
    *,
    control_snapshot: BaselineSnapshot,
    as_of: datetime,
) -> dict[str, CanonicalValue]:
    """Deterministic candidate merge/split hypotheses (never authoritative)."""
    members_by_episode = _eligible_by_episode(
        observations, control_snapshot=control_snapshot, as_of=as_of
    )
    episode_ids = sorted(members_by_episode)
    merge_hypotheses: list[CanonicalValue] = []
    for left_id, right_id in combinations(episode_ids, 2):
        left_members = members_by_episode[left_id]
        right_members = members_by_episode[right_id]
        left_urls = {
            item.grouping.canonical_url for item in left_members if item.grouping.canonical_url
        }
        right_urls = {
            item.grouping.canonical_url for item in right_members if item.grouping.canonical_url
        }
        shared_urls = sorted(left_urls & right_urls)
        left_sources = {item.grouping.source_id for item in left_members}
        right_sources = {item.grouping.source_id for item in right_members}
        shared_sources = sorted(left_sources & right_sources)
        left_identities = {
            identity for item in left_members if (identity := _artifact_identity(item)) is not None
        }
        right_identities = {
            identity for item in right_members if (identity := _artifact_identity(item)) is not None
        }
        shared_identities = sorted(left_identities & right_identities)
        reasons: list[str] = []
        if shared_urls:
            reasons.append("shared-canonical-url")
        if shared_identities:
            reasons.append("shared-artifact-identity")
        if not reasons:
            continue
        shared_url_values: list[CanonicalValue] = [url for url in shared_urls]
        shared_source_values: list[CanonicalValue] = [source for source in shared_sources]
        shared_identity_values: list[CanonicalValue] = [identity for identity in shared_identities]
        reason_values: list[CanonicalValue] = [reason for reason in sorted(reasons)]
        entry: dict[str, CanonicalValue] = {
            "episode_a_id": left_id,
            "episode_b_id": right_id,
            "hypothesis_status": ExperimentalAnalysisStatus.HYPOTHESIS.value,
            "reasons": reason_values,
            "shared_artifact_identities": shared_identity_values,
            "shared_canonical_urls": shared_url_values,
            "shared_source_ids": shared_source_values,
        }
        merge_hypotheses.append(entry)
    split_hypotheses: list[CanonicalValue] = []
    for episode_id in episode_ids:
        versions_by_name: dict[str, set[str]] = {}
        for item in members_by_episode[episode_id]:
            if item.grouping.kind == "ARTIFACT" and item.grouping.artifact_name is not None:
                version = item.grouping.artifact_version if item.grouping.artifact_version else ""
                versions_by_name.setdefault(item.grouping.artifact_name, set()).add(version)
        mixed_names = sorted(
            name for name, versions in versions_by_name.items() if len(versions) > 1
        )
        if not mixed_names:
            continue
        implicated = tuple(
            sorted(
                item.observation_id
                for item in members_by_episode[episode_id]
                if item.grouping.kind == "ARTIFACT" and item.grouping.artifact_name in mixed_names
            )
        )
        mixed_values: list[CanonicalValue] = [name for name in mixed_names]
        implicated_values: list[CanonicalValue] = [observation_id for observation_id in implicated]
        split_reasons: list[CanonicalValue] = ["mixed-artifact-versions"]
        split_entry: dict[str, CanonicalValue] = {
            "episode_id": episode_id,
            "hypothesis_status": ExperimentalAnalysisStatus.HYPOTHESIS.value,
            "mixed_artifact_names": mixed_values,
            "observation_ids": implicated_values,
            "reasons": split_reasons,
        }
        split_hypotheses.append(split_entry)
    return {
        "merge_hypotheses": merge_hypotheses,
        "split_hypotheses": split_hypotheses,
        "baseline_relationship": _GROUPING_BASELINE_RELATIONSHIP,
    }


# --- ENTITY_PROVENANCE ------------------------------------------------------


def _min_pair_distance_seconds(
    left: tuple[BaselineObservationInput, ...],
    right: tuple[BaselineObservationInput, ...],
) -> int:
    return min(
        _seconds(abs(left_item.observed_at - right_item.observed_at))
        for left_item in left
        for right_item in right
    )


def build_entity_provenance_payload(
    observations: Iterable[BaselineObservationInput],
    *,
    control_snapshot: BaselineSnapshot,
    as_of: datetime,
) -> dict[str, CanonicalValue]:
    """Candidate entity links and provenance hypotheses (HYPOTHESIS only)."""
    members_by_episode = _eligible_by_episode(
        observations, control_snapshot=control_snapshot, as_of=as_of
    )
    episode_ids = sorted(members_by_episode)
    entity_links: list[CanonicalValue] = []
    for left_id, right_id in combinations(episode_ids, 2):
        left_members = members_by_episode[left_id]
        right_members = members_by_episode[right_id]
        left_urls = {
            item.grouping.canonical_url for item in left_members if item.grouping.canonical_url
        }
        right_urls = {
            item.grouping.canonical_url for item in right_members if item.grouping.canonical_url
        }
        shared_urls = sorted(left_urls & right_urls)
        left_sources = {item.grouping.source_id for item in left_members}
        right_sources = {item.grouping.source_id for item in right_members}
        shared_sources = sorted(left_sources & right_sources)
        left_identities = {
            identity for item in left_members if (identity := _artifact_identity(item)) is not None
        }
        right_identities = {
            identity for item in right_members if (identity := _artifact_identity(item)) is not None
        }
        shared_identities = sorted(left_identities & right_identities)
        evidence_kinds: list[str] = []
        if shared_urls:
            evidence_kinds.append("shared-canonical-url")
        if shared_identities:
            evidence_kinds.append("shared-artifact-identity")
        if shared_sources:
            evidence_kinds.append("shared-source")
        if not evidence_kinds:
            continue
        distance: int | None = None
        if shared_urls:
            distance = _min_pair_distance_seconds(left_members, right_members)
            if distance > ENTITY_LINK_WINDOW_SECONDS:
                evidence_kinds = [kind for kind in evidence_kinds if kind != "shared-canonical-url"]
                if not evidence_kinds:
                    continue
        evidence_values: list[CanonicalValue] = [kind for kind in sorted(evidence_kinds)]
        shared_url_values: list[CanonicalValue] = [url for url in shared_urls]
        shared_source_values: list[CanonicalValue] = [source for source in shared_sources]
        shared_identity_values: list[CanonicalValue] = [identity for identity in shared_identities]
        link_entry: dict[str, CanonicalValue] = {
            "evidence_kinds": evidence_values,
            "episode_a_id": left_id,
            "episode_b_id": right_id,
            "hypothesis_status": ExperimentalAnalysisStatus.HYPOTHESIS.value,
            "min_observation_distance_seconds": distance,
            "same_entity_interpretation": _SAME_ENTITY_INTERPRETATION,
            "shared_artifact_identities": shared_identity_values,
            "shared_canonical_urls": shared_url_values,
            "shared_source_ids": shared_source_values,
        }
        entity_links.append(link_entry)
    provenance_hypotheses: list[CanonicalValue] = []
    for episode_id in episode_ids:
        members = members_by_episode[episode_id]
        if not members:
            continue
        earliest = members[0]
        primaries = [
            item for item in members if PRIMARY_EMISSION_ROLE in item.grouping.signal_roles
        ]
        earliest_primary_source = (
            min(
                primaries,
                key=lambda item: (item.observed_at, item.observation_id),
            ).grouping.source_id
            if primaries
            else None
        )
        provenance_entry: dict[str, CanonicalValue] = {
            "earliest_observed_at": canonical_timestamp(earliest.observed_at),
            "earliest_observed_source_id": earliest.grouping.source_id,
            "earliest_primary_emission_source_id": earliest_primary_source,
            "episode_id": episode_id,
            "hypothesis_status": ExperimentalAnalysisStatus.HYPOTHESIS.value,
            "origin_interpretation": _ORIGIN_INTERPRETATION,
        }
        provenance_hypotheses.append(provenance_entry)
    return {
        "entity_links": entity_links,
        "provenance_hypotheses": provenance_hypotheses,
    }


# --- CORROBORATION ----------------------------------------------------------


def build_corroboration_payload(
    observations: Iterable[BaselineObservationInput],
    *,
    control_snapshot: BaselineSnapshot,
    as_of: datetime,
) -> dict[str, CanonicalValue]:
    """Cross-source corroboration descriptors (never confirmation counts)."""
    members_by_episode = _eligible_by_episode(
        observations, control_snapshot=control_snapshot, as_of=as_of
    )
    descriptors: list[CanonicalValue] = []
    for episode_id in sorted(members_by_episode):
        windowed = _windowed_members(members_by_episode[episode_id], as_of=as_of)
        sources = sorted({item.grouping.source_id for item in windowed})
        roles = sorted({role for item in windowed for role in item.grouping.signal_roles})
        time_spread: int | None = None
        if len(windowed) >= 2:
            time_spread = _seconds(windowed[-1].observed_at - windowed[0].observed_at)
        source_values: list[CanonicalValue] = [source for source in sources]
        role_values: list[CanonicalValue] = [role for role in roles]
        descriptor_entry: dict[str, CanonicalValue] = {
            "distinct_lane_roles": role_values,
            "distinct_source_count": len(sources),
            "episode_id": episode_id,
            "lane_diversity": len(roles),
            "observation_count": len(windowed),
            "source_ids": source_values,
            "status": ExperimentalAnalysisStatus.DESCRIPTOR.value,
            "time_spread_seconds": time_spread,
        }
        descriptors.append(descriptor_entry)
    return {
        "descriptors": descriptors,
        "semantics": _CORROBORATION_SEMANTICS,
    }


# --- PROPAGATION_GRAPH ------------------------------------------------------


def _node_id(item: BaselineObservationInput) -> str:
    lane = min(item.grouping.signal_roles) if item.grouping.signal_roles else "NONE"
    return f"{item.grouping.source_id}#{lane}"


def build_propagation_graph_payload(
    observations: Iterable[BaselineObservationInput],
    *,
    control_snapshot: BaselineSnapshot,
    as_of: datetime,
) -> dict[str, CanonicalValue]:
    """Deterministic directed source/lane adjacency graph within the window."""
    members_by_episode = _eligible_by_episode(
        observations, control_snapshot=control_snapshot, as_of=as_of
    )
    node_ids: set[str] = set()
    edge_counts: dict[tuple[str, str], int] = {}
    edge_episodes: dict[tuple[str, str], set[str]] = {}
    for episode_id in sorted(members_by_episode):
        windowed = _windowed_members(members_by_episode[episode_id], as_of=as_of)
        if not windowed:
            continue
        sequence = [_node_id(item) for item in windowed]
        node_ids.update(sequence)
        for from_node, to_node in pairwise(sequence):
            key = (from_node, to_node)
            edge_counts[key] = edge_counts.get(key, 0) + 1
            edge_episodes.setdefault(key, set()).add(episode_id)
    nodes: list[CanonicalValue] = []
    for node_id in sorted(node_ids):
        source_id, _, lane = node_id.rpartition("#")
        node_entry: dict[str, CanonicalValue] = {
            "lane": lane,
            "node_id": node_id,
            "source_id": source_id,
        }
        nodes.append(node_entry)
    edges: list[CanonicalValue] = []
    for from_node, to_node in sorted(edge_counts):
        episode_values: list[CanonicalValue] = [
            episode_id for episode_id in sorted(edge_episodes[(from_node, to_node)])
        ]
        edge_entry: dict[str, CanonicalValue] = {
            "count": edge_counts[(from_node, to_node)],
            "episode_ids": episode_values,
            "from_node_id": from_node,
            "to_node_id": to_node,
        }
        edges.append(edge_entry)
    return {
        "bounded_by": (
            "prospective-eligible member observations within "
            f"[as_of-{PROPAGATION_GRAPH_WINDOW_SECONDS}s, as_of] of the control "
            "episode universe"
        ),
        "edges": edges,
        "nodes": nodes,
        "sequence_semantics": _PROPAGATION_SEMANTICS,
        "window_seconds": PROPAGATION_GRAPH_WINDOW_SECONDS,
    }


# --- INDICATORS -------------------------------------------------------------


_burst_definition = (
    "count of windowed prospective-eligible member observations in "
    "[as_of-3600s, as_of] minus floor(windowed count * 3600 / 86400): "
    "hourly burst excess; interpretable indicator only, never a "
    "manipulation verdict"
)
_same_source_definition = (
    "count of consecutive windowed prospective-eligible member observation "
    "pairs (ordered by observed_at then observation_id) sharing the same "
    "source_id: possible self-echo pattern; interpretable indicator only, "
    "never a manipulation verdict"
)
_timing_definition = (
    "length of the longest run of consecutive identical observed_at gaps "
    "among windowed prospective-eligible member observations: possible "
    "coordinated timing regularity; interpretable indicator only, never a "
    "manipulation verdict; UNKNOWN when fewer than 3 windowed observations"
)

_INDICATOR_DEFINITIONS: dict[str, str] = {
    "burst_rate_excess": _burst_definition,
    "same_source_adjacency": _same_source_definition,
    "identical_timing_gap_run": _timing_definition,
}

_INDICATOR_UNITS: dict[str, str] = {
    "burst_rate_excess": "excess_observations_last_hour_vs_window_mean",
    "same_source_adjacency": "same_source_adjacent_pairs",
    "identical_timing_gap_run": "longest_equal_gap_run",
}


def _indicator(
    name: str,
    value: int | None,
    *,
    window_seconds: int | None,
) -> FeatureValue:
    return FeatureValue(
        name=name,
        value=value,
        unit=_INDICATOR_UNITS[name],
        definition=_INDICATOR_DEFINITIONS[name],
        window_seconds=window_seconds,
        status=FeatureStatus.OBSERVED if value is not None else FeatureStatus.UNKNOWN,
    )


def _burst_rate_excess(
    windowed: tuple[BaselineObservationInput, ...], *, as_of: datetime
) -> FeatureValue:
    if not windowed:
        return _indicator(
            "burst_rate_excess", None, window_seconds=ANALYSIS_OBSERVATION_WINDOW_SECONDS
        )
    last_hour = sum(
        1
        for item in windowed
        if _seconds(as_of - item.observed_at) < INDICATOR_BURST_WINDOW_SECONDS
    )
    expected = len(windowed) * INDICATOR_BURST_WINDOW_SECONDS // ANALYSIS_OBSERVATION_WINDOW_SECONDS
    return _indicator(
        "burst_rate_excess",
        last_hour - expected,
        window_seconds=ANALYSIS_OBSERVATION_WINDOW_SECONDS,
    )


def _same_source_adjacency(windowed: tuple[BaselineObservationInput, ...]) -> FeatureValue:
    if not windowed:
        return _indicator(
            "same_source_adjacency", None, window_seconds=ANALYSIS_OBSERVATION_WINDOW_SECONDS
        )
    count = sum(
        1
        for earlier, later in pairwise(windowed)
        if earlier.grouping.source_id == later.grouping.source_id
    )
    return _indicator(
        "same_source_adjacency", count, window_seconds=ANALYSIS_OBSERVATION_WINDOW_SECONDS
    )


def _identical_timing_gap_run(windowed: tuple[BaselineObservationInput, ...]) -> FeatureValue:
    if len(windowed) < 3:
        return _indicator(
            "identical_timing_gap_run", None, window_seconds=ANALYSIS_OBSERVATION_WINDOW_SECONDS
        )
    gaps = [
        _seconds(later.observed_at - earlier.observed_at) for earlier, later in pairwise(windowed)
    ]
    best = 1
    current = 1
    for earlier_gap, later_gap in pairwise(gaps):
        if earlier_gap == later_gap:
            current += 1
        else:
            current = 1
        best = max(best, current)
    return _indicator(
        "identical_timing_gap_run",
        best if best >= 2 else 0,
        window_seconds=ANALYSIS_OBSERVATION_WINDOW_SECONDS,
    )


def build_indicators_payload(
    observations: Iterable[BaselineObservationInput],
    *,
    control_snapshot: BaselineSnapshot,
    as_of: datetime,
) -> dict[str, CanonicalValue]:
    """Interpretable manipulation/reflexivity indicators (no verdicts)."""
    members_by_episode = _eligible_by_episode(
        observations, control_snapshot=control_snapshot, as_of=as_of
    )
    episodes: list[CanonicalValue] = []
    for episode_id in sorted(members_by_episode):
        windowed = _windowed_members(members_by_episode[episode_id], as_of=as_of)
        indicators = (
            _burst_rate_excess(windowed, as_of=as_of),
            _same_source_adjacency(windowed),
            _identical_timing_gap_run(windowed),
        )
        names = tuple(indicator.name for indicator in indicators)
        if names != _INDICATOR_ORDER:  # pragma: no cover - defensive
            raise ValueError("indicator order drifted from configuration")
        indicator_values: list[CanonicalValue] = [
            indicator.to_canonical() for indicator in indicators
        ]
        episode_entry: dict[str, CanonicalValue] = {
            "episode_id": episode_id,
            "indicator_status": ExperimentalAnalysisStatus.INDICATORS.value,
            "indicators": indicator_values,
        }
        episodes.append(episode_entry)
    order_values: list[CanonicalValue] = [order for order in _INDICATOR_ORDER]
    return {
        "episodes": episodes,
        "indicator_order": order_values,
        "verdict_policy": "INDICATORS_ONLY_NEVER_A_MANIPULATION_VERDICT",
    }


# --- TRAJECTORY -------------------------------------------------------------


def build_trajectory_payload(frames: tuple[TrajectoryFrame, ...]) -> dict[str, CanonicalValue]:
    """Per-episode trajectory projection over stored EXPERIMENTAL_SHADOW frames."""
    if not frames:
        raise ValueError("trajectory projection requires at least one stored frame")
    as_ofs = [frame.feature_batch.as_of for frame in frames]
    if any(later <= earlier for earlier, later in pairwise(as_ofs)):
        raise ValueError("trajectory frames must be strictly ordered by as_of")
    frame_values: list[CanonicalValue] = []
    ranks_by_frame: list[dict[str, int]] = []
    values_by_episode: dict[str, dict[str, dict[str, CanonicalValue]]] = {}
    for frame in frames:
        batch = frame.feature_batch
        pef = frame.pef_artifact
        if pef is not None and pef.as_of != batch.as_of:
            raise ValueError("trajectory pef artifact as_of must match its frame batch")
        ranks = (
            {episode.episode_id: episode.rank for episode in pef.episodes}
            if pef is not None
            else {}
        )
        ranks_by_frame.append(ranks)
        frame_entry: dict[str, CanonicalValue] = {
            "as_of": canonical_timestamp(batch.as_of),
            "episode_universe_digest": str(batch.episode_universe_digest),
            "feature_batch_digest": str(batch.batch_digest),
            "feature_batch_id": batch.batch_id,
            "pef_artifact_id": None if pef is None else pef.artifact_id,
            "pef_output_digest": None if pef is None else str(pef.output_digest),
        }
        frame_values.append(frame_entry)
        for vector in batch.vectors:
            values: dict[str, CanonicalValue] = {
                feature.name: feature.value for feature in vector.features
            }
            values_by_episode.setdefault(vector.episode_id, {})[
                canonical_timestamp(batch.as_of)
            ] = values
    trajectories: list[CanonicalValue] = []
    for episode_id in sorted(values_by_episode):
        points: list[CanonicalValue] = []
        for index, frame in enumerate(frames):
            timestamp = canonical_timestamp(frame.feature_batch.as_of)
            stored = values_by_episode[episode_id].get(timestamp)
            if stored is None:
                continue
            point_entry: dict[str, CanonicalValue] = {
                "as_of": timestamp,
                "candidate_rank": ranks_by_frame[index].get(episode_id),
                "values": stored,
            }
            points.append(point_entry)
        trajectory_entry: dict[str, CanonicalValue] = {
            "episode_id": episode_id,
            "points": points,
        }
        trajectories.append(trajectory_entry)
    return {
        "frames": frame_values,
        "projection_status": ExperimentalAnalysisStatus.PROJECTION.value,
        "trajectories": trajectories,
    }


# --- artifact builders ------------------------------------------------------


def _snapshot_bound_artifact(
    kind: ExperimentalAnalysisKind,
    *,
    payload: dict[str, CanonicalValue],
    control_snapshot: BaselineSnapshot,
    control_receipt: ProjectionReceipt,
    generated_at: datetime,
    source_registry_version: Digest,
) -> ExperimentalAnalysisArtifact:
    _require_control_compatibility(control_snapshot, control_receipt, as_of=control_snapshot.as_of)
    return ExperimentalAnalysisArtifact(
        kind=kind,
        as_of=control_snapshot.as_of,
        generated_at=generated_at,
        status=_KIND_STATUS[kind],
        payload=payload,
        control_snapshot_id=control_snapshot.snapshot_id,
        control_receipt_id=control_receipt.receipt_id,
        source_registry_version=source_registry_version,
        episode_universe_digest=shadow_universe_digest(control_snapshot),
    )


def build_grouping_hypotheses_artifact(
    observations: Iterable[BaselineObservationInput],
    *,
    control_snapshot: BaselineSnapshot,
    control_receipt: ProjectionReceipt,
    generated_at: datetime,
    source_registry_version: Digest,
) -> ExperimentalAnalysisArtifact:
    _require_control_compatibility(control_snapshot, control_receipt, as_of=control_snapshot.as_of)
    payload = build_grouping_hypotheses_payload(
        observations, control_snapshot=control_snapshot, as_of=control_snapshot.as_of
    )
    return _snapshot_bound_artifact(
        ExperimentalAnalysisKind.GROUPING_HYPOTHESES,
        payload=payload,
        control_snapshot=control_snapshot,
        control_receipt=control_receipt,
        generated_at=generated_at,
        source_registry_version=source_registry_version,
    )


def build_entity_provenance_artifact(
    observations: Iterable[BaselineObservationInput],
    *,
    control_snapshot: BaselineSnapshot,
    control_receipt: ProjectionReceipt,
    generated_at: datetime,
    source_registry_version: Digest,
) -> ExperimentalAnalysisArtifact:
    _require_control_compatibility(control_snapshot, control_receipt, as_of=control_snapshot.as_of)
    payload = build_entity_provenance_payload(
        observations, control_snapshot=control_snapshot, as_of=control_snapshot.as_of
    )
    return _snapshot_bound_artifact(
        ExperimentalAnalysisKind.ENTITY_PROVENANCE,
        payload=payload,
        control_snapshot=control_snapshot,
        control_receipt=control_receipt,
        generated_at=generated_at,
        source_registry_version=source_registry_version,
    )


def build_corroboration_artifact(
    observations: Iterable[BaselineObservationInput],
    *,
    control_snapshot: BaselineSnapshot,
    control_receipt: ProjectionReceipt,
    generated_at: datetime,
    source_registry_version: Digest,
) -> ExperimentalAnalysisArtifact:
    _require_control_compatibility(control_snapshot, control_receipt, as_of=control_snapshot.as_of)
    payload = build_corroboration_payload(
        observations, control_snapshot=control_snapshot, as_of=control_snapshot.as_of
    )
    return _snapshot_bound_artifact(
        ExperimentalAnalysisKind.CORROBORATION,
        payload=payload,
        control_snapshot=control_snapshot,
        control_receipt=control_receipt,
        generated_at=generated_at,
        source_registry_version=source_registry_version,
    )


def build_propagation_graph_artifact(
    observations: Iterable[BaselineObservationInput],
    *,
    control_snapshot: BaselineSnapshot,
    control_receipt: ProjectionReceipt,
    generated_at: datetime,
    source_registry_version: Digest,
) -> ExperimentalAnalysisArtifact:
    _require_control_compatibility(control_snapshot, control_receipt, as_of=control_snapshot.as_of)
    payload = build_propagation_graph_payload(
        observations, control_snapshot=control_snapshot, as_of=control_snapshot.as_of
    )
    return _snapshot_bound_artifact(
        ExperimentalAnalysisKind.PROPAGATION_GRAPH,
        payload=payload,
        control_snapshot=control_snapshot,
        control_receipt=control_receipt,
        generated_at=generated_at,
        source_registry_version=source_registry_version,
    )


def build_indicators_artifact(
    observations: Iterable[BaselineObservationInput],
    *,
    control_snapshot: BaselineSnapshot,
    control_receipt: ProjectionReceipt,
    generated_at: datetime,
    source_registry_version: Digest,
) -> ExperimentalAnalysisArtifact:
    _require_control_compatibility(control_snapshot, control_receipt, as_of=control_snapshot.as_of)
    payload = build_indicators_payload(
        observations, control_snapshot=control_snapshot, as_of=control_snapshot.as_of
    )
    return _snapshot_bound_artifact(
        ExperimentalAnalysisKind.INDICATORS,
        payload=payload,
        control_snapshot=control_snapshot,
        control_receipt=control_receipt,
        generated_at=generated_at,
        source_registry_version=source_registry_version,
    )


def build_trajectory_artifact(
    frames: Iterable[TrajectoryFrame],
    *,
    generated_at: datetime,
    source_registry_version: Digest,
) -> ExperimentalAnalysisArtifact:
    """Read-only trajectory projection over stored EXPERIMENTAL_SHADOW frames."""
    frame_tuple = tuple(frames)
    payload = build_trajectory_payload(frame_tuple)
    return ExperimentalAnalysisArtifact(
        kind=ExperimentalAnalysisKind.TRAJECTORY,
        as_of=frame_tuple[-1].feature_batch.as_of,
        generated_at=generated_at,
        status=ExperimentalAnalysisStatus.PROJECTION,
        payload=payload,
        source_registry_version=source_registry_version,
    )


def experimental_analysis_input_digest(
    observations: Iterable[BaselineObservationInput],
    *,
    control_snapshot: BaselineSnapshot,
) -> Digest:
    """Digest the exact evidence inputs bound into a snapshot-bound artifact (R8)."""
    return pef_input_digest(observations, control_snapshot=control_snapshot)


def trajectory_input_digest(frames: Iterable[TrajectoryFrame]) -> Digest:
    """Digest the exact stored-frame digests a trajectory projection binds (R8)."""
    frame_values: list[CanonicalValue] = []
    for frame in frames:
        frame_values.append(
            {
                "feature_batch_digest": str(frame.feature_batch.batch_digest),
                "pef_output_digest": (
                    None if frame.pef_artifact is None else str(frame.pef_artifact.output_digest)
                ),
            }
        )
    material: dict[str, CanonicalValue] = {"frames": frame_values}
    return sha256_digest(canonical_json_bytes(material))
