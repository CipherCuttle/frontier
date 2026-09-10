import { describe, expect, it } from "vitest";
import type {
  EpisodeEvidenceResponse,
  EpisodeResponse,
  ObservationEvidenceResponse,
} from "../../../clients/typescript/src/generated/public_read_v0";
import {
  buildDiscoveryEvidenceItem,
  buildDiscoveryGroup,
  filterDiscoveryGroups,
  formatDiscoveryAge,
} from "./discover";

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
    mentions_1h: 0,
    mentions_24h: 1,
    mentions_6h: 1,
    observation_ids: [`obs_${rank}`],
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

function observation(
  id: string,
  sourceId: string,
  payload: Record<string, unknown>,
): ObservationEvidenceResponse {
  return {
    canonicalization_version: "frontier-canonical-json-v1",
    collection_occurrences: [],
    content_digest: "sha256:content",
    effective_at: null,
    fetch_digest: "sha256:fetch",
    kind: "ARTIFACT",
    observation_id: id,
    observed_at: "2026-09-10T17:55:00.000000Z",
    payload,
    relations: [],
    retrieved_at: "2026-09-10T17:55:00.000000Z",
    schema_version: "observation-v1",
    source_id: sourceId,
    source_item_key: id,
    source_published_at: null,
  };
}

function evidenceResponse(
  item: EpisodeResponse,
  observations: ObservationEvidenceResponse[],
): EpisodeEvidenceResponse {
  return {
    episode: item,
    generated_at: "2026-09-10T18:00:02.000000Z",
    observations,
    snapshot,
  };
}

describe("DISCOVER feed presentation model", () => {
  it("keeps human-readable text attached to evidence items, not episode identity", () => {
    const item = episode(1, "episode_agent", {
      evidence_count_total: 2,
      observation_ids: ["obs_package", "obs_attention"],
    });
    const packageObservation = observation("obs_package", "pypi.updates", {
      canonical_url: "https://pypi.org/project/hyper-agent/0.2.0/",
      name: "hyper-agent",
      version: "0.2.0",
      source_metadata: { description: "Agent runtime with local tools" },
    });
    const attentionObservation = observation("obs_attention", "hn.frontpage", {
      canonical_url: "https://news.ycombinator.com/item?id=123",
      title: "Show HN: hyper-agent",
    });

    const group = buildDiscoveryGroup(
      item,
      evidenceResponse(item, [packageObservation, attentionObservation]),
    );

    expect(group.episode.episode_id).toBe("episode_agent");
    expect(group.evidence.map((entry) => entry.title)).toEqual([
      "hyper-agent 0.2.0",
      "Show HN: hyper-agent",
    ]);
    expect(filterDiscoveryGroups([group], "ALL", "local tools")).toEqual([group]);
  });

  it("rejects unsafe evidence links instead of rendering arbitrary schemes", () => {
    const item = buildDiscoveryEvidenceItem(
      observation("obs_unsafe", "hn.frontpage", {
        canonical_url: "javascript:alert(1)",
        title: "Unsafe link fixture",
      }),
    );

    expect(item.title).toBe("Unsafe link fixture");
    expect(item.url).toBeNull();
  });

  it("fails closed when evidence response episode identity disagrees", () => {
    const expected = episode(1, "episode_expected");
    const wrong = episode(1, "episode_wrong");

    expect(() => buildDiscoveryGroup(expected, evidenceResponse(wrong, []))).toThrow(
      "episode identity mismatch",
    );
  });

  it("filters lanes without changing baseline order", () => {
    const groups = [
      buildDiscoveryGroup(
        episode(1, "episode_quiet", { velocity_6h_delta: 0 }),
        null,
      ),
      buildDiscoveryGroup(
        episode(2, "episode_rising", { velocity_6h_delta: 4, mentions_1h: 2 }),
        null,
      ),
      buildDiscoveryGroup(
        episode(3, "episode_security", {
          source_ids: ["cisa.kev"],
          signal_roles: ["PRIMARY_EMISSION"],
        }),
        null,
      ),
    ];

    expect(filterDiscoveryGroups(groups, "RISING", "").map((group) => group.episode.rank)).toEqual([
      2,
    ]);
    expect(
      filterDiscoveryGroups(groups, "SECURITY", "").map((group) => group.episode.rank),
    ).toEqual([3]);
    expect(
      filterDiscoveryGroups(groups, "PRIMARY", "").map((group) => group.episode.rank),
    ).toEqual([1, 2, 3]);
  });

  it("formats feed age compactly", () => {
    expect(formatDiscoveryAge(45)).toBe("45s");
    expect(formatDiscoveryAge(90)).toBe("1m");
    expect(formatDiscoveryAge(7_200)).toBe("2h");
    expect(formatDiscoveryAge(172_800)).toBe("2d");
  });
});
