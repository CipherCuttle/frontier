import {
  getEpisode,
  getExperimentalEpisodeComparison,
  getExperimentalEvaluationDetail,
  getExperimentalFeatureBatches,
  getExperimentalHistory,
  getExperimentalOverview,
  getExperimentalRunDetail,
  getExperimentalShadowRuns,
  getExperimentalStatus,
  getHealth,
  getNow,
  getRadar,
  getTrending,
  type EpisodeEvidenceResponse,
  type ExperimentalEpisodeComparisonResponse,
  type ExperimentalEvaluationDetailSectionResponse,
  type ExperimentalFeatureBatchSectionResponse,
  type ExperimentalHistoryResponse,
  type ExperimentalOverviewResponse,
  type ExperimentalRunDetailSectionResponse,
  type ExperimentalShadowRunSectionResponse,
  type ExperimentalStatusResponse,
  type FrontierPublicReadTransport,
  type HealthResponse,
  type PublicViewKind,
  type ViewResponse,
} from "../../../clients/typescript/src/generated/public_read_v0";

export type {
  EpisodeEvidenceResponse,
  EpisodeResponse,
  ExperimentalAnalysisArtifactResponse,
  ExperimentalEpisodeComparisonResponse,
  ExperimentalEvaluationDetailResponse,
  ExperimentalEvaluationDetailSectionResponse,
  ExperimentalEvaluationReceiptResponse,
  ExperimentalFeatureBatchResponse,
  ExperimentalFeatureBatchSectionResponse,
  ExperimentalHistoryResponse,
  ExperimentalOverviewResponse,
  ExperimentalPefArtifactResponse,
  ExperimentalRunDetailResponse,
  ExperimentalRunDetailSectionResponse,
  ExperimentalShadowRunResponse,
  ExperimentalShadowRunSectionResponse,
  ExperimentalStatusResponse,
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

/**
 * Experiment identity binding (WP8): the run / freeze / evaluation identity
 * the EXPERIMENTAL surfaces are currently bound to. Not just a snapshot id —
 * experimental responses are only valid against the bound experiment identity.
 */
export interface ExperimentalIdentityBinding {
  runId: string | null;
  freezeReceiptId: string | null;
  evaluationReceiptId: string | null;
}

export class StaleExperimentResponseError extends Error {
  readonly context: string;
  readonly requested: ExperimentalIdentityBinding | null;
  readonly active: ExperimentalIdentityBinding | null;

  constructor(
    context: string,
    requested: ExperimentalIdentityBinding | null,
    active: ExperimentalIdentityBinding | null,
  ) {
    super(
      `Discarded stale ${context} response; the experiment identity moved from ` +
        `${describeBinding(requested)} to ${describeBinding(active)} mid-flight.`,
    );
    this.name = "StaleExperimentResponseError";
    this.context = context;
    this.requested = requested;
    this.active = active;
  }
}

function describeBinding(binding: ExperimentalIdentityBinding | null): string {
  if (!binding) return "UNBOUND";
  return (
    `run=${binding.runId ?? "UNKNOWN"}` +
    ` freeze=${binding.freezeReceiptId ?? "UNKNOWN"}` +
    ` evaluation=${binding.evaluationReceiptId ?? "UNKNOWN"}`
  );
}

function bindingChanged(
  requested: ExperimentalIdentityBinding | null,
  active: ExperimentalIdentityBinding | null,
): boolean {
  if (requested === null || active === null) return requested !== active;
  return (
    requested.runId !== active.runId ||
    requested.freezeReceiptId !== active.freezeReceiptId ||
    requested.evaluationReceiptId !== active.evaluationReceiptId
  );
}

/**
 * A non-null response identity that contradicts the bound identity means the
 * response belongs to a superseded run/freeze/evaluation — discard it (R4).
 */
function identityMismatch(
  binding: ExperimentalIdentityBinding,
  response: ExperimentalIdentityBinding,
): boolean {
  return (
    (binding.runId !== null && response.runId !== null && binding.runId !== response.runId) ||
    (binding.freezeReceiptId !== null &&
      response.freezeReceiptId !== null &&
      binding.freezeReceiptId !== response.freezeReceiptId) ||
    (binding.evaluationReceiptId !== null &&
      response.evaluationReceiptId !== null &&
      binding.evaluationReceiptId !== response.evaluationReceiptId)
  );
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
  /**
   * Labelled EXPERIMENTAL_SHADOW per-episode baseline-vs-candidate comparison
   * (WP7). Guarded by the experiment identity binding: responses from a
   * superseded run/freeze/evaluation are discarded, never rendered.
   */
  experimentalEpisodeComparison(
    episodeId: string,
    options?: { asOf?: string; runId?: string },
  ): Promise<ExperimentalEpisodeComparisonResponse>;
  /** Labelled EXPERIMENTAL_SHADOW full run detail (GET only). */
  experimentalRunDetail(runId: string): Promise<ExperimentalRunDetailSectionResponse>;
  /** Labelled EXPERIMENTAL_SHADOW full evaluation detail (GET only). */
  experimentalEvaluationDetail(
    evaluationId: string,
  ): Promise<ExperimentalEvaluationDetailSectionResponse>;
  /** Labelled EXPERIMENTAL_SHADOW coherent experiment status surface (WP7). */
  experimentalStatus(): Promise<ExperimentalStatusResponse>;
  /** Labelled EXPERIMENTAL_SHADOW bounded newest-first experiment history (WP7). */
  experimentalHistory(limit?: number): Promise<ExperimentalHistoryResponse>;
  /**
   * Bind the active experiment identity (run/freeze/evaluation). Experimental
   * fetches issued afterwards discard responses that belong to a superseded
   * identity — the war-room analogue of the snapshot stale-response guard.
   */
  setExperimentalBinding(binding: ExperimentalIdentityBinding | null): void;
}

export function createTerminalPublicReadApi(
  transport: FrontierPublicReadTransport,
): TerminalPublicReadApi {
  let activeSnapshotId: string | null = null;
  let experimentalBinding: ExperimentalIdentityBinding | null = null;

  const requireActiveSnapshot = (
    context: "episode" | "health",
    requestedSnapshotId: string,
  ): void => {
    if (activeSnapshotId !== requestedSnapshotId) {
      throw new StaleSnapshotResponseError(context, requestedSnapshotId, activeSnapshotId);
    }
  };

  const requireFreshIdentity = (
    context: string,
    bindingAtRequest: ExperimentalIdentityBinding | null,
    responseIdentity: ExperimentalIdentityBinding | null,
  ): void => {
    if (bindingChanged(bindingAtRequest, experimentalBinding)) {
      throw new StaleExperimentResponseError(context, bindingAtRequest, experimentalBinding);
    }
    if (
      bindingAtRequest !== null &&
      responseIdentity !== null &&
      identityMismatch(bindingAtRequest, responseIdentity)
    ) {
      throw new StaleExperimentResponseError(context, bindingAtRequest, experimentalBinding);
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
    async experimentalEpisodeComparison(episodeId, options = {}) {
      const bindingAtRequest = experimentalBinding;
      const query = {
        ...(options.asOf ? { as_of: options.asOf } : {}),
        ...(options.runId ? { run_id: options.runId } : {}),
      };
      const response = await getExperimentalEpisodeComparison(transport, episodeId, query);
      requireFreshIdentity("episode comparison", bindingAtRequest, {
        runId: response.run_id,
        freezeReceiptId: response.candidate_freeze_receipt_id,
        evaluationReceiptId: response.evaluation_receipt_id,
      });
      return response;
    },
    async experimentalRunDetail(runId) {
      const bindingAtRequest = experimentalBinding;
      const response = await getExperimentalRunDetail(transport, runId, {});
      requireFreshIdentity("run detail", bindingAtRequest, null);
      return response;
    },
    async experimentalEvaluationDetail(evaluationId) {
      const bindingAtRequest = experimentalBinding;
      const response = await getExperimentalEvaluationDetail(transport, evaluationId, {});
      requireFreshIdentity("evaluation detail", bindingAtRequest, null);
      return response;
    },
    async experimentalStatus() {
      const bindingAtRequest = experimentalBinding;
      const response = await getExperimentalStatus(transport);
      requireFreshIdentity("experiment status", bindingAtRequest, null);
      return response;
    },
    async experimentalHistory(limit) {
      const bindingAtRequest = experimentalBinding;
      const query = limit ? { limit } : {};
      const response = await getExperimentalHistory(transport, query);
      requireFreshIdentity("experiment history", bindingAtRequest, null);
      return response;
    },
    setExperimentalBinding(binding) {
      experimentalBinding = binding;
    },
  };
}
