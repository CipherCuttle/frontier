import { describe, expect, it } from "vitest";
import type {
  EpisodeResponse,
  ExperimentalEpisodeComparisonResponse,
  ExperimentalHistoryResponse,
  ExperimentalOverviewResponse,
  ExperimentalShadowRunResponse,
  ExperimentalStatusResponse,
} from "./api";
import {
  bindingFromOverview,
  buildExperimentCommandCenter,
  buildExperimentHistory,
  buildFeatureExplanations,
  buildRankDeltasFromComparisons,
  buildWarRoomHistory,
  computeRankDeltas,
  displayRankDelta,
  EXPERIMENTAL_LENS_LABEL,
  EXPERIMENTAL_LENS_NOTE,
  experimentalStateKind,
  filterEpisodes,
  resolveKeyboardCommand,
  resolveSectionAvailability,
} from "./model";

function episode(rank: number, sourceId = `source-${rank}`): EpisodeResponse {
  return {
    acceleration_6h: rank,
    age_seconds: rank,
    backfill_evidence_count: 0,
    confirmation: "UNAVAILABLE",
    episode_id: `episode-${String(rank).padStart(3, "0")}`,
    evidence_count_total: 1,
    evidence_root_diversity: null,
    first_observed_at: "2026-09-05T12:00:00.000000Z",
    last_observed_at: "2026-09-05T12:00:00.000000Z",
    mentions_1h: 1,
    mentions_24h: 1,
    mentions_6h: 1,
    observation_ids: [`obs-${rank}`],
    preprevious_6h: 0,
    previous_6h: 0,
    prospective_evidence_count: 1,
    rank,
    recovered_backlog_evidence_count: 0,
    signal_roles: [rank % 2 === 0 ? "ATTENTION" : "PRIMARY_EMISSION"],
    source_count: 1,
    source_ids: [sourceId],
    source_role_diversity: 1,
    velocity_6h_delta: rank,
  };
}

function comparison(
  episodeId: string,
  overrides: Partial<ExperimentalEpisodeComparisonResponse> = {},
): ExperimentalEpisodeComparisonResponse {
  return {
    as_of: "2026-09-05T12:00:00.000000Z",
    authority_state: "EXPERIMENTAL_SHADOW",
    availability: "AVAILABLE",
    baseline_rank: 1,
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
    rank_delta: 2,
    rank_delta_state: "AVAILABLE",
    run_failure_reason: null,
    run_id: "shadowrun_fixture",
    run_status: "RAN",
    schema_version: "experimental-read-response-v0",
    ...overrides,
  };
}

describe("terminal semantic helpers", () => {
  it("preserves baseline rank and relative order through local filtering", () => {
    const input = [episode(1, "alpha"), episode(2, "beta"), episode(3, "alpha-secondary")];
    const filtered = filterEpisodes(input, "alpha");
    expect(filtered.map((item) => item.rank)).toEqual([1, 3]);
    expect(input.map((item) => item.rank)).toEqual([1, 2, 3]);
  });

  it("preserves all 500 deterministic rows without semantic reordering", () => {
    const input = Array.from({ length: 500 }, (_, index) => episode(index + 1));
    const output = filterEpisodes(input, "");
    expect(output).toHaveLength(500);
    expect(output.map((item) => item.rank)).toEqual(input.map((item) => item.rank));
  });

  it("maps the frozen keyboard contract including the experimental lens key", () => {
    expect(resolveKeyboardCommand("1", document.body)).toEqual({ kind: "lens", lens: "RADAR" });
    expect(resolveKeyboardCommand("2", document.body)).toEqual({ kind: "lens", lens: "NOW" });
    expect(resolveKeyboardCommand("3", document.body)).toEqual({ kind: "lens", lens: "TRENDING" });
    expect(resolveKeyboardCommand("x", document.body)).toEqual({ kind: "lens", lens: "EXPERIMENTAL" });
    expect(resolveKeyboardCommand("X", document.body)).toEqual({ kind: "lens", lens: "EXPERIMENTAL" });
    expect(resolveKeyboardCommand("e", document.body)).toEqual({ kind: "panel", panel: "experiment" });
    expect(resolveKeyboardCommand("E", document.body)).toEqual({ kind: "panel", panel: "experiment" });
    expect(resolveKeyboardCommand("j", document.body)).toEqual({ kind: "next" });
    expect(resolveKeyboardCommand("k", document.body)).toEqual({ kind: "previous" });
    expect(resolveKeyboardCommand("h", document.body)).toEqual({ kind: "panel", panel: "health" });
    expect(resolveKeyboardCommand("a", document.body)).toEqual({ kind: "panel", panel: "audit" });
    expect(resolveKeyboardCommand("?", document.body)).toEqual({ kind: "panel", panel: "help" });
  });

  it("does not steal keyboard commands from editable targets", () => {
    const input = document.createElement("input");
    expect(resolveKeyboardCommand("1", input)).toBeNull();
    expect(resolveKeyboardCommand("j", input)).toBeNull();
    expect(resolveKeyboardCommand("x", input)).toBeNull();
    expect(resolveKeyboardCommand("e", input)).toBeNull();
    expect(resolveKeyboardCommand("Escape", input)).toEqual({ kind: "escape" });
  });
});

