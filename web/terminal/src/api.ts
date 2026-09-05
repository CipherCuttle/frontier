import {
  getEpisode,
  getHealth,
  getNow,
  getRadar,
  getTrending,
  type EpisodeEvidenceResponse,
  type FrontierPublicReadTransport,
  type HealthResponse,
  type PublicViewKind,
  type ViewResponse,
} from "../../../clients/typescript/src/generated/public_read_v0";

export type {
  EpisodeEvidenceResponse,
  EpisodeResponse,
  FrontierPublicReadTransport,
  HealthResponse,
  ObservationEvidenceResponse,
  PublicViewKind,
  SnapshotBindingResponse,
  SourceHealthResponse,
  ViewResponse,
} from "../../../clients/typescript/src/generated/public_read_v0";

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
}

export function createTerminalPublicReadApi(
  transport: FrontierPublicReadTransport,
): TerminalPublicReadApi {
  return {
    async view(lens, options) {
      const query = {
        limit: options.limit ?? 500,
        offset: options.offset ?? 0,
        ...(options.snapshotId ? { snapshot_id: options.snapshotId } : {}),
      };
      if (lens === "RADAR") return getRadar(transport, query);
      if (lens === "NOW") return getNow(transport, query);
      return getTrending(transport, query);
    },
    episode(episodeId, snapshotId) {
      return getEpisode(transport, episodeId, { snapshot_id: snapshotId });
    },
    health(snapshotId) {
      return getHealth(transport, { snapshot_id: snapshotId });
    },
  };
}
