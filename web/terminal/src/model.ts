import type {
  EpisodeResponse,
  ExperimentalAvailabilityState,
  ExperimentalEpisodeComparisonResponse,
  ExperimentalFeatureBatchResponse,
  ExperimentalHistoryResponse,
  ExperimentalOverviewResponse,
  ExperimentalShadowRunResponse,
  ExperimentalStatusResponse,
  PublicViewKind,
} from "./api";
import { experimentalAvailability } from "./api";

export type PanelKind = "inspector" | "health" | "audit" | "help" | "experiment";

/**
 * Terminal lens selector. RADAR/NOW/TRENDING are the frozen public read-plane
 * baseline lenses (TERMINAL_V0). EXPERIMENTAL is a clearly-labelled
 * EXPERIMENTAL_SHADOW comparison lens: it never replaces or reranks the
 * baseline plane (slice H; snapshot safety).
 */
export type TerminalLens = PublicViewKind | "EXPERIMENTAL";
export const EXPERIMENTAL_LENS = "EXPERIMENTAL" as const;
export const EXPERIMENTAL_LENS_LABEL = "EXPERIMENTAL SHADOW";
export const EXPERIMENTAL_LENS_NOTE =
  "Identity, digests, and statuses only. Not baseline authority, not truth, " +
  "confidence, or independent confirmation. Every item is hypothesis-level " +
  "experimental output.";

export type KeyboardCommand =
  | { kind: "lens"; lens: TerminalLens }
  | { kind: "next" }
  | { kind: "previous" }
  | { kind: "inspect" }
  | { kind: "escape" }
  | { kind: "filter" }
  | { kind: "panel"; panel: Exclude<PanelKind, "inspector"> }
  | { kind: "refresh" };

export function filterEpisodes(items: readonly EpisodeResponse[], rawQuery: string): EpisodeResponse[] {
  const query = rawQuery.trim().toLocaleLowerCase();
  if (!query) return [...items];
  return items.filter((item) => {
    const searchable = [item.episode_id, ...item.source_ids, ...item.signal_roles]
      .join(" ")
      .toLocaleLowerCase();
    return searchable.includes(query);
  });
}

export function shortId(value: string, width = 10): string {
  if (value.length <= width + 2) return value;
  return `${value.slice(0, width)}…`;
}

export function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return (
    target.isContentEditable ||
    target.tagName === "INPUT" ||
    target.tagName === "TEXTAREA" ||
    target.tagName === "SELECT"
  );
}

export function resolveKeyboardCommand(
  key: string,
  target: EventTarget | null,
): KeyboardCommand | null {
  if (isEditableTarget(target)) return key === "Escape" ? { kind: "escape" } : null;
  if (key === "1") return { kind: "lens", lens: "RADAR" };
  if (key === "2") return { kind: "lens", lens: "NOW" };
  if (key === "3") return { kind: "lens", lens: "TRENDING" };
  if (key.toLocaleLowerCase() === "x") return { kind: "lens", lens: EXPERIMENTAL_LENS };
  if (key.toLocaleLowerCase() === "e") return { kind: "panel", panel: "experiment" };
  if (key === "j" || key === "ArrowDown") return { kind: "next" };
  if (key === "k" || key === "ArrowUp") return { kind: "previous" };
  if (key === "Enter") return { kind: "inspect" };
  if (key === "Escape") return { kind: "escape" };
  if (key === "/") return { kind: "filter" };
  if (key.toLocaleLowerCase() === "h") return { kind: "panel", panel: "health" };
  if (key.toLocaleLowerCase() === "a") return { kind: "panel", panel: "audit" };
  if (key === "?") return { kind: "panel", panel: "help" };
  if (key.toLocaleLowerCase() === "r") return { kind: "refresh" };
  return null;
}

export function assertSnapshotBinding(expected: string, actual: string, context: string): void {
  if (expected !== actual) {
    throw new Error(`${context} snapshot binding mismatch: expected ${expected}, got ${actual}`);
  }
}

export function displayUnavailable(value: string | null | undefined): string {
  if (value === null || value === undefined || value === "UNAVAILABLE") return "UNAVAILABLE";
  return value;
}

