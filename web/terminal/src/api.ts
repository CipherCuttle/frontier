import {
  getEpisode,
  getExperimentalFeatureBatches,
  getExperimentalOverview,
  getExperimentalShadowRuns,
  getHealth,
  getNow,
  getRadar,
  getTrending,
  type EpisodeEvidenceResponse,
  type ExperimentalFeatureBatchSectionResponse,
  type ExperimentalOverviewResponse,
  type ExperimentalShadowRunSectionResponse,
  type FrontierPublicReadTransport,
  type HealthResponse,
  type PublicViewKind,
  type ViewResponse,
} from "../../../clients/typescript/src/generated/public_read_v0";

export type {
  EpisodeEvidenceResponse,
  EpisodeResponse,
  ExperimentalAnalysisArtifactResponse,
  ExperimentalEvaluationReceiptResponse,
  ExperimentalFeatureBatchResponse,
  ExperimentalFeatureBatchSectionResponse,
  ExperimentalOverviewResponse,
  ExperimentalPefArtifactResponse,
  ExperimentalShadowRunResponse,
  ExperimentalShadowRunSectionResponse,
  FrontierPublicReadTransport,
  HealthResponse,
  ObservationEvidenceResponse,
  PublicViewKind,
  SnapshotBindingResponse,
  SourceHealthResponse,
  ViewResponse,
} from "../../../clients/typescript/src/generated/public_read_v0";

/** Explicit EXPERIMENTAL_SHADOW availability states (R4): never fabricated. */
export type ExperimentalAvailabilityState = "AVAILABLE" | "NO_DATA" | "UNKNOWN";

const KNOWN_AVAILABILITY_STATES: readonly ExperimentalAvailabilityState[] = [
  "AVAILABLE",
  "NO_DATA",
  "UNKNOWN",
];

/**
 * Normalize an EXPERIMENTAL_SHADOW availability value.
 *
 * Fail-closed (R4): anything that is not an exact known state — including an
 * unknown status string — resolves to UNKNOWN, never to AVAILABLE or NO_DATA.
 */
export function experimentalAvailability(
  value: string | null | undefined,
): ExperimentalAvailabilityState {
  return KNOWN_AVAILABILITY_STATES.includes(value as ExperimentalAvailabilityState)
    ? (value as ExperimentalAvailabilityState)
    : "UNKNOWN";
}

export class PublicReadHttpError extends Error {
  readonly status: number;
  readonly code: string | null;

  constructor(status: number, code: string | null, message: string) {
    super(message);
    this.name = "PublicReadHttpError";
    this.status = status;
    this.code = code;
  }
}

export class StaleSnapshotResponseError extends Error {
  readonly requestedSnapshotId: string;
  readonly activeSnapshotId: string | null;
  readonly context: "episode" | "health";

  constructor(
    context: "episode" | "health",
    requestedSnapshotId: string,
    activeSnapshotId: string | null,
  ) {
    super(
      `Discarded stale ${context} response for snapshot ${requestedSnapshotId}; active snapshot is ${activeSnapshotId ?? "UNBOUND"}.`,
    );
    this.name = "StaleSnapshotResponseError";
    this.context = context;
    this.requestedSnapshotId = requestedSnapshotId;
    this.activeSnapshotId = activeSnapshotId;
  }
}

export class BrowserPublicReadTransport implements FrontierPublicReadTransport {
  private readonly baseUrl: string;

  constructor(baseUrl: string) {
    this.baseUrl = baseUrl.replace(/\/$/, "");
  }

  async get<T>(
    path: string,
    query: Record<string, string | number | boolean | null | undefined> = {},
  ): Promise<T> {
    const url = new URL(`${this.baseUrl}${path}`, window.location.origin);
    for (const [key, value] of Object.entries(query)) {
      if (value !== null && value !== undefined) {
        url.searchParams.set(key, String(value));
      }
    }
    const response = await fetch(url, {
      method: "GET",
      headers: { Accept: "application/json" },
    });
    if (!response.ok) {
      let code: string | null = null;
      let detail = `Public read request failed with HTTP ${response.status}.`;
      try {
        const body = (await response.json()) as { error?: unknown; detail?: unknown };
        if (typeof body.error === "string") code = body.error;
        if (typeof body.detail === "string") detail = body.detail;
      } catch {
        // Preserve the bounded HTTP status message when the error body is not JSON.
      }
      throw new PublicReadHttpError(response.status, code, detail);
    }
    return (await response.json()) as T;
  }
}

export interface TerminalPublicReadApi {
  view(
    lens: PublicViewKind,
    options: { snapshotId?: string; limit?: number; offset?: number },
  ): Promise<ViewResponse>;
  episode(episodeId: string, snapshotId: string): Promise<EpisodeEvidenceResponse>;
  health(snapshotId: string): Promise<HealthResponse>;
  /** Labelled EXPERIMENTAL_SHADOW overview (identity/status surfaces only). */
  experimentalOverview(asOf?: string): Promise<ExperimentalOverviewResponse>;
  /** Labelled EXPERIMENTAL_SHADOW latest-shadow-run section (GET only). */
  experimentalShadowRuns(asOf?: string): Promise<ExperimentalShadowRunSectionResponse>;
  /** Labelled EXPERIMENTAL_SHADOW latest-feature-batch section (GET only). */
  experimentalFeatureBatches(asOf?: string): Promise<ExperimentalFeatureBatchSectionResponse>;
}

export function createTerminalPublicReadApi(
  transport: FrontierPublicReadTransport,
): TerminalPublicReadApi {
  let activeSnapshotId: string | null = null;

  const requireActiveSnapshot = (
    context: "episode" | "health",
    requestedSnapshotId: string,
  ): void => {
    if (activeSnapshotId !== requestedSnapshotId) {
      throw new StaleSnapshotResponseError(context, requestedSnapshotId, activeSnapshotId);
    }
  };

  return {
    async view(lens, options) {
      const query = {
        limit: options.limit ?? 500,
        offset: options.offset ?? 0,
        ...(options.snapshotId ? { snapshot_id: options.snapshotId } : {}),
      };
      if (!options.snapshotId) activeSnapshotId = null;
      const response =
        lens === "RADAR"
          ? await getRadar(transport, query)
          : lens === "NOW"
            ? await getNow(transport, query)
            : await getTrending(transport, query);
      activeSnapshotId = response.snapshot.snapshot_id;
      return response;
    },
    async episode(episodeId, snapshotId) {
      const response = await getEpisode(transport, episodeId, { snapshot_id: snapshotId });
      requireActiveSnapshot("episode", snapshotId);
      return response;
    },
    async health(snapshotId) {
      const response = await getHealth(transport, { snapshot_id: snapshotId });
      requireActiveSnapshot("health", snapshotId);
      return response;
    },
    async experimentalOverview(asOf) {
      // EXPERIMENTAL_SHADOW surface: read-only GET; never mutates or reranks
      // the baseline plane. Sections carry explicit NO_DATA/UNKNOWN states (R4).
      const query = asOf ? { as_of: asOf } : {};
      return await getExperimentalOverview(transport, query);
    },
    async experimentalShadowRuns(asOf) {
      const query = asOf ? { as_of: asOf } : {};
      return await getExperimentalShadowRuns(transport, query);
    },
    async experimentalFeatureBatches(asOf) {
      const query = asOf ? { as_of: asOf } : {};
      return await getExperimentalFeatureBatches(transport, query);
    },
  };
}
