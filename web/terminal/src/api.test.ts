import { afterEach, describe, expect, it, vi } from "vitest";
import {
  BrowserPublicReadTransport,
  StaleSnapshotResponseError,
  createTerminalPublicReadApi,
  type EpisodeEvidenceResponse,
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
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ ok: true }), {
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
