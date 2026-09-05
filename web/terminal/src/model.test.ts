import { describe, expect, it } from "vitest";
import type { EpisodeResponse } from "./api";
import { filterEpisodes, resolveKeyboardCommand } from "./model";

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

  it("maps the frozen keyboard contract", () => {
    expect(resolveKeyboardCommand("1", document.body)).toEqual({ kind: "lens", lens: "RADAR" });
    expect(resolveKeyboardCommand("2", document.body)).toEqual({ kind: "lens", lens: "NOW" });
    expect(resolveKeyboardCommand("3", document.body)).toEqual({ kind: "lens", lens: "TRENDING" });
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
    expect(resolveKeyboardCommand("Escape", input)).toEqual({ kind: "escape" });
  });
});
