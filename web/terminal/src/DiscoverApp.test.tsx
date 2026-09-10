import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type {
  EpisodeEvidenceResponse,
  EpisodeResponse,
  FrontierPublicReadTransport,
  ObservationEvidenceResponse,
  ObservationResponse,
  ViewResponse,
} from "../../../clients/typescript/src/generated/public_read_v0";
import { DiscoverApp } from "./DiscoverApp";

afterEach(cleanup);

const snapshot = {
  algorithm_version: "windowed-episode-metrics-v0",
  as_of: "2026-09-10T18:00:00.000000Z",
  configuration_digest: "sha256:cfg",
  input_digest: "sha256:input",
  output_digest: "sha256:output",
  projection_name: "baseline-intelligence",
  projection_version: "baseline-intelligence-v0",
  ranking_policy_version: "naive-episode-activity-v0",
  receipt_id: "receipt_fixture",
  receipt_schema_version: "projection-receipt-v1",
  schema_version: "baseline-intelligence-snapshot-v0",
  snapshot_id: "snapshot_discover",
  source_registry_version: "sha256:registry",
};

function episode(
  rank: number,
  id: string,
  observationId: string,
  overrides: Partial<EpisodeResponse> = {},
): EpisodeResponse {
  return {
    acceleration_6h: 0,
    age_seconds: 300,
    backfill_evidence_count: 0,
    confirmation: "UNAVAILABLE",
    episode_id: id,
    evidence_count_total: 1,
    evidence_root_diversity: null,
    first_observed_at: "2026-09-10T17:55:00.000000Z",
    last_observed_at: "2026-09-10T17:55:00.000000Z",
    mentions_1h: 1,
    mentions_24h: 1,
    mentions_6h: 1,
    observation_ids: [observationId],
    preprevious_6h: 0,
    previous_6h: 0,
    prospective_evidence_count: 1,
    rank,
    recovered_backlog_evidence_count: 0,
    signal_roles: ["PRIMARY_EMISSION"],
    source_count: 1,
    source_ids: ["pypi.updates"],
    source_role_diversity: 1,
    velocity_6h_delta: 0,
    ...overrides,
  };
}

const agentEpisode = episode(1, "episode_agent", "obs_agent", { velocity_6h_delta: 3 });
const securityEpisode = episode(2, "episode_security", "obs_security", {
  mentions_1h: 0,
  signal_roles: ["PRIMARY_EMISSION"],
  source_ids: ["cisa.kev"],
});

function observation(
  observationId: string,
  sourceId: string,
  payload: Record<string, unknown>,
): ObservationEvidenceResponse {
  return {
    canonicalization_version: "frontier-canonical-json-v1",
    collection_occurrences: [],
    content_digest: `sha256:${observationId}`,
    effective_at: null,
    fetch_digest: "sha256:fetch",
    kind: sourceId === "pypi.updates" ? "ARTIFACT" : "DOCUMENT",
    observation_id: observationId,
    observed_at: "2026-09-10T17:55:00.000000Z",
    payload,
    relations: [],
    retrieved_at: "2026-09-10T17:55:00.000000Z",
    schema_version: "observation-v1",
    source_id: sourceId,
    source_item_key: observationId,
    source_published_at: null,
  };
}

const agentObservation = observation("obs_agent", "pypi.updates", {
  canonical_url: "https://pypi.org/project/hyper-agent/0.2.0/",
  name: "hyper-agent",
  version: "0.2.0",
  source_metadata: { description: "A local-first agent runtime" },
});
const securityObservation = observation("obs_security", "cisa.kev", {
  canonical_url: "https://www.cisa.gov/known-exploited-vulnerabilities-catalog",
  title: "Freshly exploited edge appliance bug",
  excerpt: "Known exploitation has been added to the catalog.",
});

