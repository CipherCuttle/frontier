import type {
  EpisodeResponse,
  ExperimentalAvailabilityState,
  ExperimentalFeatureBatchResponse,
  ExperimentalOverviewResponse,
  ExperimentalShadowRunResponse,
  PublicViewKind,
} from "./api";
import { experimentalAvailability } from "./api";

export type PanelKind = "inspector" | "health" | "audit" | "help";

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
// EXPERIMENTAL lens model (slice H)
//
// Everything below renders EXPERIMENTAL_SHADOW read surfaces (R7): identity,
// digests, and statuses only. Missing data is an explicit EMPTY/UNKNOWN state
// and is never fabricated into baseline-looking intelligence (R4).
// ---------------------------------------------------------------------------

/** Resolve one overview section's availability, fail-closed to UNKNOWN (R4). */
export function resolveSectionAvailability(
  availability: Record<string, string> | null | undefined,
  section: string,
): ExperimentalAvailabilityState {
  const value = availability?.[section];
  return value === undefined || value === null ? "UNKNOWN" : experimentalAvailability(value);
}

export interface ExperimentalRankDelta {
  episodeId: string;
  baselineRank: number;
  /** Null means the candidate rank is not exposed by the summary surface (UNKNOWN). */
  experimentalRank: number | null;
  /** experimentalRank - baselineRank; null while the candidate rank is UNKNOWN. */
  delta: number | null;
}

/**
 * Baseline-vs-candidate rank deltas for the EXPERIMENTAL lens.
 *
 * ``candidateRanks`` must come from an EXPERIMENTAL_SHADOW surface. The
 * current summary read plane exposes run/artifact identity and status only,
 * not per-episode candidate ranks, so the terminal passes null and renders
 * every experimental rank/delta as UNKNOWN — never invented (R4, R7).
 */
export function computeRankDeltas(
  baselineItems: readonly EpisodeResponse[],
  candidateRanks: ReadonlyMap<string, number> | null,
): ExperimentalRankDelta[] {
  return baselineItems.map((item) => {
    const experimentalRank = candidateRanks?.get(item.episode_id) ?? null;
    const delta = experimentalRank === null ? null : experimentalRank - item.rank;
    return { episodeId: item.episode_id, baselineRank: item.rank, experimentalRank, delta };
  });
}

export function displayRankDelta(delta: number | null): string {
  if (delta === null) return "UNKNOWN";
  if (delta === 0) return "±0";
  return `${delta > 0 ? "+" : ""}${delta}`;
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
