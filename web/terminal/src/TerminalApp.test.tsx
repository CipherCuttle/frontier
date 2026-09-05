import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type {
  EpisodeEvidenceResponse,
  FrontierPublicReadTransport,
  HealthResponse,
  ViewResponse,
} from "./api";
import { TerminalApp } from "./TerminalApp";

afterEach(cleanup);

const snapshot = {
  algorithm_version: "windowed-episode-metrics-v0",
  as_of: "2026-09-05T12:00:00.000000Z",
  configuration_digest: "sha256:cfg",
  input_digest: "sha256:input",
  output_digest: "sha256:output",
  projection_name: "baseline-intelligence",
  projection_version: "baseline-intelligence-v0",
  ranking_policy_version: "naive-episode-activity-v0",
  receipt_id: "receipt_fixture",
  receipt_schema_version: "projection-receipt-v1",
  schema_version: "baseline-intelligence-snapshot-v0",
  snapshot_id: "snapshot_fixture",
  source_registry_version: "sha256:registry",
} as const;

const episode = {
  acceleration_6h: 2,
  age_seconds: 90,
  backfill_evidence_count: 0,
  confirmation: "UNAVAILABLE",
  episode_id: "episode_fixture",
  evidence_count_total: 2,
  evidence_root_diversity: null,
  first_observed_at: "2026-09-05T11:58:00.000000Z",
  last_observed_at: "2026-09-05T11:59:00.000000Z",
  mentions_1h: 2,
  mentions_24h: 2,
  mentions_6h: 2,
  observation_ids: ["obs_fixture"],
  preprevious_6h: 0,
  previous_6h: 0,
  prospective_evidence_count: 2,
  rank: 7,
  recovered_backlog_evidence_count: 0,
  signal_roles: ["ATTENTION", "PRIMARY_EMISSION"],
  source_count: 2,
  source_ids: ["source.one", "source.two"],
  source_role_diversity: 2,
  velocity_6h_delta: 2,
} as const;

function viewResponse(view: "RADAR" | "NOW" | "TRENDING" = "RADAR"): ViewResponse {
  return {
    coverage_state: "UNKNOWN",
    freshness_state: "DEGRADED",
    generated_at: "2026-09-05T12:00:01.000000Z",
    items: [{ ...episode, observation_ids: [...episode.observation_ids], signal_roles: [...episode.signal_roles], source_ids: [...episode.source_ids] }],
    limit: 500,
    offset: 0,
    schema_state: "OK",
    semantic_scope: "BASELINE_SUBSTRATE",
    snapshot: { ...snapshot },
    total: 1,
    transport_state: "OK",
    view,
    view_policy_version: view === "RADAR" ? "radar-baseline-order-v0" : "fixture-policy-v0",
  };
}

const evidenceResponse: EpisodeEvidenceResponse = {
  episode: { ...episode, observation_ids: [...episode.observation_ids], signal_roles: [...episode.signal_roles], source_ids: [...episode.source_ids] },
  generated_at: "2026-09-05T12:00:01.000000Z",
  observations: [{
    canonicalization_version: "canonical-v1",
    collection_occurrences: [],
    content_digest: "sha256:content",
    effective_at: null,
    fetch_digest: "sha256:fetch",
    kind: "ATTENTION",
    observation_id: "obs_fixture",
    observed_at: "2026-09-05T11:59:00.000000Z",
    payload: { title: "Evidence payload title" },
    relations: [],
    retrieved_at: "2026-09-05T11:58:59.000000Z",
    schema_version: "observation-v1",
    source_id: "source.one",
    source_item_key: "item-1",
    source_published_at: null,
  }],
  snapshot: { ...snapshot },
};

const healthResponse: HealthResponse = {
  coverage_state: "UNKNOWN",
  freshness_state: "DEGRADED",
  generated_at: "2026-09-05T12:00:01.000000Z",
  schema_state: "OK",
  snapshot: { ...snapshot },
  sources: [{
    as_of: snapshot.as_of,
    completeness: "UNKNOWN",
    details: {},
    freshness: "DEGRADED",
    schema: "OK",
    source_id: "source.one",
    transport: "OK",
  }],
  transport_state: "OK",
};

class FakeTransport implements FrontierPublicReadTransport {
  readonly calls: Array<{ path: string; query: Record<string, unknown> }> = [];

  async get<T>(
    path: string,
    query: Record<string, string | number | boolean | null | undefined> = {},
  ): Promise<T> {
    this.calls.push({ path, query });
    if (path.startsWith("/v0/episodes/")) return evidenceResponse as T;
    if (path === "/v0/health") return healthResponse as T;
    if (path === "/v0/now") return viewResponse("NOW") as T;
    if (path === "/v0/trending") return viewResponse("TRENDING") as T;
    return viewResponse("RADAR") as T;
  }
}

describe("TERMINAL_V0", () => {
  it("renders baseline authority and unavailable epistemic states without source-count overclaim", async () => {
    const transport = new FakeTransport();
    render(<TerminalApp transport={transport} />);
    await screen.findByText("#7");
    expect(screen.getAllByText("UNAVAILABLE").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("BASELINE SUBSTRATE")).toBeTruthy();
    expect(screen.queryByText(/independently confirmed/i)).toBeNull();
    expect(screen.getByText("UNKNOWN")).toBeTruthy();
  });

  it("uses the exact selected snapshot for health and episode drilldown", async () => {
    const transport = new FakeTransport();
    render(<TerminalApp transport={transport} />);
    await screen.findByText("#7");
    fireEvent.keyDown(window, { key: "h" });
    await screen.findByText("Health + coverage");
    fireEvent.keyDown(window, { key: "Escape" });
    fireEvent.keyDown(window, { key: "Enter" });
    await screen.findByText("Evidence inspector");
    const boundCalls = transport.calls.filter((call) => call.path === "/v0/health" || call.path.startsWith("/v0/episodes/"));
    expect(boundCalls).toHaveLength(2);
    for (const call of boundCalls) expect(call.query.snapshot_id).toBe(snapshot.snapshot_id);
  });

  it("switches lenses while preserving the selected snapshot binding", async () => {
    const transport = new FakeTransport();
    render(<TerminalApp transport={transport} />);
    await screen.findByText("#7");
    fireEvent.keyDown(window, { key: "2" });
    await waitFor(() => expect(transport.calls.some((call) => call.path === "/v0/now")).toBe(true));
    const nowCall = transport.calls.find((call) => call.path === "/v0/now");
    expect(nowCall?.query.snapshot_id).toBe(snapshot.snapshot_id);
  });
});