// ---------------------------------------------------------------------------
// EXPERIMENTAL lens model (slice H / WP8 experiment war room)
//
// Everything below renders EXPERIMENTAL_SHADOW read surfaces (R7): identity,
// digests, and statuses only. Missing data is an explicit UNKNOWN/NO_DATA/
// UNAVAILABLE/FAILED/DEGRADED/INSUFFICIENT_SAMPLE/INVALID_DRIFT state and is
// never fabricated into baseline-looking intelligence (R4).
// ---------------------------------------------------------------------------

/** Resolve one overview section's availability, fail-closed to UNKNOWN (R4). */
export function resolveSectionAvailability(
  availability: Record<string, string> | null | undefined,
  section: string,
): ExperimentalAvailabilityState {
  const value = availability?.[section];
  return value === undefined || value === null ? "UNKNOWN" : experimentalAvailability(value);
}

/**
 * Explicit experimental state matrix (WP8). Each state is rendered
 * distinctly and never coerced into another:
 *
 * - UNKNOWN            — fetch failed / not observed (epistemic gap)
 * - NO_DATA            — the table/section is empty for this horizon
 * - UNAVAILABLE        — capability absent from the read surface
 * - FAILED / DEGRADED /
 *   INSUFFICIENT_SAMPLE /
 *   INVALID_DRIFT      — preregistered evaluation statuses, rendered verbatim
 * - COMPLETE / AVAILABLE / OK — stored success states, rendered verbatim
 */
export type WarRoomStateKind =
  | "AVAILABLE"
  | "UNKNOWN"
  | "NO_DATA"
  | "UNAVAILABLE"
  | "FAILED"
  | "DEGRADED"
  | "INSUFFICIENT_SAMPLE"
  | "INVALID_DRIFT"
  | "COMPLETE"
  | "OK";

const WAR_ROOM_STATE_VOCABULARY: readonly WarRoomStateKind[] = [
  "AVAILABLE",
  "UNKNOWN",
  "NO_DATA",
  "UNAVAILABLE",
  "FAILED",
  "DEGRADED",
  "INSUFFICIENT_SAMPLE",
  "INVALID_DRIFT",
  "COMPLETE",
  "OK",
];

/**
 * Classify an experimental status/state string into the explicit war-room
 * state matrix, fail-closed to UNKNOWN. The raw status string is always
 * rendered verbatim alongside the classified state; this classifier only
 * decides which state-badge family a value belongs to (never coerces).
 */
export function experimentalStateKind(value: string | null | undefined): WarRoomStateKind {
  return WAR_ROOM_STATE_VOCABULARY.includes(value as WarRoomStateKind)
    ? (value as WarRoomStateKind)
    : "UNKNOWN";
}

export interface ExperimentalRankDelta {
  episodeId: string;
  baselineRank: number;
  /** Candidate rank for this episode, or null when unknown. */
  experimentalRank: number | null;
  /**
   * Verbatim candidate-rank state: UNKNOWN when the comparison fetch failed
   * or was never issued; otherwise the read plane's own state (e.g.
   * UNAVAILABLE when the candidate artifact has no rank for the episode).
   */
  experimentalRankState: string;
  /** Server-computed rank_delta; never recomputed client-side, null when absent. */
  delta: number | null;
  /** Verbatim delta state; UNAVAILABLE whenever the delta is not available. */
  deltaState: string;
}

/**
 * Baseline-vs-candidate rank deltas from candidate ranks only (EXPERIMENTAL
 * lens). ``candidateRanks`` must come from an EXPERIMENTAL_SHADOW surface.
 * Missing candidate ranks render delta UNAVAILABLE — never 0, never invented
 * (R4, R7). Baseline rows are never reordered or reranked by this data.
 */
export function computeRankDeltas(
  baselineItems: readonly EpisodeResponse[],
  candidateRanks: ReadonlyMap<string, number> | null,
): ExperimentalRankDelta[] {
  return baselineItems.map((item) => {
    const experimentalRank = candidateRanks?.get(item.episode_id) ?? null;
    const delta =
      experimentalRank === null ? null : experimentalRank - item.rank;
    return {
      episodeId: item.episode_id,
      baselineRank: item.rank,
      experimentalRank,
      experimentalRankState: experimentalRank === null ? "UNKNOWN" : "AVAILABLE",
      delta,
      deltaState: delta === null ? "UNAVAILABLE" : "AVAILABLE",
    };
  });
}