const radar: ViewResponse = {
  coverage_state: "OK",
  freshness_state: "OK",
  generated_at: "2026-09-10T18:00:02.000000Z",
  items: [agentEpisode, securityEpisode],
  limit: 100,
  offset: 0,
  schema_state: "OK",
  semantic_scope: "BASELINE_SUBSTRATE",
  snapshot,
  total: 2,
  transport_state: "OK",
  view: "RADAR",
  view_policy_version: "baseline-read-views-v0",
};

class DiscoveryTransport implements FrontierPublicReadTransport {
  readonly calls: Array<{ path: string; query: Record<string, unknown> }> = [];

  async get<T>(
    path: string,
    query: Record<string, string | number | boolean | null | undefined> = {},
  ): Promise<T> {
    this.calls.push({ path, query });
    if (path === "/v0/radar") return radar as T;
    if (path === "/v0/observations/obs_agent") {
      return {
        generated_at: radar.generated_at,
        observation: agentObservation,
        snapshot,
      } satisfies ObservationResponse as T;
    }
    if (path === "/v0/observations/obs_security") {
      return {
        generated_at: radar.generated_at,
        observation: securityObservation,
        snapshot,
      } satisfies ObservationResponse as T;
    }
    if (path === "/v0/episodes/episode_agent") {
      return {
        episode: agentEpisode,
        generated_at: radar.generated_at,
        observations: [agentObservation],
        snapshot,
      } satisfies EpisodeEvidenceResponse as T;
    }
    throw new Error(`unexpected request ${path}`);
  }
}

describe("DISCOVER default surface", () => {
  it("loads baseline RADAR, hydrates human titles at the exact snapshot, and searches them", async () => {
    const transport = new DiscoveryTransport();
    render(<DiscoverApp transport={transport} />);

    await screen.findByText("hyper-agent 0.2.0");
    await screen.findByText("Freshly exploited edge appliance bug");

    const radarCall = transport.calls.find((call) => call.path === "/v0/radar");
    expect(radarCall?.query.limit).toBe(100);
    const observationCalls = transport.calls.filter((call) => call.path.startsWith("/v0/observations/"));
    expect(observationCalls).toHaveLength(2);
    for (const call of observationCalls) expect(call.query.snapshot_id).toBe(snapshot.snapshot_id);

    fireEvent.change(screen.getByPlaceholderText("models, agents, CVEs, packages, repos…"), {
      target: { value: "edge appliance" },
    });
    expect(screen.queryByText("hyper-agent 0.2.0")).toBeNull();
    expect(screen.getByText("Freshly exploited edge appliance bug")).toBeTruthy();
  });

  it("filters by clickable lane without reranking the default baseline sequence", async () => {
    const transport = new DiscoveryTransport();
    render(<DiscoverApp transport={transport} />);
    await screen.findByText("hyper-agent 0.2.0");

    const cards = document.querySelectorAll(".discover-card");
    expect([...cards].map((card) => card.getAttribute("data-episode-id"))).toEqual([
      "episode_agent",
      "episode_security",
    ]);

    fireEvent.click(screen.getByRole("button", { name: /Rising/i }));
    await waitFor(() => expect(document.querySelectorAll(".discover-card")).toHaveLength(1));
    expect(screen.getByText("hyper-agent 0.2.0")).toBeTruthy();
    expect(screen.queryByText("Freshly exploited edge appliance bug")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: /Security/i }));
    expect(screen.getByText("Freshly exploited edge appliance bug")).toBeTruthy();
  });

  it("opens exact-snapshot episode evidence from a feed card", async () => {
    const transport = new DiscoveryTransport();
    render(<DiscoverApp transport={transport} />);
    await screen.findByText("hyper-agent 0.2.0");

    fireEvent.click(screen.getAllByRole("button", { name: "evidence →" })[0]!);
    await screen.findByText("POINT-IN-TIME EVIDENCE");
    const episodeCall = transport.calls.find((call) => call.path === "/v0/episodes/episode_agent");
    expect(episodeCall?.query.snapshot_id).toBe(snapshot.snapshot_id);
    expect(screen.getByText(/Source count is evidence diversity/)).toBeTruthy();
  });
});
