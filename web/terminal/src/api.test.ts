import { afterEach, describe, expect, it, vi } from "vitest";
import { BrowserPublicReadTransport } from "./api";

afterEach(() => {
  vi.unstubAllGlobals();
});

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