describe("EXPERIMENTAL lens model (slice H)", () => {
  it("computes hand-checked baseline-vs-candidate rank deltas and UNKNOWN gaps", () => {
    const baseline = [episode(1), episode(2), episode(3)];
    const candidateRanks = new Map<string, number>([
      ["episode-001", 3],
      ["episode-002", 1],
    ]);
    const deltas = computeRankDeltas(baseline, candidateRanks);
    expect(deltas).toHaveLength(3);
    expect(deltas[0]).toMatchObject({ episodeId: "episode-001", baselineRank: 1, experimentalRank: 3, delta: 2 });
    expect(deltas[1]).toMatchObject({ episodeId: "episode-002", baselineRank: 2, experimentalRank: 1, delta: -1 });
    expect(deltas[2]).toMatchObject({ episodeId: "episode-003", baselineRank: 3, experimentalRank: null });
    expect(deltas.at(2)?.delta).toBeNull();
    expect(deltas.at(2)?.deltaState).toBe("UNAVAILABLE");
    expect(displayRankDelta(2)).toBe("+2");
    expect(displayRankDelta(-1)).toBe("-1");
    expect(displayRankDelta(0)).toBe("±0");
  });

  it("never invents candidate ranks when the summary plane exposes none", () => {
    const baseline = [episode(1), episode(2)];
    const deltas = computeRankDeltas(baseline, null);
    expect(deltas.every((delta) => delta.experimentalRank === null && delta.delta === null)).toBe(true);
    expect(deltas.every((delta) => delta.deltaState === "UNAVAILABLE")).toBe(true);
    expect(deltas.map((delta) => delta.baselineRank)).toEqual([1, 2]);
    expect(displayRankDelta(null)).toBe("UNKNOWN");
    // UNKNOWN candidate ranks render the delta UNAVAILABLE — never a coerced 0.
    expect(displayRankDelta(null, "UNAVAILABLE")).toBe("UNAVAILABLE");
    expect(displayRankDelta(null, "INSUFFICIENT_SAMPLE")).toBe("INSUFFICIENT_SAMPLE");
    expect(displayRankDelta(null, "AVAILABLE")).toBe("UNKNOWN");
  });

  it("builds deltas from the WP7 comparison surface without client-side delta math", () => {
    const baseline = [episode(1), episode(2), episode(3)];
    const comparisons = new Map<string, ExperimentalEpisodeComparisonResponse>([
      ["episode-001", comparison("episode-001", { candidate_rank: 3, rank_delta: 2 })],
      [
        "episode-002",
        comparison("episode-002", {
          candidate_rank: null,
          candidate_rank_state: "UNAVAILABLE",
          rank_delta: null,
          rank_delta_state: "UNAVAILABLE",
        }),
      ],
    ]);
    const deltas = buildRankDeltasFromComparisons(baseline, comparisons);
    expect(deltas[0]).toMatchObject({
      episodeId: "episode-001",
      baselineRank: 1,
      experimentalRank: 3,
      experimentalRankState: "AVAILABLE",
      delta: 2,
      deltaState: "AVAILABLE",
    });
    // Candidate rank missing on the read plane: delta UNAVAILABLE, not 0.
    expect(deltas[1]).toMatchObject({
      episodeId: "episode-002",
      experimentalRank: null,
      experimentalRankState: "UNAVAILABLE",
      delta: null,
      deltaState: "UNAVAILABLE",
    });
    expect(displayRankDelta(deltas.at(1)?.delta ?? null, deltas.at(1)?.deltaState)).toBe("UNAVAILABLE");
    // Baseline rank always comes from the baseline plane, not the candidate data.
    expect(deltas.map((delta) => delta.baselineRank)).toEqual([1, 2, 3]);
    // A comparison fetch that failed entirely renders UNKNOWN rank / UNAVAILABLE delta.
    expect(buildRankDeltasFromComparisons(baseline, new Map())[2]).toMatchObject({
      episodeId: "episode-003",
      experimentalRank: null,
      experimentalRankState: "UNKNOWN",
      delta: null,
      deltaState: "UNAVAILABLE",
    });
    expect(displayRankDelta(null, "UNKNOWN")).toBe("UNKNOWN");
  });

  it("resolves section availability fail-closed to UNKNOWN (R4)", () => {
    const availability = { shadow_run: "AVAILABLE", pef_artifact: "NO_DATA" };
    expect(resolveSectionAvailability(availability, "shadow_run")).toBe("AVAILABLE");
    expect(resolveSectionAvailability(availability, "pef_artifact")).toBe("NO_DATA");
    expect(resolveSectionAvailability(availability, "evaluation_receipt")).toBe("UNKNOWN");
    expect(resolveSectionAvailability(availability, "feature_batch")).toBe("UNKNOWN");
    expect(resolveSectionAvailability(null, "shadow_run")).toBe("UNKNOWN");
    expect(resolveSectionAvailability({ shadow_run: "WEIRD" }, "shadow_run")).toBe("UNKNOWN");
  });

  it("classifies the explicit war-room state matrix distinctly and fail-closed", () => {
    expect(experimentalStateKind("UNKNOWN")).toBe("UNKNOWN");
    expect(experimentalStateKind("NO_DATA")).toBe("NO_DATA");
    expect(experimentalStateKind("UNAVAILABLE")).toBe("UNAVAILABLE");
    // Preregistered evaluation statuses render verbatim.
    expect(experimentalStateKind("FAILED")).toBe("FAILED");
    expect(experimentalStateKind("DEGRADED")).toBe("DEGRADED");
    expect(experimentalStateKind("INSUFFICIENT_SAMPLE")).toBe("INSUFFICIENT_SAMPLE");
    expect(experimentalStateKind("INVALID_DRIFT")).toBe("INVALID_DRIFT");
    expect(experimentalStateKind("COMPLETE")).toBe("COMPLETE");
    // Unknown or missing strings fail closed to UNKNOWN — never to AVAILABLE.
    expect(experimentalStateKind("SOME_NOVEL_STATUS")).toBe("UNKNOWN");
    expect(experimentalStateKind(null)).toBe("UNKNOWN");
    expect(experimentalStateKind(undefined)).toBe("UNKNOWN");
  });

  it("labels the experimental lens and never escalates its epistemic authority (R7)", () => {
    expect(EXPERIMENTAL_LENS_LABEL).toBe("EXPERIMENTAL SHADOW");
    expect(EXPERIMENTAL_LENS_NOTE).toMatch(/not baseline authority/i);
    expect(EXPERIMENTAL_LENS_NOTE).toMatch(/not truth/i);
    expect(EXPERIMENTAL_LENS_NOTE).toMatch(/hypothesis-level/i);
  });

  it("builds experiment history with explicit availability per section", () => {
    const shadowRun: ExperimentalShadowRunResponse = {
      algorithm_version: "pef-v0",
      as_of: "2026-09-05T12:00:00.000000Z",
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
    const overview: ExperimentalOverviewResponse = {
      analysis_artifacts: {},
      as_of: "2026-09-05T12:00:00.000000Z",
      availability: {
        shadow_run: "AVAILABLE",
        pef_artifact: "NO_DATA",
        evaluation_receipt: "NO_DATA",
        feature_batch: "WEIRD_STATE",
      },
      candidate_id: "pef_v0",
      configuration_digest: "sha256:cfg",
      experiment_id: "exp_pef_v0",
      generated_at: "2026-09-05T12:00:01.000000Z",
      latest_evaluation_receipt: null,
      latest_feature_batch: null,
      latest_pef_artifact: null,
      latest_shadow_run: shadowRun,
    };
    const history = buildExperimentHistory(overview);
    expect(history.map((entry) => entry.section)).toEqual([
      "shadow_run",
      "pef_artifact",
      "evaluation_receipt",
      "feature_batch",
    ]);
    expect(history[0]).toMatchObject({ availability: "AVAILABLE", id: "shadowrun_fixture", status: "RAN" });
    expect(history[1]).toMatchObject({ availability: "NO_DATA", id: null, status: null });
    expect(history[3]).toMatchObject({ availability: "UNKNOWN" });
    expect(buildExperimentHistory(null)).toEqual([]);
  });

  it("renders feature explanations with UNKNOWN values and no scalar scores (R4, R7)", () => {
    const noBatch = buildFeatureExplanations(null);
    expect(noBatch).toHaveLength(10);
    for (const feature of noBatch) {
      expect(feature.value).toBe("UNKNOWN");
      expect(feature.status).toBe("UNKNOWN");
      expect(feature.definition.length).toBeGreaterThan(0);
    }
    const names = noBatch.map((feature) => feature.name);
    expect(names).toContain("persistence");
    expect(names).toContain("discovery_lag");
    const ranBatch = buildFeatureExplanations({
      algorithm_version: "transparent-advanced-features-v0",
      as_of: "2026-09-05T12:00:00.000000Z",
      authority_state: "EXPERIMENTAL_SHADOW",
      batch_digest: "sha256:batch",
      batch_id: "featurebatch_fixture",
      configuration_digest: "sha256:cfg",
      control_receipt_id: "receipt_control",
      control_snapshot_id: "snapshot_control",
      episode_universe_digest: "sha256:universe",
      generated_at: "2026-09-05T12:00:01.000000Z",
      schema_version: "advanced-features-v0",
      status: "RAN",
      vector_count: 42,
    });
    for (const feature of ranBatch) {
      expect(feature.value).toBe("UNKNOWN (values not exposed; 42 vectors in batch)");
      expect(feature.status).toBe("UNKNOWN");
    }
  });
});

describe("WP8 experiment war-room model", () => {
  it("derives the experiment identity binding from the overview, never guessing", () => {
    const shadowRun: ExperimentalShadowRunResponse = {
      algorithm_version: "pef-v0",
      as_of: "2026-09-05T12:00:00.000000Z",
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
    expect(
      bindingFromOverview({
        ...({} as ExperimentalOverviewResponse),
        latest_shadow_run: shadowRun,
      }),
    ).toEqual({
      runId: "shadowrun_fixture",
      freezeReceiptId: "freezereceipt_fixture",
      evaluationReceiptId: null,
    });
    expect(bindingFromOverview(null)).toEqual({
      runId: null,
      freezeReceiptId: null,
      evaluationReceiptId: null,
    });
  });

  it("maps the WP7 history surface newest-first without reordering", () => {
    const history: ExperimentalHistoryResponse = {
      availability: "AVAILABLE",
      candidate_id: "pef_v0",
      evaluations: [
        { as_of: "2026-09-05T12:30:00.000000Z", evaluation_id: "eval_new", status: "INSUFFICIENT_SAMPLE" },
        { as_of: "2026-09-05T12:00:00.000000Z", evaluation_id: "eval_old", status: "FAILED" },
      ],
      experiment_id: "exp_pef_v0",
      limit: 20,
      runs: [
        { as_of: "2026-09-05T12:30:00.000000Z", run_class: "PROSPECTIVE", run_digest: "sha256:new", run_id: "run_new", status: "RAN" },
        { as_of: "2026-09-05T12:00:00.000000Z", run_class: null, run_digest: "sha256:old", run_id: "run_old", status: "FAILED" },
      ],
    };
    const entries = buildWarRoomHistory(history);
    expect(entries.map((entry) => entry.id)).toEqual(["run_new", "run_old", "eval_new", "eval_old"]);
    expect(entries[0]).toMatchObject({ kind: "run", status: "RAN", runClass: "PROSPECTIVE" });
    expect(entries[3]).toMatchObject({ kind: "evaluation", status: "FAILED", runClass: null });
    expect(buildWarRoomHistory(null)).toEqual([]);
  });

  it("parses the WP7 status surface into the explicit command-center matrix", () => {
    const status: ExperimentalStatusResponse = {
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
    const center = buildExperimentCommandCenter(status);
    expect(center.availability).toBe("AVAILABLE");
    expect(center.experimentId).toBe("exp_pef_v0");
    expect(center.freeze).toMatchObject({
      state: "BOUND",
      receiptId: "freezereceipt_fixture",
      implementationState: "AVAILABLE",
      sourceRegistryState: "AVAILABLE",
    });
    expect(center.window).toMatchObject({ state: "OPEN", start: "2026-09-05T00:00:00.000000Z" });
    expect(center.run).toMatchObject({ state: "AVAILABLE", runId: "shadowrun_fixture" });
    expect(center.health.coverageState).toBe("DEGRADED");
    expect(center.samples.qualifying).toHaveLength(1);
    expect(center.samples.thresholds).toEqual({ minimum_qualifying_domains: 2 });
    expect(center.domains).toHaveLength(1);
    expect(center.domains[0]).toMatchObject({
      domain: "vuln_disclosure",
      candidatePrecision: "0.500000",
      noninferiorityPass: true,
      qualifiesSampleAdequacy: true,
    });
    expect(center.precision.candidate).toMatchObject({ state: "AVAILABLE", precision: "0.500000", surfacedResolved: 2 });
    expect(center.precision.baseline).toMatchObject({ state: "AVAILABLE", precision: "1.000000" });
    expect(center.lead).toEqual({ state: "AVAILABLE", deltaSeconds: "3600" });
    expect(center.drift.state).toBe("OK");
    expect(center.noninferiority).toMatchObject({ state: "PASS", lowerBound: "-1.000000", margin: "0.100000" });
    expect(center.evaluation).toEqual({ state: "AVAILABLE", status: "COMPLETE" });
  });

  it("degrades every command-center cell to explicit UNKNOWN without a status surface", () => {
    for (const response of [null, { availability: "NO_DATA", status: null } as ExperimentalStatusResponse]) {
      const center = buildExperimentCommandCenter(response);
      expect(center.availability).toBe(response === null ? "UNKNOWN" : "NO_DATA");
      expect(center.experimentId).toBeNull();
      expect(center.freeze).toMatchObject({ state: "UNKNOWN", receiptId: null });
      expect(center.window).toMatchObject({ state: "UNKNOWN", start: null });
      expect(center.run).toMatchObject({ state: "UNKNOWN", runId: null });
      expect(center.health.coverageState).toBe("UNKNOWN");
      expect(center.samples).toMatchObject({ qualifying: [], thresholds: null });
      expect(center.domains).toEqual([]);
      expect(center.precision.candidate).toMatchObject({ state: "UNKNOWN", precision: null });
      expect(center.precision.baseline).toMatchObject({ state: "UNKNOWN", precision: null });
      expect(center.lead).toEqual({ state: "UNKNOWN", deltaSeconds: null });
      expect(center.drift.state).toBe("UNKNOWN");
      expect(center.noninferiority).toMatchObject({ state: "UNKNOWN", lowerBound: null });
      expect(center.evaluation).toMatchObject({ state: "UNKNOWN", status: null });
    }
  });
});
