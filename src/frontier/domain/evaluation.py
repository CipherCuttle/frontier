"""Preregistered PEF_V0 evaluation machinery (slice D).

Implements EXACTLY the evaluation section of
``experiments/advanced_intelligence/pef_v0/preregistration.json``:

- model-independent outcome labels (``FOLLOW_ON_ATTENTION_OR_DISCOVERY_WITHIN_24H``)
  derived from evidence alone, never from either arm's outputs (R7);
- coverage-safe unresolved outcomes (``UNRESOLVED_COVERAGE``): excluded from the
  ``resolved_label_fraction`` numerator AND denominator, never coerced to 0/1 (R4);
- opportunity anchors with deduplication and the frozen V0 domain taxonomy;
- top-K paired comparison with per-arm precision over surfaced resolved
  opportunities;
- Newcombe hybrid score interval (method 10) for the candidate-minus-control
  difference with the preregistered z and the -0.10 non-inferiority margin;
- lead-time advantage medians (domain and pooled, misses retained as
  ``resolution_at``, both-miss ties are zero);
- sample adequacy gating (min resolved/positive/surfaced counts, resolved label
  fraction in bps, minimum two qualifying domains);
- an immutable, digest-bound evaluation receipt (R8) whose status never lets a
  FAILED/INSUFFICIENT/DRIFTED outcome masquerade as COMPLETE/CONFIRMATORY.

All numeric statistics use :class:`decimal.Decimal` (canonical JSON forbids
binary floats) with a fixed arithmetic context so the evaluation is
deterministic and replayable (ADR-0010).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from enum import StrEnum

from .advanced_intelligence import (
    PEF_ALGORITHM_VERSION,
    PEF_AUTHORITY_STATE,
    PEF_CANDIDATE_ID,
    PEF_CONFIGURATION_DIGEST,
    PEF_EXPERIMENT_ID,
    PEF_PRIMARY_EMISSION_ROLE,
    canonical_freeze_components,
)
from .candidate_freeze import FreezeStatus
from .canonical_json import (
    CanonicalValue,
    canonical_decimal,
    canonical_json_bytes,
    canonical_timestamp,
)
from .digests import Digest, sha256_digest, sha256_hex
from .health import HealthValue

EVALUATION_SCHEMA_VERSION = "evaluation-receipt-v0"
EVALUATION_ID_PREFIX = "evaluation_"
EVALUATION_ALGORITHM_VERSION = "pef-v0-evaluation-newcombe-v0"
EVALUATION_AUTHORITY_STATE = "EXPERIMENTAL_EVALUATION"

# Fixed evaluation configuration mirrored from the preregistration's frozen
# "evaluation" section. This structure is digest-bound into every receipt, so
# any post-hoc threshold change would break replayability (R8).
EVALUATION_CONFIGURATION: dict[str, CanonicalValue] = {
    "global_rank_cutoff_k": 100,
    "snapshot_cadence_seconds": 300,
    "label_maturation_seconds_after_window": 86400,
    "noninferiority_margin": "0.10",
    "newcombe_z": "1.959963984540054",
    "outcome_label": {
        "name": "FOLLOW_ON_ATTENTION_OR_DISCOVERY_WITHIN_24H",
        "model_independent": True,
        "candidate_or_control_outputs_may_define_label": False,
        "unresolved_coverage": (
            "UNRESOLVED_COVERAGE is excluded from resolved_label_fraction "
            "numerator AND denominator; absence never coerces to negative"
        ),
    },
    "lead_time": {
        "value_seconds": "control_detection_time - candidate_detection_time",
        "population": (
            "all positive resolved retained opportunities, including arm "
            "misses assigned resolution_at; both-miss ties are zero"
        ),
        "domain_floor": "median lead_time_advantage_seconds > 0",
        "pooled_floor": "pooled median lead_time_advantage_seconds > 0",
    },
    "sample_adequacy": {
        "min_resolved_opportunities_per_domain": 30,
        "min_positive_opportunities_per_domain": 10,
        "min_surfaced_resolved_opportunities_per_arm_per_domain": 20,
        "min_resolved_label_fraction_bps_per_domain": 9000,
        "resolved_label_fraction_denominator": (
            "all retained non-duplicate non-UNQUALIFIED_MIXED opportunities in the domain"
        ),
        "resolved_label_fraction_numerator": (
            "retained opportunities resolved POSITIVE or NEGATIVE; "
            "UNRESOLVED_COVERAGE is not resolved"
        ),
        "minimum_qualifying_domains": 2,
        "fewer_than_two_adequately_sampled_domains": "INSUFFICIENT_SAMPLE",
    },
    "verdict_semantics": (
        "EXPERIMENTAL_COMPARISON_NOT_TRUTH: rank/precision/lead-time are "
        "experimental promotion-gate statistics, never truth or confidence"
    ),
}

EVALUATION_CONFIGURATION_DIGEST = sha256_digest(canonical_json_bytes(EVALUATION_CONFIGURATION))

GLOBAL_RANK_CUTOFF_K = 100
NONINFERIORITY_MARGIN = Decimal("0.10")
NEWCOMBE_Z = Decimal("1.959963984540054")
LABEL_MATURATION_SECONDS = 86400
SNAPSHOT_CADENCE_SECONDS = 300

MIN_RESOLVED_OPPORTUNITIES_PER_DOMAIN = 30
MIN_POSITIVE_OPPORTUNITIES_PER_DOMAIN = 10
MIN_SURFACED_RESOLVED_PER_ARM_PER_DOMAIN = 20
MIN_RESOLVED_LABEL_FRACTION_BPS_PER_DOMAIN = 9000
MINIMUM_QUALIFYING_DOMAINS = 2

DOMAIN_SOFTWARE_PACKAGES = "SOFTWARE_PACKAGES"
DOMAIN_AI_MODELS = "AI_MODELS"
DOMAIN_SECURITY_VULNERABILITIES = "SECURITY_VULNERABILITIES"
DOMAIN_UNQUALIFIED_MIXED = "UNQUALIFIED_MIXED"
DOMAIN_UNQUALIFIED = "UNQUALIFIED"

QUALIFYING_DOMAINS: tuple[str, ...] = (
    DOMAIN_SOFTWARE_PACKAGES,
    DOMAIN_AI_MODELS,
    DOMAIN_SECURITY_VULNERABILITIES,
)
ANCHOR_SOURCE_BY_DOMAIN: dict[str, str] = {
    DOMAIN_SOFTWARE_PACKAGES: "pypi.updates",
    DOMAIN_AI_MODELS: "hf.models",
    DOMAIN_SECURITY_VULNERABILITIES: "cisa.kev",
}
_DOMAIN_BY_ANCHOR_SOURCE = {source: domain for domain, source in ANCHOR_SOURCE_BY_DOMAIN.items()}

ATTENTION_SOURCE_ID = "hn.frontpage"
ATTENTION_ROLE = "ATTENTION"
DISCOVERY_SOURCE_ID = "gdelt.frontier"
DISCOVERY_ROLE = "DISCOVERY"
OUTCOME_LANE_SOURCE_IDS = (ATTENTION_SOURCE_ID, DISCOVERY_SOURCE_ID)

# Fixed decimal context: identical inputs always produce identical outputs.
_DECIMAL_CONTEXT_PRECISION = 34
_DECIMAL_QUANT = Decimal("0.000000000001")


def _quantize(value: Decimal) -> Decimal:
    with localcontext() as ctx:
        ctx.prec = _DECIMAL_CONTEXT_PRECISION
        ctx.rounding = ROUND_HALF_EVEN
        return value.quantize(_DECIMAL_QUANT)


def classify_anchor_domain(primary_emission_source_ids: Iterable[str]) -> str:
    """Frozen V0 domain taxonomy for an opportunity's qualifying anchors.

    ``hn.frontpage``/``gdelt.frontier`` never assign a domain. More than one
    qualifying stratum in the same resolution grouping episode is
    ``UNQUALIFIED_MIXED``; none is ``UNQUALIFIED``.
    """
    anchor_sources = _DOMAIN_BY_ANCHOR_SOURCE
    qualifying = {source for source in primary_emission_source_ids if source in anchor_sources}
    if len(qualifying) > 1:
        return DOMAIN_UNQUALIFIED_MIXED
    if not qualifying:
        return DOMAIN_UNQUALIFIED
    (source,) = tuple(qualifying)
    return _DOMAIN_BY_ANCHOR_SOURCE[source]


@dataclass(frozen=True, slots=True)
class AnchorObservation:
    """A prospectively eligible canonical observation (label input only).

    Model-independent: these are evidence facts, never an arm output (R7).
    """

    observation_id: str
    source_id: str
    role: str
    observed_at: datetime

    def __post_init__(self) -> None:
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("anchor observation observed_at must be timezone-aware")
        if not self.observation_id:
            raise ValueError("anchor observation requires an observation_id")
        if not self.source_id or not self.role:
            raise ValueError("anchor observation requires source_id and role")

    def to_canonical(self) -> dict[str, CanonicalValue]:
        return {
            "observation_id": self.observation_id,
            "observed_at": canonical_timestamp(self.observed_at),
            "role": self.role,
            "source_id": self.source_id,
        }


@dataclass(frozen=True, slots=True)
class LaneBoundary:
    """Outcome-lane health at one expected paired boundary (R4).

    Only an all-OK boundary counts as coverage; DEGRADED/UNKNOWN/FAILED or a
    missing boundary is a coverage gap and blocks a NEGATIVE resolution.
    """

    source_id: str
    as_of: datetime
    transport_state: HealthValue
    freshness_state: HealthValue
    completeness_state: HealthValue
    schema_state: HealthValue

    def __post_init__(self) -> None:
        if self.as_of.tzinfo is None or self.as_of.utcoffset() is None:
            raise ValueError("lane boundary as_of must be timezone-aware")

    @property
    def ok(self) -> bool:
        return (
            self.transport_state is HealthValue.OK
            and self.freshness_state is HealthValue.OK
            and self.completeness_state is HealthValue.OK
            and self.schema_state is HealthValue.OK
        )

    def to_canonical(self) -> dict[str, CanonicalValue]:
        return {
            "as_of": canonical_timestamp(self.as_of),
            "completeness_state": self.completeness_state.value,
            "freshness_state": self.freshness_state.value,
            "schema_state": self.schema_state.value,
            "source_id": self.source_id,
            "transport_state": self.transport_state.value,
        }


@dataclass(frozen=True, slots=True)
class OpportunityGroup:
    """One resolution grouping episode's opportunity material at resolution time.

    ``primary_emission_anchors`` lists the qualifying V0 PRIMARY_EMISSION
    candidate anchors in the resolution grouping episode (from frozen anchor
    sources). ``member_observations`` carries every prospectively eligible
    member observation available to the model-independent label. Deduplication
    retains only the earliest qualifying anchor (observed_at then
    observation_id); each retained anchor counts once.
    """

    resolution_episode_id: str
    primary_emission_anchors: tuple[AnchorObservation, ...]
    member_observations: tuple[AnchorObservation, ...]
    lane_boundaries: tuple[LaneBoundary, ...] = ()

    def __post_init__(self) -> None:
        if not self.resolution_episode_id:
            raise ValueError("opportunity group requires a resolution episode id")
        seen_anchors: set[str] = set()
        for item in self.primary_emission_anchors:
            if item.observation_id in seen_anchors:
                raise ValueError("duplicate observation_id among primary emission anchors")
            seen_anchors.add(item.observation_id)
        seen_members: set[str] = set()
        for item in self.member_observations:
            if item.observation_id in seen_members:
                raise ValueError("duplicate observation_id among group member observations")
            seen_members.add(item.observation_id)


class OutcomeLabel(StrEnum):
    """Model-independent, coverage-safe outcome labels (R4, R7).

    UNRESOLVED_COVERAGE is an explicit epistemic state: it is excluded from the
    resolved_label_fraction numerator AND denominator and is never coerced into
    a positive or a negative outcome.
    """

    POSITIVE = "POSITIVE"
    NEGATIVE = "NEGATIVE"
    UNRESOLVED_COVERAGE = "UNRESOLVED_COVERAGE"


@dataclass(frozen=True, slots=True)
class RetainedOpportunity:
    """One deduplicated, domain-classified, labelled opportunity anchor."""

    anchor: AnchorObservation
    domain: str
    resolution_episode_id: str
    resolution_at: datetime
    label: OutcomeLabel

    def __post_init__(self) -> None:
        if self.domain not in (*QUALIFYING_DOMAINS, DOMAIN_UNQUALIFIED_MIXED, DOMAIN_UNQUALIFIED):
            raise ValueError("unknown V0 evaluation domain")
        if self.resolution_at != resolution_at_for(self.anchor):
            raise ValueError("resolution_at must be anchor.observed_at + label maturation")

    def to_canonical(self) -> dict[str, CanonicalValue]:
        return {
            "anchor": self.anchor.to_canonical(),
            "domain": self.domain,
            "label": self.label.value,
            "resolution_at": canonical_timestamp(self.resolution_at),
            "resolution_episode_id": self.resolution_episode_id,
        }


def resolution_at_for(anchor: AnchorObservation) -> datetime:
    return anchor.observed_at + timedelta(seconds=LABEL_MATURATION_SECONDS)


def expected_lane_boundaries(anchor_observed_at: datetime) -> tuple[datetime, ...]:
    """Expected paired boundaries from the first boundary strictly after
    ``anchor.observed_at`` through ``resolution_at`` (inclusive), aligned to
    UTC epoch multiples of the snapshot cadence."""
    anchor_epoch = int(anchor_observed_at.timestamp())
    resolution_epoch = int(
        (anchor_observed_at + timedelta(seconds=LABEL_MATURATION_SECONDS)).timestamp()
    )
    start = (anchor_epoch // SNAPSHOT_CADENCE_SECONDS + 1) * SNAPSHOT_CADENCE_SECONDS
    return tuple(
        datetime.fromtimestamp(epoch, tz=UTC)
        for epoch in range(start, resolution_epoch + 1, SNAPSHOT_CADENCE_SECONDS)
    )


def resolve_outcome_label(
    primary_emission_anchor: AnchorObservation,
    *,
    member_observations: Sequence[AnchorObservation],
    lane_boundaries: Sequence[LaneBoundary],
) -> OutcomeLabel:
    """Automated deterministic label; no arm output may define it.

    POSITIVE iff the resolution grouping episode contains a prospectively
    eligible observation with ``anchor.observed_at < observed_at <= resolution_at``
    from ``hn.frontpage`` with ATTENTION role or ``gdelt.frontier`` with
    DISCOVERY role. A positive stays positive under degraded coverage.

    NEGATIVE requires the absence AND both outcome lanes all-OK at every
    expected paired boundary; any non-OK or missing boundary leaves the
    opportunity explicitly UNRESOLVED_COVERAGE (absence is not evidence of
    absence under degraded coverage, R4).
    """
    resolution_at = resolution_at_for(primary_emission_anchor)
    positive = False
    for item in member_observations:
        if not (primary_emission_anchor.observed_at < item.observed_at <= resolution_at):
            continue
        if item.source_id == ATTENTION_SOURCE_ID and item.role == ATTENTION_ROLE:
            positive = True
            break
        if item.source_id == DISCOVERY_SOURCE_ID and item.role == DISCOVERY_ROLE:
            positive = True
            break
    if positive:
        return OutcomeLabel.POSITIVE
    required = {
        (source, boundary)
        for source in OUTCOME_LANE_SOURCE_IDS
        for boundary in expected_lane_boundaries(primary_emission_anchor.observed_at)
    }
    covered: dict[tuple[str, datetime], bool] = {}
    for boundary in lane_boundaries:
        key = (boundary.source_id, boundary.as_of)
        if key in required:
            covered[key] = covered.get(key, False) or boundary.ok
    if any(not covered.get(key, False) for key in required):
        return OutcomeLabel.UNRESOLVED_COVERAGE
    return OutcomeLabel.NEGATIVE


def build_retained_opportunities(
    groups: Sequence[OpportunityGroup],
) -> tuple[RetainedOpportunity, ...]:
    """Deduplicate anchors and derive model-independent labels per group.

    At ``resolution_at`` an anchor is retained only when it is the earliest
    qualifying V0 primary-emission observation in its resolution grouping
    episode (ordered by ``observed_at`` then ``observation_id``); each retained
    anchor counts once. Groups whose qualifying anchors span more than one
    frozen stratum are UNQUALIFIED_MIXED; groups with no qualifying anchor are
    UNQUALIFIED and dropped (they cannot manufacture the domain count).
    """
    retained: list[RetainedOpportunity] = []
    for group in groups:
        qualifying = tuple(
            anchor
            for anchor in group.primary_emission_anchors
            if anchor.role == PEF_PRIMARY_EMISSION_ROLE
            and anchor.source_id in _DOMAIN_BY_ANCHOR_SOURCE
        )
        if not qualifying:
            continue
        domain = classify_anchor_domain(anchor.source_id for anchor in qualifying)
        anchor = min(qualifying, key=lambda item: (item.observed_at, item.observation_id))
        label = resolve_outcome_label(
            anchor,
            member_observations=group.member_observations,
            lane_boundaries=group.lane_boundaries,
        )
        retained.append(
            RetainedOpportunity(
                anchor=anchor,
                domain=domain,
                resolution_episode_id=group.resolution_episode_id,
                resolution_at=resolution_at_for(anchor),
                label=label,
            )
        )
    return tuple(sorted(retained, key=lambda item: (item.domain, item.anchor.observation_id)))


@dataclass(frozen=True, slots=True)
class AnchorTracking:
    """One paired snapshot's anchor tracking entry (both arms, same as_of).

    ``episode_id`` is the current grouping episode containing the stable anchor
    observation at that snapshot (episode ids may evolve). Ranks are the arms'
    global ranks at that snapshot; ``None`` means the arm did not rank the
    episode in that snapshot's payload.
    """

    as_of: datetime
    episode_id: str | None
    control_rank: int | None
    candidate_rank: int | None

    def __post_init__(self) -> None:
        if self.as_of.tzinfo is None or self.as_of.utcoffset() is None:
            raise ValueError("anchor tracking as_of must be timezone-aware")
        if self.episode_id is None and (
            self.control_rank is not None or self.candidate_rank is not None
        ):
            raise ValueError("anchor tracking ranks require an episode id")


@dataclass(frozen=True, slots=True)
class AnchorDetection:
    """Per-arm detection times for one opportunity (misses kept, R8)."""

    control_detection_time: datetime
    candidate_detection_time: datetime
    control_surfaced: bool
    candidate_surfaced: bool


def detect_anchor(
    opportunity: RetainedOpportunity,
    tracking: Sequence[AnchorTracking],
    *,
    rank_cutoff_k: int = GLOBAL_RANK_CUTOFF_K,
) -> AnchorDetection:
    """Earliest paired boundary at or before resolution_at where the anchor's
    current episode enters each arm's global top-K.

    ``never_detected_time`` is ``resolution_at``; a miss is retained as exactly
    that value (no dropped misses). Boundaries strictly before the anchor's
    ``observed_at`` cannot detect it and are ignored.
    """
    if rank_cutoff_k < 1:
        raise ValueError("rank cutoff K must be a positive integer")
    entries = sorted(
        (
            item
            for item in tracking
            if opportunity.anchor.observed_at <= item.as_of <= opportunity.resolution_at
        ),
        key=lambda item: item.as_of,
    )
    if len({item.as_of for item in entries}) != len(entries):
        raise ValueError("anchor tracking contains duplicate snapshot boundaries")

    control_detection_time = opportunity.resolution_at
    candidate_detection_time = opportunity.resolution_at
    control_surfaced = False
    candidate_surfaced = False
    for item in entries:
        if (
            not control_surfaced
            and item.control_rank is not None
            and item.control_rank <= rank_cutoff_k
        ):
            control_detection_time = item.as_of
            control_surfaced = True
        if (
            not candidate_surfaced
            and item.candidate_rank is not None
            and item.candidate_rank <= rank_cutoff_k
        ):
            candidate_detection_time = item.as_of
            candidate_surfaced = True
    return AnchorDetection(
        control_detection_time=control_detection_time,
        candidate_detection_time=candidate_detection_time,
        control_surfaced=control_surfaced,
        candidate_surfaced=candidate_surfaced,
    )


def lead_time_advantage_seconds(detection: AnchorDetection) -> int:
    """``control_detection_time - candidate_detection_time`` in whole seconds.

    Positive means the candidate surfaced earlier. A both-arm miss is zero and
    is never dropped.
    """
    delta = detection.control_detection_time - detection.candidate_detection_time
    return delta.days * 86400 + delta.seconds


def wilson_score_bounds(
    successes: int, n: int, z: Decimal = NEWCOMBE_Z
) -> tuple[Decimal, Decimal] | None:
    """Wilson score interval bounds for one binomial proportion.

    Closed form (pure stdlib math, deterministic Decimal arithmetic):

        center = (p + z^2/(2n)) / (1 + z^2/n)
        half   = z / (1 + z^2/n) * sqrt(p(1-p)/n + z^2/(4n^2))
        L = center - half, U = center + half   (clamped to [0, 1])

    Returns ``None`` when the sample is empty (n <= 0): an empty arm has no
    defined proportion and must fail sample adequacy instead of yielding 0 or 1.
    """
    if n <= 0:
        return None
    p = Decimal(successes) / Decimal(n)
    z2 = z * z
    denominator = Decimal(1) + z2 / Decimal(n)
    center = (p + z2 / (Decimal(2) * Decimal(n))) / denominator
    variance = p * (Decimal(1) - p) / Decimal(n) + z2 / (Decimal(4) * Decimal(n) * Decimal(n))
    half = (z / denominator) * _sqrt(variance)
    lower = center - half
    upper = center + half
    zero = Decimal(0)
    one = Decimal(1)
    return (_quantize(max(zero, lower)), _quantize(min(one, upper)))


def _sqrt(value: Decimal) -> Decimal:
    with localcontext() as ctx:
        ctx.prec = _DECIMAL_CONTEXT_PRECISION
        ctx.rounding = ROUND_HALF_EVEN
        if value < 0:
            raise ValueError("square root of negative decimal")
        return value.sqrt()


def newcombe_difference_bounds(
    successes_1: int,
    n_1: int,
    successes_2: int,
    n_2: int,
    z: Decimal = NEWCOMBE_Z,
) -> tuple[Decimal, Decimal] | None:
    """Newcombe hybrid score interval (method 10) for ``p1 - p2``.

    Two-sided score interval built from each arm's Wilson interval with the
    shared preregistered z:

        D = p1 - p2
        L = D - sqrt((p1 - L1)^2 + (U2 - p2)^2)
        U = D + sqrt((U1 - p1)^2 + (p2 - L2)^2)

    where (L1, U1) and (L2, U2) are the Wilson bounds of arm 1 and arm 2. The
    non-inferiority gate uses the lower bound against ``-margin``. Returns
    ``None`` when either arm is empty (n <= 0); empty arms fail sample
    adequacy and never produce a fabricated interval.
    """
    bounds_1 = wilson_score_bounds(successes_1, n_1, z)
    bounds_2 = wilson_score_bounds(successes_2, n_2, z)
    if bounds_1 is None or bounds_2 is None:
        return None
    lower_1, upper_1 = bounds_1
    lower_2, upper_2 = bounds_2
    p1 = Decimal(successes_1) / Decimal(n_1)
    p2 = Decimal(successes_2) / Decimal(n_2)
    difference = p1 - p2
    lower = difference - _sqrt((p1 - lower_1) ** 2 + (upper_2 - p2) ** 2)
    upper = difference + _sqrt((upper_1 - p1) ** 2 + (p2 - lower_2) ** 2)
    return (_quantize(lower), _quantize(upper))


def median(values: Sequence[int]) -> Decimal:
    """Deterministic median of integers (even counts average the middle two)."""
    if not values:
        raise ValueError("median of empty population")
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return Decimal(ordered[middle])
    return (Decimal(ordered[middle - 1]) + Decimal(ordered[middle])) / Decimal(2)


@dataclass(frozen=True, slots=True)
class ArmPrecision:
    """Precision@K surface for one arm over resolved opportunities."""

    surfaced_resolved: int
    positive_surfaced_resolved: int

    @property
    def precision(self) -> Decimal | None:
        if self.surfaced_resolved <= 0:
            return None
        return _quantize(Decimal(self.positive_surfaced_resolved) / Decimal(self.surfaced_resolved))

    def to_canonical(self) -> dict[str, CanonicalValue]:
        precision = self.precision
        return {
            "positive_surfaced_resolved": self.positive_surfaced_resolved,
            "precision": None if precision is None else canonical_decimal(precision),
            "surfaced_resolved": self.surfaced_resolved,
        }


@dataclass(frozen=True, slots=True)
class DomainEvaluation:
    """Per-domain evaluation table entry (preregistered fields verbatim)."""

    domain: str
    resolved_label_fraction_denominator: int
    resolved_label_fraction_numerator: int
    unresolved_coverage_count: int
    positive_count: int
    negative_count: int
    candidate_arm: ArmPrecision
    control_arm: ArmPrecision
    difference_lower_bound: Decimal | None
    median_lead_time_advantage_seconds: Decimal | None
    qualifies_sample_adequacy: bool

    @property
    def resolved_label_fraction_bps(self) -> int | None:
        denominator = self.resolved_label_fraction_denominator
        if denominator <= 0:
            return None
        return (self.resolved_label_fraction_numerator * 10000) // denominator

    @property
    def point_floor_pass(self) -> bool | None:
        """``candidate_precision >= control_precision``; None when undefined."""
        candidate = self.candidate_arm.precision
        control = self.control_arm.precision
        if candidate is None or control is None:
            return None
        return candidate >= control

    @property
    def noninferiority_pass(self) -> bool | None:
        lower = self.difference_lower_bound
        if lower is None:
            return None
        return lower >= -NONINFERIORITY_MARGIN

    @property
    def lead_time_pass(self) -> bool | None:
        median_lead = self.median_lead_time_advantage_seconds
        if median_lead is None:
            return None
        return median_lead > 0

    @property
    def promotion_eligible(self) -> bool:
        return (
            self.qualifies_sample_adequacy
            and self.point_floor_pass is True
            and self.noninferiority_pass is True
            and self.lead_time_pass is True
        )

    def to_canonical(self) -> dict[str, CanonicalValue]:
        return {
            "candidate_arm": self.candidate_arm.to_canonical(),
            "control_arm": self.control_arm.to_canonical(),
            "difference_lower_bound": (
                None
                if self.difference_lower_bound is None
                else canonical_decimal(self.difference_lower_bound)
            ),
            "domain": self.domain,
            "lead_time_median_advantage_seconds": (
                None
                if self.median_lead_time_advantage_seconds is None
                else canonical_decimal(self.median_lead_time_advantage_seconds)
            ),
            "negative_count": self.negative_count,
            "point_floor_pass": self.point_floor_pass,
            "noninferiority_pass": self.noninferiority_pass,
            "lead_time_pass": self.lead_time_pass,
            "positive_count": self.positive_count,
            "promotion_eligible": self.promotion_eligible,
            "qualifies_sample_adequacy": self.qualifies_sample_adequacy,
            "resolved_label_fraction_bps": self.resolved_label_fraction_bps,
            "resolved_label_fraction_denominator": self.resolved_label_fraction_denominator,
            "resolved_label_fraction_numerator": self.resolved_label_fraction_numerator,
            "unresolved_coverage_count": self.unresolved_coverage_count,
        }


def evaluate_domains(
    opportunities: Sequence[RetainedOpportunity],
    tracking_by_anchor: Mapping[str, Sequence[AnchorTracking]],
    *,
    rank_cutoff_k: int = GLOBAL_RANK_CUTOFF_K,
) -> tuple[DomainEvaluation, ...]:
    """Stratify resolved opportunities by the frozen V0 taxonomy and evaluate
    every preregistered domain gate. UNQUALIFIED/UNQUALIFIED_MIXED anchors are
    retained and reported only in receipt counts, never as domain rows.
    """
    domains = sorted({item.domain for item in opportunities})
    evaluations: list[DomainEvaluation] = []
    for domain in domains:
        in_domain = [item for item in opportunities if item.domain == domain]
        denominator = len(in_domain)
        resolved = [
            item for item in in_domain if item.label is not OutcomeLabel.UNRESOLVED_COVERAGE
        ]
        unresolved_coverage_count = denominator - len(resolved)
        positives = [item for item in resolved if item.label is OutcomeLabel.POSITIVE]
        negatives = [item for item in resolved if item.label is OutcomeLabel.NEGATIVE]

        candidate_positive = 0
        control_positive = 0
        candidate_surfaced = 0
        control_surfaced = 0
        lead_times: list[int] = []
        for item in resolved:
            tracking = tracking_by_anchor.get(item.anchor.observation_id, ())
            detection = detect_anchor(item, tracking, rank_cutoff_k=rank_cutoff_k)
            if detection.candidate_surfaced:
                candidate_surfaced += 1
                if item.label is OutcomeLabel.POSITIVE:
                    candidate_positive += 1
            if detection.control_surfaced:
                control_surfaced += 1
                if item.label is OutcomeLabel.POSITIVE:
                    control_positive += 1
            if item.label is OutcomeLabel.POSITIVE:
                lead_times.append(lead_time_advantage_seconds(detection))

        candidate_arm = ArmPrecision(
            surfaced_resolved=candidate_surfaced,
            positive_surfaced_resolved=candidate_positive,
        )
        control_arm = ArmPrecision(
            surfaced_resolved=control_surfaced,
            positive_surfaced_resolved=control_positive,
        )
        bounds = newcombe_difference_bounds(
            candidate_positive,
            candidate_surfaced,
            control_positive,
            control_surfaced,
        )
        median_lead = median(lead_times) if lead_times else None
        qualifies = sample_adequacy_pass(
            DomainEvaluation(
                domain=domain,
                resolved_label_fraction_denominator=denominator,
                resolved_label_fraction_numerator=len(resolved),
                unresolved_coverage_count=unresolved_coverage_count,
                positive_count=len(positives),
                negative_count=len(negatives),
                candidate_arm=candidate_arm,
                control_arm=control_arm,
                difference_lower_bound=None if bounds is None else bounds[0],
                median_lead_time_advantage_seconds=median_lead,
                qualifies_sample_adequacy=False,
            )
        )
        evaluations.append(
            DomainEvaluation(
                domain=domain,
                resolved_label_fraction_denominator=denominator,
                resolved_label_fraction_numerator=len(resolved),
                unresolved_coverage_count=unresolved_coverage_count,
                positive_count=len(positives),
                negative_count=len(negatives),
                candidate_arm=candidate_arm,
                control_arm=control_arm,
                difference_lower_bound=None if bounds is None else bounds[0],
                median_lead_time_advantage_seconds=median_lead,
                qualifies_sample_adequacy=qualifies,
            )
        )
    return tuple(evaluations)


def sample_adequacy_pass(evaluation: DomainEvaluation) -> bool:
    """Preregistered per-domain sample-adequacy gate.

    Requires min resolved opportunities (30), min positives (10), min surfaced
    resolved opportunities per arm (20), and a resolved label fraction of at
    least 9000 bps, where the denominator is every retained non-duplicate
    non-UNQUALIFIED_MIXED opportunity in the domain and the numerator counts
    only POSITIVE or NEGATIVE resolutions (UNRESOLVED_COVERAGE never resolves).
    """
    fraction_bps = evaluation.resolved_label_fraction_bps
    return (
        evaluation.resolved_label_fraction_denominator >= MIN_RESOLVED_OPPORTUNITIES_PER_DOMAIN
        and evaluation.positive_count >= MIN_POSITIVE_OPPORTUNITIES_PER_DOMAIN
        and evaluation.candidate_arm.surfaced_resolved >= MIN_SURFACED_RESOLVED_PER_ARM_PER_DOMAIN
        and evaluation.control_arm.surfaced_resolved >= MIN_SURFACED_RESOLVED_PER_ARM_PER_DOMAIN
        and fraction_bps is not None
        and fraction_bps >= MIN_RESOLVED_LABEL_FRACTION_BPS_PER_DOMAIN
    )


class EvaluationStatus(StrEnum):
    """Evaluation receipt lifecycle status (R7, R8).

    COMPLETE means the preregistered evaluation ran to a verdict over at least
    the minimum qualifying domains. INSUFFICIENT_SAMPLE is an explicit
    epistemic state (not a failed hypothesis). INVALID_DRIFT means the bound
    freeze receipt is DRIFTED, which invalidates confirmatory status. FAILED
    means the evaluation could not be computed. Non-COMPLETE statuses never
    carry a verdict payload that could masquerade as confirmatory evidence.
    """

    COMPLETE = "COMPLETE"
    INSUFFICIENT_SAMPLE = "INSUFFICIENT_SAMPLE"
    FAILED = "FAILED"
    INVALID_DRIFT = "INVALID_DRIFT"


@dataclass(frozen=True, slots=True)
class ShadowRunBinding:
    run_id: str
    run_digest: Digest

    def to_canonical(self) -> dict[str, CanonicalValue]:
        return {"run_digest": str(self.run_digest), "run_id": self.run_id}


@dataclass(frozen=True, slots=True)
class EvaluationCounts:
    """Retained-anchor accounting shared by every status (R8)."""

    opportunity_groups: int
    anchors_retained: int
    unqualified_mixed_count: int
    unqualified_count: int
    resolved_positive: int
    resolved_negative: int
    unresolved_coverage: int

    def to_canonical(self) -> dict[str, CanonicalValue]:
        return {
            "anchors_retained": self.anchors_retained,
            "opportunity_groups": self.opportunity_groups,
            "resolved_negative": self.resolved_negative,
            "resolved_positive": self.resolved_positive,
            "unqualified_count": self.unqualified_count,
            "unqualified_mixed_count": self.unqualified_mixed_count,
            "unresolved_coverage": self.unresolved_coverage,
        }


@dataclass(frozen=True, slots=True)
class EvaluationReceipt:
    """Immutable, digest-bound evaluation receipt for a PEF_V0 shadow window.

    Binds the paired shadow runs (ids + digests), the candidate freeze receipt
    (id + digest), the preregistration digests, the evaluation algorithm
    version, ``as_of``, counts, per-domain gates, pooled lead-time median, and
    status. ``confirmatory_evidence`` can be true only when the status is
    COMPLETE, the freeze receipt is FROZEN, and every adequately sampled
    domain passed every preregistered gate; a DRIFTED freeze yields
    INVALID_DRIFT and never confirmatory evidence.
    """

    as_of: datetime
    generated_at: datetime
    status: EvaluationStatus
    counts: EvaluationCounts
    shadow_runs: tuple[ShadowRunBinding, ...]
    candidate_freeze_receipt_id: str
    freeze_receipt_digest: Digest
    preregistration_digest: Digest
    freeze_status: FreezeStatus
    domains: tuple[DomainEvaluation, ...] = ()
    pooled_median_lead_time_advantage_seconds: Decimal | None = None
    verdict: str | None = None
    status_reason: str | None = None
    schema_version: str = EVALUATION_SCHEMA_VERSION
    experiment_id: str = PEF_EXPERIMENT_ID
    candidate_id: str = PEF_CANDIDATE_ID
    algorithm_version: str = PEF_ALGORITHM_VERSION
    candidate_configuration_digest: Digest = PEF_CONFIGURATION_DIGEST
    evaluation_algorithm_version: str = EVALUATION_ALGORITHM_VERSION
    evaluation_configuration_digest: Digest = EVALUATION_CONFIGURATION_DIGEST
    authority_state: str = EVALUATION_AUTHORITY_STATE
    candidate_authority_state: str = PEF_AUTHORITY_STATE

    def __post_init__(self) -> None:
        if self.as_of.tzinfo is None or self.as_of.utcoffset() is None:
            raise ValueError("evaluation receipt as_of must be timezone-aware")
        if self.generated_at.tzinfo is None or self.generated_at.utcoffset() is None:
            raise ValueError("evaluation receipt generated_at must be timezone-aware")
        if not self.shadow_runs:
            raise ValueError("evaluation receipt must bind at least one shadow run")
        if self.status is EvaluationStatus.COMPLETE:
            if self.verdict is None:
                raise ValueError("COMPLETE evaluation receipt requires an explicit verdict")
            if self.status_reason is not None:
                raise ValueError("COMPLETE evaluation receipt cannot carry a status reason")
        else:
            if not self.status_reason:
                raise ValueError(f"{self.status.value} evaluation receipt requires a status reason")
        frozen_required = self.status is EvaluationStatus.COMPLETE
        if frozen_required and self.freeze_status is not FreezeStatus.FROZEN:
            raise ValueError("COMPLETE evaluation receipt requires a FROZEN freeze receipt")
        if not frozen_required and self.verdict is not None:
            raise ValueError("only COMPLETE evaluation receipts may carry a verdict")
        if self.candidate_authority_state != PEF_AUTHORITY_STATE:
            raise ValueError("evaluation receipt candidate authority state mismatch")

    @property
    def confirmatory_evidence(self) -> bool:
        return self.status is EvaluationStatus.COMPLETE and self.verdict == "SUPPORTED"

    @property
    def qualifying_domain_count(self) -> int:
        return sum(1 for domain in self.domains if domain.qualifies_sample_adequacy)

    @property
    def evaluation_id(self) -> str:
        return EVALUATION_ID_PREFIX + sha256_hex(canonical_json_bytes(self.to_canonical()))

    @property
    def receipt_digest(self) -> Digest:
        return sha256_digest(canonical_json_bytes(self.to_canonical()))

    def to_canonical(self) -> dict[str, CanonicalValue]:
        domain_values: list[CanonicalValue] = [domain.to_canonical() for domain in self.domains]
        run_values: list[CanonicalValue] = [run.to_canonical() for run in self.shadow_runs]
        pooled_domain_medians: list[CanonicalValue] = [
            {
                "domain": domain.domain,
                "median_lead_time_advantage_seconds": (
                    None
                    if domain.median_lead_time_advantage_seconds is None
                    else canonical_decimal(domain.median_lead_time_advantage_seconds)
                ),
            }
            for domain in self.domains
            if domain.qualifies_sample_adequacy
        ]
        return {
            "as_of": canonical_timestamp(self.as_of),
            "authority_state": self.authority_state,
            "candidate_authority_state": self.candidate_authority_state,
            "candidate_configuration_digest": str(self.candidate_configuration_digest),
            "candidate_freeze_receipt_id": self.candidate_freeze_receipt_id,
            "candidate_id": self.candidate_id,
            "counts": self.counts.to_canonical(),
            "domains": domain_values,
            "evaluation_algorithm_version": self.evaluation_algorithm_version,
            "evaluation_configuration_digest": str(self.evaluation_configuration_digest),
            "experiment_id": self.experiment_id,
            "freeze_receipt_digest": str(self.freeze_receipt_digest),
            "freeze_status": self.freeze_status.value,
            "generated_at": canonical_timestamp(self.generated_at),
            "pooled_median_lead_time_advantage_seconds": (
                None
                if self.pooled_median_lead_time_advantage_seconds is None
                else canonical_decimal(self.pooled_median_lead_time_advantage_seconds)
            ),
            "preregistration_digest": str(self.preregistration_digest),
            "qualifying_domain_count": self.qualifying_domain_count,
            "qualifying_domains_lead_time_medians": pooled_domain_medians,
            "schema_version": self.schema_version,
            "shadow_runs": run_values,
            "status": self.status.value,
            "status_reason": self.status_reason,
            "verdict": self.verdict,
        }


def pooled_lead_time_median(
    domain_evaluations: Sequence[DomainEvaluation],
    tracking_by_anchor: Mapping[str, Sequence[AnchorTracking]],
    opportunities: Sequence[RetainedOpportunity],
    *,
    rank_cutoff_k: int = GLOBAL_RANK_CUTOFF_K,
) -> Decimal | None:
    """Pooled median lead-time advantage over adequately sampled domains.

    Population: all positive resolved retained opportunities in each adequately
    sampled domain, including arm misses assigned ``resolution_at`` (ties zero,
    no dropped misses). Returns ``None`` when no adequately sampled domain
    exists.
    """
    adequate_domains = {
        domain.domain for domain in domain_evaluations if domain.qualifies_sample_adequacy
    }
    lead_times: list[int] = []
    for item in opportunities:
        if item.domain not in adequate_domains:
            continue
        if item.label is not OutcomeLabel.POSITIVE:
            continue
        tracking = tracking_by_anchor.get(item.anchor.observation_id, ())
        detection = detect_anchor(item, tracking, rank_cutoff_k=rank_cutoff_k)
        lead_times.append(lead_time_advantage_seconds(detection))
    if not lead_times:
        return None
    return _quantize(median(lead_times))


def build_evaluation_receipt(
    *,
    as_of: datetime,
    generated_at: datetime,
    shadow_runs: Sequence[ShadowRunBinding],
    candidate_freeze_receipt_id: str,
    freeze_receipt_digest: Digest,
    preregistration_digest: Digest,
    freeze_status: FreezeStatus,
    opportunities: Sequence[RetainedOpportunity],
    tracking_by_anchor: Mapping[str, Sequence[AnchorTracking]],
    domain_evaluations: Sequence[DomainEvaluation],
    pooled_median: Decimal | None,
    status: EvaluationStatus,
    status_reason: str | None = None,
    verdict: str | None = None,
) -> EvaluationReceipt:
    """Assemble the immutable receipt; verdict semantics stay experimental.

    SUPPORTED requires at least ``MINIMUM_QUALIFYING_DOMAINS`` adequately
    sampled domains, every adequately sampled domain promotion-eligible, and a
    strictly positive pooled lead-time median. Fewer than two adequately
    sampled domains cannot yield SUPPORTED (preregistration sample-adequacy
    rule).
    """
    counts = EvaluationCounts(
        opportunity_groups=len(opportunities),
        anchors_retained=len(opportunities),
        unqualified_mixed_count=sum(
            1 for item in opportunities if item.domain == DOMAIN_UNQUALIFIED_MIXED
        ),
        unqualified_count=sum(1 for item in opportunities if item.domain == DOMAIN_UNQUALIFIED),
        resolved_positive=sum(1 for item in opportunities if item.label is OutcomeLabel.POSITIVE),
        resolved_negative=sum(1 for item in opportunities if item.label is OutcomeLabel.NEGATIVE),
        unresolved_coverage=sum(
            1 for item in opportunities if item.label is OutcomeLabel.UNRESOLVED_COVERAGE
        ),
    )
    freeze_id = canonical_freeze_components(candidate_freeze_receipt_id)
    if freeze_id is None:
        raise ValueError("evaluation receipt requires a candidate freeze receipt id")
    return EvaluationReceipt(
        as_of=as_of,
        generated_at=generated_at,
        status=status,
        status_reason=status_reason,
        counts=counts,
        shadow_runs=tuple(shadow_runs),
        candidate_freeze_receipt_id=freeze_id,
        freeze_receipt_digest=freeze_receipt_digest,
        preregistration_digest=preregistration_digest,
        freeze_status=freeze_status,
        domains=tuple(domain_evaluations),
        pooled_median_lead_time_advantage_seconds=pooled_median,
        verdict=verdict,
    )