/**
 * Rank deltas from the WP7 per-episode comparison endpoint. The server's own
 * ``rank_delta`` / ``rank_delta_state`` are rendered verbatim; a missing
 * comparison (fetch failed or outside the bounded fetch window) renders the
 * candidate rank UNKNOWN and the delta UNAVAILABLE — never a coerced 0.
 * Baseline rank stays the baseline plane's own rank: candidate data never
 * reorders baseline rows.
 */
export function buildRankDeltasFromComparisons(
  baselineItems: readonly EpisodeResponse[],
  comparisons: ReadonlyMap<string, ExperimentalEpisodeComparisonResponse> | null,
): ExperimentalRankDelta[] {
  return baselineItems.map((item) => {
    const comparison = comparisons?.get(item.episode_id) ?? null;
    if (comparison === null) {
      return {
        episodeId: item.episode_id,
        baselineRank: item.rank,
        experimentalRank: null,
        experimentalRankState: "UNKNOWN",
        delta: null,
        deltaState: "UNAVAILABLE",
      };
    }
    const delta = comparison.rank_delta;
    return {
      episodeId: item.episode_id,
      baselineRank: item.rank,
      experimentalRank: comparison.candidate_rank,
      experimentalRankState:
        comparison.candidate_rank === null ? comparison.candidate_rank_state : "AVAILABLE",
      delta,
      deltaState: delta === null ? comparison.rank_delta_state : "AVAILABLE",
    };
  });
}

export function displayRankDelta(delta: number | null, state?: string | null): string {
  if (delta !== null) {
    if (delta === 0) return "±0";
    return `${delta > 0 ? "+" : ""}${delta}`;
  }
  if (state && state !== "AVAILABLE") return state;
  return "UNKNOWN";
}

/**
 * Experiment identity binding derived from the overview: the run / freeze /
 * evaluation identity EXPERIMENTAL fetches are guarded against (WP8 stale
 * guard). Never guessed: absent sections bind null.
 */
export interface ExperimentalIdentityBinding {
  runId: string | null;
  freezeReceiptId: string | null;
  evaluationReceiptId: string | null;
}

export function bindingFromOverview(
  overview: ExperimentalOverviewResponse | null,
): ExperimentalIdentityBinding {
  return {
    runId: overview?.latest_shadow_run?.run_id ?? null,
    freezeReceiptId: overview?.latest_shadow_run?.candidate_freeze_receipt_id ?? null,
    evaluationReceiptId: overview?.latest_evaluation_receipt?.evaluation_id ?? null,
  };
}

export interface ExperimentalHistoryEntry {
  section: string;
  availability: ExperimentalAvailabilityState;
  id: string | null;
  status: string | null;
  asOf: string | null;
}

function historyEntry(
  section: string,
  availability: ExperimentalAvailabilityState,
  id: string | null,
  status: string | null,
  asOf: string | null,
): ExperimentalHistoryEntry {
  return { section, availability, id, status, asOf };
}

/**
 * Experiment history for the EXPERIMENTAL lens: the latest stored shadow run,
 * PEF artifact, evaluation receipt, feature batch, and analysis artifacts,
 * each with its explicit availability state. NO_DATA entries are visible as
 * explicit empty states, never hidden (R4).
 */
export function buildExperimentHistory(
  overview: ExperimentalOverviewResponse | null,
): ExperimentalHistoryEntry[] {
  if (!overview) return [];
  const availability = overview.availability ?? {};
  const entries: ExperimentalHistoryEntry[] = [];
  const run = overview.latest_shadow_run;
  entries.push(
    historyEntry(
      "shadow_run",
      experimentalAvailability(availability.shadow_run),
      run?.run_id ?? null,
      run?.status ?? null,
      run?.as_of ?? null,
    ),
  );
  const pef = overview.latest_pef_artifact;
  entries.push(
    historyEntry(
      "pef_artifact",
      experimentalAvailability(availability.pef_artifact),
      pef?.artifact_id ?? null,
      pef?.status ?? null,
      pef?.as_of ?? null,
    ),
  );
  const receipt = overview.latest_evaluation_receipt;
  entries.push(
    historyEntry(
      "evaluation_receipt",
      experimentalAvailability(availability.evaluation_receipt),
      receipt?.evaluation_id ?? null,
      receipt?.status ?? null,
      receipt?.as_of ?? null,
    ),
  );
  const batch = overview.latest_feature_batch;
  entries.push(
    historyEntry(
      "feature_batch",
      experimentalAvailability(availability.feature_batch),
      batch?.batch_id ?? null,
      batch?.status ?? null,
      batch?.as_of ?? null,
    ),
  );
  for (const [kind, artifact] of Object.entries(overview.analysis_artifacts ?? {})) {
    entries.push(
      historyEntry(
        `analysis:${kind}`,
        experimentalAvailability(availability[`analysis:${kind}`]),
        artifact.analysis_id,
        artifact.status,
        artifact.as_of,
      ),
    );
  }
  return entries;
}

