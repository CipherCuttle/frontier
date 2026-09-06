import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type {
  EpisodeEvidenceResponse,
  ExperimentalOverviewResponse,
  ExperimentalShadowRunResponse,
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

const experimentalShadowRun: ExperimentalShadowRunResponse = {
  algorithm_version: "pef-v0",
  as_of: snapshot.as_of,
  authority_state: "EXPERIMENTAL_SHADOW",
  candidate_artifact_id: "pefart_fixture",
  candidate_freeze_receipt_id: "freezereceipt_fixture",
  candidate_id: "pef_v0",
  candidate_output_digest: "sha256:cand",
  configuration_digest: "sha256:cfg",
  control_receipt_id: "receipt_control",
  control_snapshot_id: "snapshot_control",
  episode_universe_digest: "sha256:universe",
  experiment_id: "exp_pef_v0",
  failure_reason: null,
  generated_at: "2026-09-05T12:00:01.000000Z",
  run_digest: "sha256:run",
  run_id: "shadowrun_fixture",
  schema_version: "experimental-read-response-v0",
  status: "RAN",
};

const experimentalOverview: ExperimentalOverviewResponse = {
  analysis_artifacts: {},
  as_of: snapshot.as_of,
  authority_state: "EXPERIMENTAL_SHADOW",
  availability: {
    shadow_run: "AVAILABLE",
    pef_artifact: "NO_DATA",
    evaluation_receipt: "NO_DATA",
    feature_batch: "NO_DATA",
  },
  candidate_id: "pef_v0",
  configuration_digest: "sha256:cfg",
  experiment_id: "exp_pef_v0",
  generated_at: "2026-09-05T12:00:01.000000Z",
  latest_evaluation_receipt: null,
  latest_feature_batch: null,
  latest_pef_artifact: null,
  latest_shadow_run: experimentalShadowRun,
  interpretation: "EXPERIMENTAL_SHADOW read surface",
  schema_version: "experimental-read-response-v0",
};

const experimentalNoDataOverview: ExperimentalOverviewResponse = {
  ...experimentalOverview,
  availability: {
    shadow_run: "NO_DATA",
    pef_artifact: "NO_DATA",
    evaluation_receipt: "NO_DATA",
    feature_batch: "NO_DATA",
  },
  latest_shadow_run: null,
};

class FakeTransport implements FrontierPublicReadTransport {
  readonly calls: Array<{ path: string; query: Record<string, unknown> }> = [];
  experimentalOverviewPayload: ExperimentalOverviewResponse | null = experimentalOverview;
  experimentalFails = false;

  async get<T>(
    path: string,
    query: Record<string, string | number | boolean | null | undefined> = {},
  ): Promise<T> {
    this.calls.push({ path, query });
    if (path.startsWith("/v0/experimental/")) {
      if (this.experimentalFails) throw new Error("experimental repository unavailable");
      if (path === "/v0/experimental/overview") {
        return (this.experimentalOverviewPayload ?? { availability: "NO_DATA", latest: null }) as T;
      }
      return { availability: "NO_DATA", latest: null } as T;
    }
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

  it("renders the EXPERIMENTAL lens labelled shadow with rank deltas and UNKNOWN candidate ranks", async () => {
    const transport = new FakeTransport();
    render(<TerminalApp transport={transport} />);
    await screen.findByText("#7");
    fireEvent.keyDown(window, { key: "x" });
    await screen.findByText("Rank deltas (baseline RADAR vs candidate)");

    expect(screen.getAllByText("EXPERIMENTAL SHADOW").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("Shadow run status")).toBeTruthy();
    expect(screen.getByText("Feature explanations")).toBeTruthy();
    expect(screen.getByText("Experiment history")).toBeTruthy();

    const overviewCall = transport.calls.find((call) => call.path === "/v0/experimental/overview");
    expect(overviewCall?.query.as_of).toBe(snapshot.as_of);
    const radarCall = transport.calls.find(
      (call) => call.path === "/v0/radar" && call.query.snapshot_id !== undefined,
    );
    expect(radarCall?.query.snapshot_id).toBe(snapshot.snapshot_id);

    expect(screen.getByText("#7")).toBeTruthy();
    expect(screen.getAllByText("UNKNOWN").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("persistence")).toBeTruthy();
    expect(screen.getAllByText("shadowrun_fixture").length).toBeGreaterThanOrEqual(1);
    expect(screen.queryByText(/independently confirmed/i)).toBeNull();
    expect(screen.queryByText(/factual confidence/i)).toBeNull();
  });

  it("toggling EXPERIMENTAL preserves baseline state and returns without refetch", async () => {
    const transport = new FakeTransport();
    render(<TerminalApp transport={transport} />);
    await screen.findByText("#7");
    fireEvent.keyDown(window, { key: "x" });
    await screen.findByText("Rank deltas (baseline RADAR vs candidate)");
    fireEvent.keyDown(window, { key: "x" });
    await screen.findByText("RADAR / episode activity");
    expect(screen.queryByText("Rank deltas (baseline RADAR vs candidate)")).toBeNull();
    expect(screen.getByText(/LOCAL FILTER/)).toBeTruthy();
    const radarCalls = transport.calls.filter((call) => call.path === "/v0/radar");
    expect(radarCalls).toHaveLength(2);
  });

  it("shows an explicit empty EXPERIMENTAL panel when no shadow data exists (NO_DATA)", async () => {
    const transport = new FakeTransport();
    transport.experimentalOverviewPayload = experimentalNoDataOverview;
    render(<TerminalApp transport={transport} />);
    await screen.findByText("#7");
    fireEvent.keyDown(window, { key: "x" });
    await screen.findByText("NO EXPERIMENTAL DATA for this as_of.");
    expect(screen.getAllByText("NO_DATA").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText(/NO SHADOW RUN DATA/)).toBeTruthy();
  });

  it("renders experimental fetch failures as explicit errors without breaking baseline lenses", async () => {
    const transport = new FakeTransport();
    transport.experimentalFails = true;
    render(<TerminalApp transport={transport} />);
    await screen.findByText("#7");
    fireEvent.keyDown(window, { key: "x" });
    await screen.findByText("EXPERIMENTAL SHADOW UNAVAILABLE");
    expect(screen.getByText("Baseline lenses remain available and unchanged.")).toBeTruthy();
    fireEvent.keyDown(window, { key: "2" });
    await waitFor(() => expect(transport.calls.some((call) => call.path === "/v0/now")).toBe(true));
    await screen.findByText("NOW / episode activity");
    expect(screen.getByText("#7")).toBeTruthy();
  });
});
