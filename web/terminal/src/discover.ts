import type {
  EpisodeResponse,
  ObservationEvidenceResponse,
} from "../../../clients/typescript/src/generated/public_read_v0";

export type DiscoveryLane =
  | "ALL"
  | "LIVE"
  | "RISING"
  | "PRIMARY"
  | "AI"
  | "CODE"
  | "SECURITY"
  | "BUZZ";

export interface DiscoveryCard {
  episode: EpisodeResponse;
  observation: ObservationEvidenceResponse | null;
  title: string;
  excerpt: string | null;
  url: string | null;
  sourceId: string;
  kind: string;
  sourceItemKey: string;
}

export const DISCOVERY_LANES: readonly {
  id: DiscoveryLane;
  label: string;
  note: string;
}[] = [
  { id: "ALL", label: "Discover", note: "baseline order" },
  { id: "LIVE", label: "Live", note: "seen in the last hour" },
  { id: "RISING", label: "Rising", note: "positive 6h velocity" },
  { id: "PRIMARY", label: "Primary", note: "primary-emission evidence" },
  { id: "AI", label: "AI", note: "models + research" },
  { id: "CODE", label: "Code", note: "repos + packages" },
  { id: "SECURITY", label: "Security", note: "known exploited vulnerabilities" },
  { id: "BUZZ", label: "Buzz", note: "attention + discovery" },
];

const AI_SOURCES = new Set(["hf.models", "arxiv.cs-ai"]);
const CODE_SOURCES = new Set(["github.ml-repos", "pypi.updates"]);
const SECURITY_SOURCES = new Set(["cisa.kev"]);
const BUZZ_SOURCES = new Set(["hn.frontpage", "gdelt.frontier"]);

function stringValue(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

function metadataString(payload: Record<string, unknown>, key: string): string | null {
  const metadata = payload.source_metadata;
  if (!metadata || typeof metadata !== "object" || Array.isArray(metadata)) return null;
  return stringValue((metadata as Record<string, unknown>)[key]);
}

function firstSource(episode: EpisodeResponse): string {
  return episode.source_ids[0] ?? "unknown-source";
}

export function buildDiscoveryCard(
  episode: EpisodeResponse,
  observation: ObservationEvidenceResponse | null,
): DiscoveryCard {
  if (observation === null) {
    return {
      episode,
      observation,
      title: episode.episode_id,
      excerpt: null,
      url: null,
      sourceId: firstSource(episode),
      kind: "UNKNOWN",
      sourceItemKey: episode.episode_id,
    };
  }

  const payload = observation.payload;
  const name = stringValue(payload.name);
  const version = stringValue(payload.version);
  const title =
    stringValue(payload.title) ??
    (name && version ? `${name} ${version}` : name) ??
    stringValue(payload.metric_name) ??
    metadataString(payload, "feed_title") ??
    observation.source_item_key;
  const excerpt = stringValue(payload.excerpt) ?? metadataString(payload, "description");

  return {
    episode,
    observation,
    title,
    excerpt,
    url: stringValue(payload.canonical_url),
    sourceId: observation.source_id,
    kind: observation.kind,
    sourceItemKey: observation.source_item_key,
  };
}

function hasSource(episode: EpisodeResponse, sources: ReadonlySet<string>): boolean {
  return episode.source_ids.some((source) => sources.has(source));
}

export function matchesDiscoveryLane(card: DiscoveryCard, lane: DiscoveryLane): boolean {
  const episode = card.episode;
  if (lane === "ALL") return true;
  if (lane === "LIVE") return episode.mentions_1h > 0;
  if (lane === "RISING") return episode.velocity_6h_delta > 0;
  if (lane === "PRIMARY") return episode.signal_roles.includes("PRIMARY_EMISSION");
  if (lane === "AI") return hasSource(episode, AI_SOURCES);
  if (lane === "CODE") return hasSource(episode, CODE_SOURCES);
  if (lane === "SECURITY") return hasSource(episode, SECURITY_SOURCES);
  return hasSource(episode, BUZZ_SOURCES);
}

export function discoverySearchText(card: DiscoveryCard): string {
  const payload = card.observation?.payload ?? {};
  const metadata = payload.source_metadata;
  const metadataValues =
    metadata && typeof metadata === "object" && !Array.isArray(metadata)
      ? Object.values(metadata as Record<string, unknown>).filter(
          (value): value is string => typeof value === "string",
        )
      : [];

  return [
    card.title,
    card.excerpt ?? "",
    card.url ?? "",
    card.sourceId,
    card.kind,
    card.sourceItemKey,
    card.episode.episode_id,
    ...card.episode.source_ids,
    ...card.episode.signal_roles,
    ...metadataValues,
  ]
    .join(" ")
    .toLocaleLowerCase();
}

export function filterDiscoveryCards(
  cards: readonly DiscoveryCard[],
  lane: DiscoveryLane,
  rawQuery: string,
): DiscoveryCard[] {
  const query = rawQuery.trim().toLocaleLowerCase();
  return cards.filter((card) => {
    if (!matchesDiscoveryLane(card, lane)) return false;
    return !query || discoverySearchText(card).includes(query);
  });
}

export function formatDiscoveryAge(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3_600) return `${Math.floor(seconds / 60)}m`;
  if (seconds < 86_400) return `${Math.floor(seconds / 3_600)}h`;
  return `${Math.floor(seconds / 86_400)}d`;
}
