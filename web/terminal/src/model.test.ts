import { describe, expect, it } from "vitest";
import type {
  EpisodeResponse,
  ExperimentalOverviewResponse,
  ExperimentalShadowRunResponse,
} from "./api";
import {
  buildExperimentHistory,
  buildFeatureExplanations,
  computeRankDeltas,
  displayRankDelta,
  EXPERIMENTAL_LENS_LABEL,
  EXPERIMENTAL_LENS_NOTE,
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
    expect(deltas[0]).toEqual({ episodeId: "episode-001", baselineRank: 1, experimentalRank: 3, delta: 2 });
    expect(deltas[1]).toEqual({ episodeId: "episode-002", baselineRank: 2, experimentalRank: 1, delta: -1 });
    expect(deltas[2]).toEqual({ episodeId: "episode-003", baselineRank: 3, experimentalRank: null, delta: null });
    expect(displayRankDelta(2)).toBe("+2");
    expect(displayRankDelta(-1)).toBe("-1");
    expect(displayRankDelta(0)).toBe("±0");
  });

  it("never invents candidate ranks when the summary plane exposes none", () => {
    const baseline = [episode(1), episode(2)];
    const deltas = computeRankDeltas(baseline, null);
    expect(deltas.every((delta) => delta.experimentalRank === null && delta.delta === null)).toBe(true);
    expect(deltas.map((delta) => delta.baselineRank)).toEqual([1, 2]);
    expect(displayRankDelta(null)).toBe("UNKNOWN");
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
