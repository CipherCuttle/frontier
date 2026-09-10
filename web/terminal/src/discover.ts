import type {
  EpisodeEvidenceResponse,
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

export interface DiscoveryEvidenceItem {
  observation: ObservationEvidenceResponse;
  title: string;
  excerpt: string | null;
  url: string | null;
}

export interface DiscoveryGroup {
  episode: EpisodeResponse;
  evidenceResponse: EpisodeEvidenceResponse | null;
  evidence: readonly DiscoveryEvidenceItem[];
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

function safeHttpUrl(value: unknown): string | null {
  const raw = stringValue(value);
  if (!raw) return null;
  try {
    const url = new URL(raw);
    return url.protocol === "http:" || url.protocol === "https:" ? url.toString() : null;
  } catch {
    return null;
  }
}

export function buildDiscoveryEvidenceItem(
  observation: ObservationEvidenceResponse,
): DiscoveryEvidenceItem {
  const payload = observation.payload;
  const name = stringValue(payload.name);
  const version = stringValue(payload.version);
  const title =
    stringValue(payload.title) ??
    (name && version ? `${name} ${version}` : name) ??
    stringValue(payload.metric_name) ??
    metadataString(payload, "feed_title") ??
    observation.source_item_key;

  return {
    observation,
    title,
    excerpt: stringValue(payload.excerpt) ?? metadataString(payload, "description"),
    url: safeHttpUrl(payload.canonical_url),
  };
}

export function buildDiscoveryGroup(
  episode: EpisodeResponse,
  evidenceResponse: EpisodeEvidenceResponse | null,
): DiscoveryGroup {
  if (evidenceResponse === null) {
    return { episode, evidenceResponse: null, evidence: [] };
  }
  if (evidenceResponse.episode.episode_id !== episode.episode_id) {
    throw new Error("DISCOVER evidence response episode identity mismatch");
  }
  return {
    episode,
    evidenceResponse,
    evidence: evidenceResponse.observations.map(buildDiscoveryEvidenceItem),
  };
}

function hasSource(episode: EpisodeResponse, sources: ReadonlySet<string>): boolean {
  return episode.source_ids.some((source) => sources.has(source));
}

export function matchesDiscoveryLane(group: DiscoveryGroup, lane: DiscoveryLane): boolean {
  const episode = group.episode;
  if (lane === "ALL") return true;
  if (lane === "LIVE") return episode.mentions_1h > 0;
  if (lane === "RISING") return episode.velocity_6h_delta > 0;
  if (lane === "PRIMARY") return episode.signal_roles.includes("PRIMARY_EMISSION");
  if (lane === "AI") return hasSource(episode, AI_SOURCES);
  if (lane === "CODE") return hasSource(episode, CODE_SOURCES);
  if (lane === "SECURITY") return hasSource(episode, SECURITY_SOURCES);
  return hasSource(episode, BUZZ_SOURCES);
}

function evidenceSearchText(item: DiscoveryEvidenceItem): string[] {
  const payload = item.observation.payload;
  const metadata = payload.source_metadata;
  const metadataValues =
    metadata && typeof metadata === "object" && !Array.isArray(metadata)
      ? Object.values(metadata as Record<string, unknown>).filter(
          (value): value is string => typeof value === "string",
        )
      : [];
  return [
    item.title,
    item.excerpt ?? "",
    item.url ?? "",
    item.observation.source_id,
    item.observation.kind,
    item.observation.source_item_key,
    ...metadataValues,
  ];
}

export function discoverySearchText(group: DiscoveryGroup): string {
  return [
    group.episode.episode_id,
    ...group.episode.source_ids,
    ...group.episode.signal_roles,
    ...group.evidence.flatMap(evidenceSearchText),
  ]
    .join(" ")
    .toLocaleLowerCase();
}

export function filterDiscoveryGroups(
  groups: readonly DiscoveryGroup[],
  lane: DiscoveryLane,
  rawQuery: string,
): DiscoveryGroup[] {
  const query = rawQuery.trim().toLocaleLowerCase();
  return groups.filter((group) => {
    if (!matchesDiscoveryLane(group, lane)) return false;
    return !query || discoverySearchText(group).includes(query);
  });
}

export function formatDiscoveryAge(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3_600) return `${Math.floor(seconds / 60)}m`;
  if (seconds < 86_400) return `${Math.floor(seconds / 3_600)}h`;
  return `${Math.floor(seconds / 86_400)}d`;
}