export interface WarRoomHistoryEntry {
  kind: "run" | "evaluation";
  id: string;
  status: string;
  asOf: string;
  runClass: string | null;
}

/**
 * WP7 experiment history surface (bounded, newest-first from the read plane;
 * the terminal never reorders it). A missing surface renders as no entries —
 * the panel shows the explicit empty state instead.
 */
export function buildWarRoomHistory(
  response: ExperimentalHistoryResponse | null,
): WarRoomHistoryEntry[] {
  if (!response) return [];
  const entries: WarRoomHistoryEntry[] = [];
  for (const run of response.runs ?? []) {
    entries.push({
      kind: "run",
      id: run.run_id,
      status: run.status,
      asOf: run.as_of,
      runClass: run.run_class ?? null,
    });
  }
  for (const evaluation of response.evaluations ?? []) {
    entries.push({
      kind: "evaluation",
      id: evaluation.evaluation_id,
      status: evaluation.status,
      asOf: evaluation.as_of,
      runClass: null,
    });
  }
  return entries;
}

export interface ExperimentalFeatureExplanation {
  name: string;
  definition: string;
  unit: string;
  /** Interpretable value or UNKNOWN; never a scalar score (R7). */
  value: string;
  status: "OBSERVED" | "UNKNOWN";
}

const EXPERIMENTAL_FEATURE_VOCABULARY: readonly {
  name: string;
  definition: string;
  unit: string;
}[] = [
  {
    name: "persistence",
    definition: "permyriad share of the 24 one-hour sub-windows of the 24h observation window containing prospective-eligible observations",
    unit: "permyriad",
  },
  {
    name: "novelty",
    definition: "permyriad share of windowed observations from sources contributing for the first time within the window",
    unit: "permyriad",
  },
  {
    name: "recency",
    definition: "10000 - floor(age_seconds * 10000 / 86400) for the newest windowed prospective-eligible observation",
    unit: "permyriad",
  },
  {
    name: "acceleration",
    definition: "late minus early half-window prospective-eligible observation counts within the 24h window",
    unit: "count",
  },
  {
    name: "breadth",
    definition: "count of distinct source_ids among windowed prospective-eligible observations",
    unit: "count",
  },
  {
    name: "propagation",
    definition: "count of distinct source_ids contributing beyond the primary lane",
    unit: "count",
  },
  {
    name: "recurrence",
    definition: "count of consecutive windowed observation pairs separated by at least one hour",
    unit: "count",
  },
  {
    name: "decay",
    definition: "staleness of the newest windowed observation in whole 6-hour steps (permyriad, bounded)",
    unit: "permyriad",
  },
  {
    name: "primary_emission_timing",
    definition: "seconds from the earliest prospective-eligible observation to the earliest PRIMARY_EMISSION observation; UNKNOWN when absent",
    unit: "seconds",
  },
  {
    name: "discovery_lag",
    definition: "seconds from the earliest ATTENTION/DISCOVERY observation to the earliest PRIMARY_EMISSION observation, clamped to 7 days; UNKNOWN when either lane is absent",
    unit: "seconds",
  },
];

/**
 * Feature explanations for the EXPERIMENTAL lens.
 *
 * Per-feature values are not exposed by the EXPERIMENTAL_SHADOW summary read
 * plane, so every value renders UNKNOWN with the batch identity visible.
 * UNKNOWN is an explicit epistemic state, never coerced to zero (R4, R7).
 */
export function buildFeatureExplanations(
  featureBatch: ExperimentalFeatureBatchResponse | null,
): ExperimentalFeatureExplanation[] {
  const batchRan =
    featureBatch !== null && featureBatch.status === "RAN" && featureBatch.vector_count !== null;
  const vectorCount = batchRan ? featureBatch.vector_count : null;
  return EXPERIMENTAL_FEATURE_VOCABULARY.map((feature) => ({
    ...feature,
    value:
      vectorCount === null
        ? "UNKNOWN"
        : `UNKNOWN (values not exposed; ${String(vectorCount)} vectors in batch)`,
    status: "UNKNOWN" as const,
  }));
}

