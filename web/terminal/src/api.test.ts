import { afterEach, describe, expect, it, vi } from "vitest";
import {
  BrowserPublicReadTransport,
  experimentalAvailability,
  StaleSnapshotResponseError,
  createTerminalPublicReadApi,
  type EpisodeEvidenceResponse,
  type ExperimentalOverviewResponse,
  type FrontierPublicReadTransport,
  type HealthResponse,
  type ViewResponse,
} from "./api";

afterEach(() => {
  vi.unstubAllGlobals();
});

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((resolvePromise) => {
    resolve = resolvePromise;
  });
  return { promise, resolve };
}

function minimalView(snapshotId: string): ViewResponse {
  return { snapshot: { snapshot_id: snapshotId } } as unknown as ViewResponse;
}

function minimalEpisode(snapshotId: string): EpisodeEvidenceResponse {
  return { snapshot: { snapshot_id: snapshotId } } as unknown as EpisodeEvidenceResponse;
}

function minimalHealth(snapshotId: string): HealthResponse {
  return { snapshot: { snapshot_id: snapshotId } } as unknown as HealthResponse;
}

describe("BrowserPublicReadTransport", () => {
  it("uses GET only and serializes bounded query parameters", async () => {
    const fetchMock = vi.fn(async (_url: string | URL, _init?: RequestInit) => new Response(JSON.stringify({ ok: true }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }));
    vi.stubGlobal("fetch", fetchMock);
    const transport = new BrowserPublicReadTransport("https://frontier.example");
    await transport.get("/v0/radar", { snapshot_id: "snapshot_abc", limit: 500, ignored: null });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(String(url)).toContain("/v0/radar?snapshot_id=snapshot_abc&limit=500");
    expect((init as RequestInit | undefined)?.method).toBe("GET");
    expect(String(url)).not.toContain("ignored");
  });
});

describe("TerminalPublicReadApi snapshot races", () => {
  it("rejects stale episode and health completions after the active snapshot changes", async () => {
    const episodeResponse = deferred<EpisodeEvidenceResponse>();
    const healthResponse = deferred<HealthResponse>();

    class RaceTransport implements FrontierPublicReadTransport {
      async get<T>(path: string): Promise<T> {
        if (path === "/v0/radar") return minimalView("snapshot_old") as T;
        if (path === "/v0/now") return minimalView("snapshot_new") as T;
        if (path.startsWith("/v0/episodes/")) return (await episodeResponse.promise) as T;
        if (path === "/v0/health") return (await healthResponse.promise) as T;
        throw new Error(`Unexpected path: ${path}`);
      }
    }

    const api = createTerminalPublicReadApi(new RaceTransport());
    await api.view("RADAR", {});

    const pendingEpisode = api.episode("episode_old", "snapshot_old");
    const pendingHealth = api.health("snapshot_old");
    const episodeRejected = expect(pendingEpisode).rejects.toMatchObject({
      name: "StaleSnapshotResponseError",
      context: "episode",
      requestedSnapshotId: "snapshot_old",
      activeSnapshotId: "snapshot_new",
    });
    const healthRejected = expect(pendingHealth).rejects.toMatchObject({
      name: "StaleSnapshotResponseError",
      context: "health",
      requestedSnapshotId: "snapshot_old",
      activeSnapshotId: "snapshot_new",
    });

    await api.view("NOW", {});
    episodeResponse.resolve(minimalEpisode("snapshot_old"));
    healthResponse.resolve(minimalHealth("snapshot_old"));

    await episodeRejected;
    await healthRejected;
    await expect(Promise.reject(new StaleSnapshotResponseError("episode", "old", "new"))).rejects.toBeInstanceOf(
      StaleSnapshotResponseError,
    );
  });
});

describe("TerminalPublicReadApi experimental surfaces (slice H)", () => {
  it("issues GET requests for the EXPERIMENTAL_SHADOW surfaces with the bound as_of", async () => {
    const overview: ExperimentalOverviewResponse = {
      analysis_artifacts: {},
      as_of: "2026-09-05T12:00:00.000000Z",
      availability: { shadow_run: "NO_DATA" },
      candidate_id: "pef_v0",
      configuration_digest: "sha256:cfg",
      experiment_id: "exp_pef_v0",
      generated_at: "2026-09-05T12:00:01.000000Z",
      latest_evaluation_receipt: null,
      latest_feature_batch: null,
      latest_pef_artifact: null,
      latest_shadow_run: null,
    };
    const paths: Array<{ path: string; query: Record<string, string | number | boolean | null | undefined> }> = [];
    const sectionPayload = { availability: "NO_DATA", latest: null };
    const transport: FrontierPublicReadTransport = {
      async get<T>(path: string, query = {}): Promise<T> {
        paths.push({ path, query });
        return (path === "/v0/experimental/overview" ? overview : sectionPayload) as T;
      },
    };
    const api = createTerminalPublicReadApi(transport);
    const [returnedOverview, runs, batches] = await Promise.all([
      api.experimentalOverview("2026-09-05T12:00:00.000000Z"),
      api.experimentalShadowRuns("2026-09-05T12:00:00.000000Z"),
      api.experimentalFeatureBatches(undefined),
    ]);
    expect(returnedOverview).toBe(overview);
    expect(runs.latest).toBeNull();
    expect(runs.availability).toBe("NO_DATA");
    expect(batches.availability).toBe("NO_DATA");
    expect(batches.latest).toBeNull();
    expect(paths.map((call) => call.path)).toEqual([
      "/v0/experimental/overview",
      "/v0/experimental/shadow-runs",
      "/v0/experimental/feature-batches",
    ]);
    expect(paths[0]?.query.as_of).toBe("2026-09-05T12:00:00.000000Z");
    expect(paths[1]?.query.as_of).toBe("2026-09-05T12:00:00.000000Z");
    expect(Object.hasOwn(paths[2]?.query ?? {}, "as_of")).toBe(false);
  });

  it("normalizes availability fail-closed: only exact states survive", () => {
    expect(experimentalAvailability("AVAILABLE")).toBe("AVAILABLE");
    expect(experimentalAvailability("NO_DATA")).toBe("NO_DATA");
    expect(experimentalAvailability("UNKNOWN")).toBe("UNKNOWN");
    expect(experimentalAvailability("available")).toBe("UNKNOWN");
    expect(experimentalAvailability("RAN")).toBe("UNKNOWN");
    expect(experimentalAvailability(null)).toBe("UNKNOWN");
    expect(experimentalAvailability(undefined)).toBe("UNKNOWN");
  });
});
