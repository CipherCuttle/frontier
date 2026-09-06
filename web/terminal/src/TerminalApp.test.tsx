import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type {
  EpisodeEvidenceResponse,
  ExperimentalEpisodeComparisonResponse,
  ExperimentalHistoryResponse,
  ExperimentalOverviewResponse,
  ExperimentalShadowRunResponse,
  ExperimentalStatusResponse,
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

function comparisonResponse(
  episodeId: string,
  overrides: Partial<ExperimentalEpisodeComparisonResponse> = {},
): ExperimentalEpisodeComparisonResponse {
  return {
    as_of: snapshot.as_of,
    authority_state: "EXPERIMENTAL_SHADOW",
    availability: "AVAILABLE",
    baseline_rank: 7,
    baseline_rank_state: "AVAILABLE",
    candidate_components: null,
    candidate_components_state: "UNAVAILABLE",
    candidate_freeze_receipt_id: "freezereceipt_fixture",
    candidate_rank: 3,
    candidate_rank_state: "AVAILABLE",
    control_snapshot_id: "snapshot_control",
    episode_id: episodeId,
    evaluation_receipt_id: "eval_fixture",
    evaluation_receipt_status: "COMPLETE",
    evaluation_state: "AVAILABLE",
    feature_availability: "NO_DATA",
    feature_interpretation: null,
    feature_interpretation_state: "UNAVAILABLE",
    feature_values: [],
    interpretation: "EXPERIMENTAL_SHADOW comparison",
    rank_delta: -4,
    rank_delta_state: "AVAILABLE",
    run_failure_reason: null,
    run_id: "shadowrun_fixture",
    run_status: "RAN",
    schema_version: "experimental-read-response-v0",
    ...overrides,
  };
}

function comparisonNoData(episodeId: string): ExperimentalEpisodeComparisonResponse {
  return comparisonResponse(episodeId, {
    availability: "NO_DATA",
    baseline_rank: null,
    baseline_rank_state: "UNAVAILABLE",
    candidate_rank: null,
    candidate_rank_state: "UNAVAILABLE",
    candidate_freeze_receipt_id: null,
    rank_delta: null,
    rank_delta_state: "UNAVAILABLE",
    run_id: null,
    run_status: null,
    evaluation_receipt_id: null,
    evaluation_receipt_status: null,
    evaluation_state: "NO_DATA",
  });
}

const experimentStatus: ExperimentalStatusResponse = {
  availability: "AVAILABLE",
  authority_state: "EXPERIMENTAL_SHADOW",
  interpretation: "EXPERIMENTAL_SHADOW status surface",
  schema_version: "experiment-status-v0",
  status: {
    experiment_id: "exp_pef_v0",
    candidate_id: "pef_v0",
    candidate_freeze_state: "BOUND",
    candidate_freeze_receipt_id: "freezereceipt_fixture",
    implementation_state: "AVAILABLE",
    implementation_commit: "abc123",
    source_registry_state: "AVAILABLE",
    source_registry_digest: "sha256:registry",
    window_state: "OPEN",
    window_start: "2026-09-05T00:00:00.000000Z",
    latest_boundary_as_of: "2026-09-05T12:00:00.000000Z",
    latest_attempt_status: null,
    latest_run_id: "shadowrun_fixture",
    latest_run_status: "RAN",
    run_state: "AVAILABLE",
    coverage_state: "DEGRADED",
    qualifying_opportunity_counts: [
      {
        anchor_count: 5,
        domain: "vuln_disclosure",
        excluded_count: 0,
        pending_count: 2,
        resolved_negative_count: 0,
        resolved_positive_count: 1,
        unknown_count: 1,
        unresolved_coverage_count: 1,
      },
    ],
    sample_adequacy_thresholds: { minimum_qualifying_domains: 2 },
    domain_evaluation_rows: [
      {
        candidate_positive_surfaced_resolved: 1,
        candidate_precision: "0.500000",
        candidate_surfaced_resolved: 2,
        control_positive_surfaced_resolved: 2,
        control_precision: "1.000000",
        control_surfaced_resolved: 2,
        difference_lower_bound: "-1.000000",
        domain: "vuln_disclosure",
        median_lead_time_advantage_seconds: "3600",
        noninferiority_pass: true,
        qualifies_sample_adequacy: true,
      },
    ],
    candidate_precision: {
      positive_surfaced_resolved: 1,
      precision: "0.500000",
      state: "AVAILABLE",
      surfaced_resolved: 2,
    },
    baseline_precision: {
      positive_surfaced_resolved: 2,
      precision: "1.000000",
      state: "AVAILABLE",
      surfaced_resolved: 2,
    },
    noninferiority: { lower_bound: "-1.000000", margin: "0.100000", state: "PASS" },
    lead_time: {
      baseline_median_lead_time_seconds: null,
      candidate_median_lead_time_seconds: null,
      delta_median_advantage_seconds: "3600",
      state: "AVAILABLE",
    },
    evaluation_receipt_state: "AVAILABLE",
    evaluation_receipt_status: "COMPLETE",
    drift_state: "OK",
  },
};

const experimentHistory: ExperimentalHistoryResponse = {
  availability: "AVAILABLE",
  candidate_id: "pef_v0",
  evaluations: [
    { as_of: snapshot.as_of, evaluation_id: "eval_fixture", status: "COMPLETE" },
  ],
  experiment_id: "exp_pef_v0",
  limit: 20,
  runs: [
    { as_of: snapshot.as_of, run_class: "PROSPECTIVE", run_digest: "sha256:run", run_id: "shadowrun_fixture", status: "RAN" },
  ],
};

class FakeTransport implements FrontierPublicReadTransport {
  readonly calls: Array<{ path: string; query: Record<string, unknown> }> = [];
  experimentalOverviewPayload: ExperimentalOverviewResponse | null = experimentalOverview;
  experimentalStatusPayload: ExperimentalStatusResponse | null = experimentStatus;
  experimentalHistoryPayload: ExperimentalHistoryResponse | null = experimentHistory;
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
      if (path === "/v0/experimental/status") {
        return (this.experimentalStatusPayload ?? { availability: "NO_DATA", status: null }) as T;
      }
      if (path === "/v0/experimental/history") {
        return (this.experimentalHistoryPayload ?? {
          availability: "NO_DATA",
          candidate_id: "pef_v0",
          evaluations: [],
          experiment_id: "exp_pef_v0",
          limit: 0,
          runs: [],
        }) as T;
      }
      if (path.startsWith("/v0/experimental/episodes/")) {
        const episodeId = decodeURIComponent(path.split("/")[4] ?? "");
        return comparisonNoData(episodeId) as T;
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

class ComparisonTransport extends FakeTransport {
  comparisonFactory: ((episodeId: string) => ExperimentalEpisodeComparisonResponse) | null = null;

  override async get<T>(
    path: string,
    query: Record<string, string | number | boolean | null | undefined> = {},
  ): Promise<T> {
    if (path.startsWith("/v0/experimental/episodes/")) {
      const episodeId = decodeURIComponent(path.split("/")[4] ?? "");
      const payload = this.comparisonFactory
        ? this.comparisonFactory(episodeId)
        : comparisonNoData(episodeId);
      this.calls.push({ path, query });
      return payload as T;
    }
    return super.get<T>(path, query);
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

  it("wires WP7 comparisons into real rank deltas with inline, non-hover identity", async () => {
    const transport = new ComparisonTransport();
    transport.comparisonFactory = (episodeId) => comparisonResponse(episodeId);
    render(<TerminalApp transport={transport} />);
    await screen.findByText("#7");
    fireEvent.keyDown(window, { key: "x" });
    await screen.findByText("Rank deltas (baseline RADAR vs candidate)");

    // Server-computed delta rendered verbatim: candidate #3 vs baseline #7.
    expect(screen.getByText("-4")).toBeTruthy();
    expect(screen.getByText("#3")).toBeTruthy();
    // Critical identity is inline in the table, never hover-only.
    expect(screen.getAllByText(/shadowrun_fix/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/freezereceipt_fix/).length).toBeGreaterThanOrEqual(1);
    // The comparison fetch used the bound as_of.
    const comparisonCall = transport.calls.find((call) => call.path.startsWith("/v0/experimental/episodes/"));
    expect(comparisonCall?.query.as_of).toBe(snapshot.as_of);
  });

  it("never reranks baseline rows: candidate data cannot reorder or replace the baseline plane", async () => {
    const transport = new ComparisonTransport();
    // Candidate rank 1 would reorder baseline #7 if the client reranked.
    transport.comparisonFactory = (episodeId) =>
      comparisonResponse(episodeId, { candidate_rank: 1, rank_delta: -6 });
    render(<TerminalApp transport={transport} />);
    await screen.findByText("#7");
    fireEvent.keyDown(window, { key: "x" });
    await screen.findByText("Rank deltas (baseline RADAR vs candidate)");

    // Baseline rank stays #7 and delta is the server's own value.
    const rankCells = screen.getAllByText("#7");
    expect(rankCells.length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("-6")).toBeTruthy();
    // Leaving the experimental lens restores the untouched baseline table.
    fireEvent.keyDown(window, { key: "x" });
    await screen.findByText("RADAR / episode activity");
    expect(screen.getByText("#7")).toBeTruthy();
    expect(screen.queryByText("Rank deltas (baseline RADAR vs candidate)")).toBeNull();
  });

  it("renders UNKNOWN ranks and UNAVAILABLE deltas distinctly (never coerced to 0)", async () => {
    const transport = new ComparisonTransport();
    transport.comparisonFactory = (episodeId) =>
      comparisonResponse(episodeId, {
        candidate_rank: null,
        candidate_rank_state: "UNAVAILABLE",
        rank_delta: null,
        rank_delta_state: "UNAVAILABLE",
      });
    render(<TerminalApp transport={transport} />);
    await screen.findByText("#7");
    fireEvent.keyDown(window, { key: "x" });
    await screen.findByText("Rank deltas (baseline RADAR vs candidate)");
    // Candidate rank column: UNAVAILABLE (capability absent), delta: UNAVAILABLE, never "0".
    expect(screen.getAllByText("UNAVAILABLE").length).toBeGreaterThanOrEqual(2);
    expect(screen.queryByText("±0")).toBeNull();
    expect(screen.queryByText(/^#?0$/)).toBeNull();
  });

  it("renders failed comparisons as UNKNOWN rather than fabricated deltas", async () => {
    const failing = new ComparisonTransport();
    // Every per-episode comparison fetch fails: nothing may be fabricated.
    failing.comparisonFactory = () => {
      throw new Error("comparison fetch failed");
    };
    render(<TerminalApp transport={failing} />);
    await screen.findByText("#7");
    fireEvent.keyDown(window, { key: "x" });
    await screen.findByText("Rank deltas (baseline RADAR vs candidate)");
    // Fetch failed → candidate rank UNKNOWN, delta UNAVAILABLE; failure is visible.
    expect(screen.getByText("comparison:episode_fixture")).toBeTruthy();
  });

  it("discards comparison responses bound to a superseded run identity", async () => {
    const staleTransport = new ComparisonTransport();
    staleTransport.comparisonFactory = (episodeId) =>
      comparisonResponse(episodeId, { run_id: "run_superseded" });
    render(<TerminalApp transport={staleTransport} />);
    await screen.findByText("#7");
    fireEvent.keyDown(window, { key: "x" });
    await screen.findByText("Rank deltas (baseline RADAR vs candidate)");
    // The stale comparison is discarded (binding run=shadowrun_fixture), so the
    // row shows UNKNOWN rank with the failure surfaced — not the stale delta.
    expect(screen.getByText("comparison:episode_fixture")).toBeTruthy();
    expect(screen.queryByText("-4")).toBeNull();
  });

  it("renders the experiment command center with the explicit state matrix and inline identity", async () => {
    const transport = new FakeTransport();
    render(<TerminalApp transport={transport} />);
    await screen.findByText("#7");
    fireEvent.keyDown(window, { key: "e" });
    await screen.findByText("Experiment command center");

    for (const label of ["FREEZE", "WINDOW", "SAMPLES", "DOMAINS", "PRECISION", "LEAD", "DRIFT", "HEALTH"]) {
      expect(screen.getByText(label)).toBeTruthy();
    }
    expect(screen.getAllByText("DEGRADED").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("OPEN")).toBeTruthy();
    expect(screen.getByText(/COMPLETE/)).toBeTruthy();
    // Critical identity inline: freeze receipt id, run id, experiment id.
    expect(screen.getByText("freezereceipt_fixture")).toBeTruthy();
    expect(screen.getByText("exp_pef_v0")).toBeTruthy();
    expect(screen.getAllByText(/shadowrun_fixture|shadowrun_fix/).length).toBeGreaterThanOrEqual(1);
    // Persistent shadow labeling on the command-center view.
    expect(screen.getAllByText("EXPERIMENTAL SHADOW").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/not baseline authority/i).length).toBeGreaterThanOrEqual(1);
  });

  it("renders preregistered evaluation statuses verbatim: FAILED / DEGRADED / INSUFFICIENT_SAMPLE / INVALID_DRIFT", async () => {
    const transport = new FakeTransport();
    transport.experimentalStatusPayload = {
      ...experimentStatus,
      status: {
        ...experimentStatus.status,
        evaluation_receipt_status: "INSUFFICIENT_SAMPLE",
        evaluation_receipt_state: "AVAILABLE",
        drift_state: "INVALID_DRIFT",
        run_state: "FAILED",
        latest_run_status: "FAILED",
        coverage_state: "DEGRADED",
        candidate_precision: {
          positive_surfaced_resolved: null,
          precision: null,
          state: "UNAVAILABLE",
          surfaced_resolved: null,
        },
      },
    } as ExperimentalStatusResponse;
    render(<TerminalApp transport={transport} />);
    await screen.findByText("#7");
    fireEvent.keyDown(window, { key: "e" });
    await screen.findByText("Experiment command center");

    expect(screen.getByText(/INSUFFICIENT_SAMPLE/)).toBeTruthy();
    expect(screen.getAllByText(/INVALID_DRIFT/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/FAILED/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("DEGRADED").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("UNAVAILABLE").length).toBeGreaterThanOrEqual(1);
  });

  it("renders a failed status fetch as explicit UNKNOWN without fabricating a healthy state", async () => {
    const transport = new FakeTransport();
    transport.experimentalFails = true;
    render(<TerminalApp transport={transport} />);
    await screen.findByText("#7");
    fireEvent.keyDown(window, { key: "e" });
    await screen.findByText("EXPERIMENT STATUS UNKNOWN");
    expect(screen.getByText(/experimental repository unavailable/)).toBeTruthy();
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
    transport.experimentalHistoryPayload = null;
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

  it("documents the experiment command center in keyboard help", async () => {
    const transport = new FakeTransport();
    render(<TerminalApp transport={transport} />);
    await screen.findByText("#7");
    fireEvent.keyDown(window, { key: "?" });
    await screen.findByText("Command map");
    expect(screen.getByText("experiment command center (WP8 status surface)")).toBeTruthy();
    expect(screen.getByText("EXPERIMENTAL shadow comparison lens (toggle)")).toBeTruthy();
  });
});