export interface ExperimentalRunStatus {
  availability: ExperimentalAvailabilityState;
  run: ExperimentalShadowRunResponse | null;
}

/** Latest shadow-run status surface; explicit NO_DATA/UNKNOWN, never fabricated. */
export function buildShadowRunStatus(
  section: ExperimentalOverviewResponse["latest_shadow_run"] | null,
  availability: string | null | undefined,
): ExperimentalRunStatus {
  return {
    availability: experimentalAvailability(availability),
    run: section ?? null,
  };
}

// ---------------------------------------------------------------------------
// WP8 experiment command-center model
//
// Parses the WP7 ExperimentStatus surface (render_experiment_status) into an
// explicit, fail-closed war-room view model: FREEZE / WINDOW / SAMPLES /
// DOMAINS / PRECISION / LEAD / DRIFT / HEALTH. Every field keeps the stored
// state verbatim; anything absent or unparseable renders UNKNOWN — never 0,
// never a fabricated state (R4, R7, R8).
// ---------------------------------------------------------------------------

export interface WarRoomPrecision {
  state: string;
  precision: string | null;
  surfacedResolved: number | null;
  positiveSurfacedResolved: number | null;
}

export interface WarRoomDomainRow {
  domain: string;
  candidatePrecision: string | null;
  controlPrecision: string | null;
  candidateSurfacedResolved: number | null;
  controlSurfacedResolved: number | null;
  differenceLowerBound: string | null;
  medianLeadAdvantageSeconds: string | null;
  noninferiorityPass: boolean | null;
  qualifiesSampleAdequacy: boolean | null;
}

export interface WarRoomDomainCount {
  domain: string;
  anchorCount: number | null;
  pendingCount: number | null;
  resolvedPositiveCount: number | null;
  resolvedNegativeCount: number | null;
  unknownCount: number | null;
  excludedCount: number | null;
  unresolvedCoverageCount: number | null;
}

export interface WarRoomCommandCenter {
  availability: ExperimentalAvailabilityState;
  experimentId: string | null;
  candidateId: string | null;
  freeze: {
    state: string;
    receiptId: string | null;
    implementationState: string;
    implementationCommit: string | null;
    sourceRegistryState: string;
    sourceRegistryDigest: string | null;
  };
  window: {
    state: string;
    start: string | null;
    latestBoundaryAsOf: string | null;
    attemptStatus: string | null;
  };
  run: {
    state: string;
    runId: string | null;
    runStatus: string | null;
  };
  health: {
    coverageState: string;
  };
  samples: {
    qualifying: WarRoomDomainCount[];
    thresholds: Record<string, unknown> | null;
  };
  domains: WarRoomDomainRow[];
  precision: {
    candidate: WarRoomPrecision;
    baseline: WarRoomPrecision;
  };
  lead: {
    state: string;
    deltaSeconds: string | null;
  };
  drift: {
    state: string;
  };
  noninferiority: {
    state: string;
    lowerBound: string | null;
    margin: string | null;
  };
  evaluation: {
    state: string;
    status: string | null;
  };
}

function asRecord(value: unknown): Record<string, unknown> | null {
  if (value === null || value === undefined || typeof value !== "object" || Array.isArray(value)) {
    return null;
  }
  return value as Record<string, unknown>;
}

function asText(record: Record<string, unknown> | null, key: string): string | null {
  const value = record?.[key];
  return typeof value === "string" ? value : null;
}

function asInt(record: Record<string, unknown> | null, key: string): number | null {
  const value = record?.[key];
  return typeof value === "number" && Number.isInteger(value) && !Number.isNaN(value)
    ? value
    : null;
}

function asBool(record: Record<string, unknown> | null, key: string): boolean | null {
  const value = record?.[key];
  return typeof value === "boolean" ? value : null;
}

function asList(record: Record<string, unknown> | null, key: string): unknown[] {
  const value = record?.[key];
  return Array.isArray(value) ? value : [];
}

function parsePrecision(raw: unknown): WarRoomPrecision {
  const record = asRecord(raw);
  return {
    state: asText(record, "state") ?? "UNKNOWN",
    precision: asText(record, "precision"),
    surfacedResolved: asInt(record, "surfaced_resolved"),
    positiveSurfacedResolved: asInt(record, "positive_surfaced_resolved"),
  };
}

