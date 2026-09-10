import { describe, expect, it } from "vitest";
import type {
  EpisodeResponse,
  ObservationEvidenceResponse,
} from "../../../clients/typescript/src/generated/public_read_v0";
import {
  buildDiscoveryCard,
  filterDiscoveryCards,
  formatDiscoveryAge,
} from "./discover";

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

describe("DISCOVER feed presentation model", () => {
  it("extracts human-readable artifact identity and searchable metadata", () => {
    const item = episode(1, "episode_agent");
    const card = buildDiscoveryCard(
      item,
      observation("obs_1", "pypi.updates", {
        canonical_url: "https://pypi.org/project/hyper-agent/0.2.0/",
        name: "hyper-agent",
        version: "0.2.0",
        source_metadata: { description: "Agent runtime with local tools" },
      }),
    );

    expect(card.title).toBe("hyper-agent 0.2.0");
    expect(card.excerpt).toBe("Agent runtime with local tools");
    expect(card.url).toContain("pypi.org");
    expect(filterDiscoveryCards([card], "ALL", "local tools")).toEqual([card]);
  });

  it("filters lanes without changing baseline order", () => {
    const cards = [
      buildDiscoveryCard(
        episode(1, "episode_quiet", { velocity_6h_delta: 0 }),
        observation("obs_1", "pypi.updates", { name: "quiet-package" }),
      ),
      buildDiscoveryCard(
        episode(2, "episode_rising", { velocity_6h_delta: 4, mentions_1h: 2 }),
        observation("obs_2", "pypi.updates", { name: "rising-package" }),
      ),
      buildDiscoveryCard(
        episode(3, "episode_security", {
          source_ids: ["cisa.kev"],
          signal_roles: ["PRIMARY_EMISSION"],
        }),
        observation("obs_3", "cisa.kev", { title: "A newly exploited vulnerability" }),
      ),
    ];

    expect(filterDiscoveryCards(cards, "RISING", "").map((card) => card.episode.rank)).toEqual([2]);
    expect(filterDiscoveryCards(cards, "SECURITY", "").map((card) => card.episode.rank)).toEqual([3]);
    expect(filterDiscoveryCards(cards, "PRIMARY", "").map((card) => card.episode.rank)).toEqual([1, 2, 3]);
  });

  it("formats feed age compactly", () => {
    expect(formatDiscoveryAge(45)).toBe("45s");
    expect(formatDiscoveryAge(90)).toBe("1m");
    expect(formatDiscoveryAge(7_200)).toBe("2h");
    expect(formatDiscoveryAge(172_800)).toBe("2d");
  });
});