function parseDomainCount(raw: unknown): WarRoomDomainCount {
  const record = asRecord(raw);
  return {
    domain: asText(record, "domain") ?? "UNKNOWN",
    anchorCount: asInt(record, "anchor_count"),
    pendingCount: asInt(record, "pending_count"),
    resolvedPositiveCount: asInt(record, "resolved_positive_count"),
    resolvedNegativeCount: asInt(record, "resolved_negative_count"),
    unknownCount: asInt(record, "unknown_count"),
    excludedCount: asInt(record, "excluded_count"),
    unresolvedCoverageCount: asInt(record, "unresolved_coverage_count"),
  };
}

function parseDomainRow(raw: unknown): WarRoomDomainRow {
  const record = asRecord(raw);
  return {
    domain: asText(record, "domain") ?? "UNKNOWN",
    candidatePrecision: asText(record, "candidate_precision"),
    controlPrecision: asText(record, "control_precision"),
    candidateSurfacedResolved: asInt(record, "candidate_surfaced_resolved"),
    controlSurfacedResolved: asInt(record, "control_surfaced_resolved"),
    differenceLowerBound: asText(record, "difference_lower_bound"),
    medianLeadAdvantageSeconds: asText(record, "median_lead_time_advantage_seconds"),
    noninferiorityPass: asBool(record, "noninferiority_pass"),
    qualifiesSampleAdequacy: asBool(record, "qualifies_sample_adequacy"),
  };
}

/**
 * War-room command-center projection of the WP7 status surface. A missing or
 * NO_DATA/UNKNOWN surface degrades every cell to an explicit UNKNOWN — the
 * command center never looks like a healthy experiment when it cannot see one.
 */
export function buildExperimentCommandCenter(
  response: ExperimentalStatusResponse | null,
): WarRoomCommandCenter {
  const status = asRecord(response?.status);
  const availability = experimentalAvailability(response?.availability);
  const noninferiority = asRecord(status?.["noninferiority"]);
  const leadTime = asRecord(status?.["lead_time"]);
  return {
    availability,
    experimentId: asText(status, "experiment_id"),
    candidateId: asText(status, "candidate_id"),
    freeze: {
      state: asText(status, "candidate_freeze_state") ?? "UNKNOWN",
      receiptId: asText(status, "candidate_freeze_receipt_id"),
      implementationState: asText(status, "implementation_state") ?? "UNKNOWN",
      implementationCommit: asText(status, "implementation_commit"),
      sourceRegistryState: asText(status, "source_registry_state") ?? "UNKNOWN",
      sourceRegistryDigest: asText(status, "source_registry_digest"),
    },
    window: {
      state: asText(status, "window_state") ?? "UNKNOWN",
      start: asText(status, "window_start"),
      latestBoundaryAsOf: asText(status, "latest_boundary_as_of"),
      attemptStatus: asText(status, "latest_attempt_status"),
    },
    run: {
      state: asText(status, "run_state") ?? "UNKNOWN",
      runId: asText(status, "latest_run_id"),
      runStatus: asText(status, "latest_run_status"),
    },
    health: {
      coverageState: asText(status, "coverage_state") ?? "UNKNOWN",
    },
    samples: {
      qualifying: asList(status, "qualifying_opportunity_counts").map(parseDomainCount),
      thresholds: asRecord(status?.["sample_adequacy_thresholds"]),
    },
    domains: asList(status, "domain_evaluation_rows").map(parseDomainRow),
    precision: {
      candidate: parsePrecision(status?.["candidate_precision"]),
      baseline: parsePrecision(status?.["baseline_precision"]),
    },
    lead: {
      state: asText(leadTime, "state") ?? "UNKNOWN",
      deltaSeconds: asText(leadTime, "delta_median_advantage_seconds"),
    },
    drift: {
      state: asText(status, "drift_state") ?? "UNKNOWN",
    },
    noninferiority: {
      state: asText(noninferiority, "state") ?? "UNKNOWN",
      lowerBound: asText(noninferiority, "lower_bound"),
      margin: asText(noninferiority, "margin"),
    },
    evaluation: {
      state: asText(status, "evaluation_receipt_state") ?? "UNKNOWN",
      status: asText(status, "evaluation_receipt_status"),
    },
  };
}

