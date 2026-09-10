import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
} from "react";
import {
  getEpisode,
  getRadar,
  type EpisodeEvidenceResponse,
  type FrontierPublicReadTransport,
  type ViewResponse,
} from "../../../clients/typescript/src/generated/public_read_v0";
import {
  buildDiscoveryEvidenceItem,
  buildDiscoveryGroup,
  DISCOVERY_LANES,
  filterDiscoveryGroups,
  formatDiscoveryAge,
  matchesDiscoveryLane,
  type DiscoveryGroup,
  type DiscoveryLane,
} from "./discover";
import { TerminalApp } from "./TerminalApp";
import "./discover.css";

interface DiscoverAppProps {
  transport: FrontierPublicReadTransport;
}

const DISCOVERY_LIMIT = 100;
const HYDRATION_BATCH_SIZE = 8;

function isEditableTarget(target: EventTarget | null): boolean {
  return (
    target instanceof HTMLElement &&
    (target.isContentEditable || target.tagName === "INPUT" || target.tagName === "TEXTAREA")
  );
}

function shortId(value: string, width = 12): string {
  if (value.length <= width + 1) return value;
  return `${value.slice(0, width)}…`;
}

function sourceLabel(sourceId: string): string {
  const labels: Record<string, string> = {
    "arxiv.cs-ai": "arXiv / CS.AI",
    "cisa.kev": "CISA KEV",
    "gdelt.frontier": "GDELT",
    "github.ml-repos": "GitHub",
    "hf.models": "Hugging Face",
    "hn.frontpage": "Hacker News",
    "pypi.updates": "PyPI",
  };
  return labels[sourceId] ?? sourceId;
}

function roleLabel(role: string): string {
  if (role === "PRIMARY_EMISSION") return "primary";
  if (role === "ATTENTION") return "attention";
  if (role === "DISCOVERY") return "discovery";
  return role.toLocaleLowerCase().replaceAll("_", " ");
}

function DiscoveryGroupView({
  group,
  onInspect,
}: {
  group: DiscoveryGroup;
  onInspect: (evidence: EpisodeEvidenceResponse) => void;
}) {
  const episode = group.episode;
  const rising = episode.velocity_6h_delta > 0;
  const live = episode.mentions_1h > 0;
  return (
    <article className="discover-card" data-episode-id={episode.episode_id}>
      <div className="discover-rank" aria-label={`Baseline rank ${episode.rank}`}>
        <span>#{episode.rank}</span>
        <small>BASE</small>
      </div>
      <div className="discover-card-main">
        <header className="discover-card-header">
          <div className="discover-source-line">
            <span className="discover-source">EPISODE</span>
            <span>{formatDiscoveryAge(episode.age_seconds)} old</span>
            {live ? <span className="discover-signal live">LIVE {episode.mentions_1h}/h</span> : null}
            {rising ? <span className="discover-signal rising">RISING +{episode.velocity_6h_delta}</span> : null}
          </div>
          <h2 className="discover-episode-id">{shortId(episode.episode_id, 28)}</h2>
        </header>

        <section className="discover-evidence-preview" aria-label="Bound evidence preview">
          <header>
            <span>BOUND EVIDENCE · TITLES BELOW ARE EVIDENCE CONTENT, NOT EPISODE NAMES</span>
            <strong>{group.evidence.length}/{episode.evidence_count_total}</strong>
          </header>
          {group.evidenceResponse === null ? (
            <p className="discover-preview-unavailable">
              Evidence is still loading or unavailable for this snapshot. This is not a claim of real-world absence.
            </p>
          ) : null}
          {group.evidence.map((item) => (
            <article className="discover-preview-item" key={item.observation.observation_id}>
              <div className="discover-evidence-meta">
                <span>EVIDENCE ITEM</span>
                <span>{sourceLabel(item.observation.source_id)}</span>
                <span>{item.observation.kind}</span>
                <span>{item.observation.observed_at}</span>
              </div>
              <h3>
                {item.url ? (
                  <a href={item.url} target="_blank" rel="noreferrer">
                    {item.title}
                  </a>
                ) : (
                  item.title
                )}
              </h3>
              {item.excerpt ? <p>{item.excerpt}</p> : null}
            </article>
          ))}
        </section>

        <footer className="discover-card-footer">
          <div className="discover-tags">
            {episode.signal_roles.map((role) => (
              <span className="discover-tag" key={role}>
                {roleLabel(role)}
              </span>
            ))}
            {episode.source_count > 1 ? (
              <span className="discover-tag">{episode.source_count} sources</span>
            ) : null}
          </div>
          <div className="discover-actions">
            <span>{episode.evidence_count_total} evidence</span>
            <button
              type="button"
              disabled={group.evidenceResponse === null}
              onClick={() => {
                if (group.evidenceResponse !== null) onInspect(group.evidenceResponse);
              }}
            >
              inspect exact evidence →
            </button>
          </div>
        </footer>
      </div>
    </article>
  );
}

function EvidenceDrawer({
  evidence,
  onClose,
}: {
  evidence: EpisodeEvidenceResponse;
  onClose: () => void;
}) {
  return (
    <aside className="discover-drawer" aria-live="polite" aria-label="Evidence inspector">
      <header className="discover-drawer-header">
        <div>
          <span className="discover-kicker">POINT-IN-TIME EVIDENCE</span>
          <strong>
            #{evidence.episode.rank} · {shortId(evidence.episode.episode_id, 20)}
          </strong>
        </div>
        <button type="button" onClick={onClose} aria-label="Close evidence inspector">
          ×
        </button>
      </header>
      <div className="discover-evidence-list">
        <div className="discover-binding">
          <span>as_of {evidence.snapshot.as_of}</span>
          <code>{shortId(evidence.snapshot.snapshot_id, 22)}</code>
        </div>
        {evidence.observations.map((observation) => {
          const item = buildDiscoveryEvidenceItem(observation);
          return (
            <article className="discover-evidence" key={observation.observation_id}>
              <div className="discover-evidence-meta">
                <span>{sourceLabel(observation.source_id)}</span>
                <span>{observation.kind}</span>
                <span>{observation.observed_at}</span>
              </div>
              <h3>
                {item.url ? (
                  <a href={item.url} target="_blank" rel="noreferrer">
                    {item.title}
                  </a>
                ) : (
                  item.title
                )}
              </h3>
              <code>{shortId(observation.observation_id, 24)}</code>
            </article>
          );
        })}
        <p className="discover-epistemic-note">
          Evidence titles are source content, not episode/entity identity. Source count is evidence diversity,
          not independent factual confirmation. Missing evidence is not observed absence.
        </p>
      </div>
    </aside>
  );
}

export function DiscoverApp({ transport }: DiscoverAppProps) {
  const searchRef = useRef<HTMLInputElement>(null);
  const requestRef = useRef(0);
  const [operatorMode, setOperatorMode] = useState(false);
  const [view, setView] = useState<ViewResponse | null>(null);
  const [episodeEvidence, setEpisodeEvidence] = useState<
    ReadonlyMap<string, EpisodeEvidenceResponse | null>
  >(new Map());
  const [lane, setLane] = useState<DiscoveryLane>("ALL");
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [hydratedCount, setHydratedCount] = useState(0);
  const [hydrationFailures, setHydrationFailures] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [selectedEvidence, setSelectedEvidence] = useState<EpisodeEvidenceResponse | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);

  const closeDrawer = useCallback(() => {
    setDrawerOpen(false);
    setSelectedEvidence(null);
  }, []);

  const loadDiscovery = useCallback(async () => {
    const requestId = ++requestRef.current;
    setLoading(true);
    setError(null);
    setEpisodeEvidence(new Map());
    setHydratedCount(0);
    setHydrationFailures(0);
    setSelectedEvidence(null);
    setDrawerOpen(false);
    try {
      const response = await getRadar(transport, { limit: DISCOVERY_LIMIT, offset: 0 });
      if (requestRef.current !== requestId) return;
      setView(response);
      setLoading(false);

      const snapshotId = response.snapshot.snapshot_id;
      for (let offset = 0; offset < response.items.length; offset += HYDRATION_BATCH_SIZE) {
        const batch = response.items.slice(offset, offset + HYDRATION_BATCH_SIZE);
        const results = await Promise.all(
          batch.map(
            async (
              episode,
            ): Promise<[string, EpisodeEvidenceResponse | null, boolean]> => {
              try {
                const evidence = await getEpisode(transport, episode.episode_id, {
                  snapshot_id: snapshotId,
                });
                if (
                  evidence.snapshot.snapshot_id !== snapshotId ||
                  evidence.episode.episode_id !== episode.episode_id
                ) {
                  return [episode.episode_id, null, true];
                }
                return [episode.episode_id, evidence, false];
              } catch {
                return [episode.episode_id, null, true];
              }
            },
          ),
        );
        if (requestRef.current !== requestId) return;
        setEpisodeEvidence((current) => {
          const next = new Map(current);
          for (const [episodeId, evidence] of results) next.set(episodeId, evidence);
          return next;
        });
        setHydratedCount((current) => current + results.length);
        setHydrationFailures(
          (current) => current + results.filter(([, , failed]) => failed).length,
        );
      }
    } catch (caught) {
      if (requestRef.current !== requestId) return;
      setLoading(false);
      setError(caught instanceof Error ? caught.message : "Discovery feed request failed.");
    }
  }, [transport]);

  useEffect(() => {
    void loadDiscovery();
    return () => {
      requestRef.current += 1;
    };
  }, [loadDiscovery]);

  useEffect(() => {
    if (operatorMode) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (isEditableTarget(event.target)) {
        if (event.key === "Escape") {
          (event.target as HTMLElement).blur();
          if (query) setQuery("");
        }
        return;
      }
      if (event.key === "/") {
        event.preventDefault();
        searchRef.current?.focus();
      }
      if (event.key === "Escape" && drawerOpen) closeDrawer();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [closeDrawer, drawerOpen, operatorMode, query]);

  const groups = useMemo(() => {
    return (view?.items ?? []).map((episode) =>
      buildDiscoveryGroup(episode, episodeEvidence.get(episode.episode_id) ?? null),
    );
  }, [episodeEvidence, view]);

  const visibleGroups = useMemo(
    () => filterDiscoveryGroups(groups, lane, query),
    [groups, lane, query],
  );

  const laneCounts = useMemo(() => {
    const counts = new Map<DiscoveryLane, number>();
    for (const definition of DISCOVERY_LANES) {
      counts.set(
        definition.id,
        groups.filter((group) => matchesDiscoveryLane(group, definition.id)).length,
      );
    }
    return counts;
  }, [groups]);

  const handleSearchKeyDown = (event: ReactKeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Escape") {
      event.currentTarget.blur();
      setQuery("");
    }
  };

  if (operatorMode) {
    return (
      <div className="discover-operator-mode">
        <button
          className="discover-return"
          type="button"
          onClick={() => setOperatorMode(false)}
        >
          ← discover feed
        </button>
        <TerminalApp transport={transport} />
      </div>
    );
  }

  return (
    <div className={drawerOpen ? "discover-shell drawer-open" : "discover-shell"}>
      <header className="discover-header">
        <div className="discover-brand">
          <span>FRONTIER</span>
          <strong>DISCOVER</strong>
        </div>
        <div className="discover-search">
          <label htmlFor="discover-query">Search the current evidence horizon</label>
          <div className="discover-search-box">
            <kbd>/</kbd>
            <input
              id="discover-query"
              ref={searchRef}
              value={query}
              onChange={(event) => setQuery(event.currentTarget.value)}
              onKeyDown={handleSearchKeyDown}
              placeholder="models, agents, CVEs, packages, repos…"
              autoComplete="off"
            />
            {query ? (
              <button type="button" onClick={() => setQuery("")} aria-label="Clear search">
                ×
              </button>
            ) : null}
          </div>
        </div>
        <div className="discover-header-actions">
          <button type="button" onClick={() => void loadDiscovery()}>
            refresh
          </button>
          <button
            type="button"
            onClick={() => {
              closeDrawer();
              setOperatorMode(true);
            }}
          >
            operator terminal ↗
          </button>
        </div>
      </header>

      <div className="discover-status-strip">
        <span className="discover-status-live">DEFAULT FEED</span>
        <span>baseline episode rank preserved · filters never rerank</span>
        <span>evidence titles are not episode names</span>
        <span>
          as_of <code>{view?.snapshot.as_of ?? "UNBOUND"}</code>
        </span>
        <span>
          evidence {hydratedCount}/{view?.items.length ?? 0}
          {hydrationFailures ? ` · ${hydrationFailures} unavailable` : ""}
        </span>
      </div>

      <nav className="discover-lanes" aria-label="Discovery filters">
        {DISCOVERY_LANES.map((definition) => (
          <button
            key={definition.id}
            type="button"
            className={lane === definition.id ? "active" : ""}
            aria-pressed={lane === definition.id}
            onClick={() => setLane(definition.id)}
          >
            <span>{definition.label}</span>
            <strong>{laneCounts.get(definition.id) ?? 0}</strong>
            <small>{definition.note}</small>
          </button>
        ))}
      </nav>

      <main className="discover-main">
        <section className="discover-feed" aria-labelledby="discover-feed-title">
          <div className="discover-feed-heading">
            <div>
              <span className="discover-kicker">
                {lane === "ALL"
                  ? "DEFAULT / OPEN SOMETHING INTERESTING"
                  : `${lane} / FILTERED`}
              </span>
              <h1 id="discover-feed-title">
                {query ? `Search: “${query}”` : "What’s happening before it gets boring?"}
              </h1>
            </div>
            <div className="discover-result-count">
              <strong>{visibleGroups.length}</strong>
              <span>of {view?.items.length ?? 0} episodes</span>
            </div>
          </div>

          {error ? (
            <div className="discover-state error" role="alert">
              {error}
            </div>
          ) : null}
          {loading ? <div className="discover-state">Loading latest baseline snapshot…</div> : null}
          {!loading && !error && visibleGroups.length === 0 ? (
            <div className="discover-state">
              <strong>No matching evidence in this bounded snapshot.</strong>
              <span>
                Try another lane or clear the search. This is not a claim of real-world absence.
              </span>
            </div>
          ) : null}

          <div className="discover-card-list">
            {visibleGroups.map((group) => (
              <DiscoveryGroupView
                group={group}
                key={group.episode.episode_id}
                onInspect={(evidence) => {
                  setSelectedEvidence(evidence);
                  setDrawerOpen(true);
                }}
              />
            ))}
          </div>
        </section>

        <aside className="discover-context">
          <section>
            <span className="discover-kicker">HOW TO USE IT</span>
            <h2>Find a thread. Follow the evidence.</h2>
            <p>
              Click a lane, search the exact evidence content, open a source item, or inspect every
              observation bound to an episode at this snapshot.
            </p>
          </section>
          <section>
            <span className="discover-kicker">SEMANTIC GUARD</span>
            <p>
              Episode identity and baseline rank stay server-authoritative. Human-readable titles are
              shown only as explicitly labelled evidence content nested under that episode.
            </p>
            <p>
              PEF and ZERO-DAY remain experimental/diagnostic and do not silently influence this feed.
            </p>
          </section>
          <section className="discover-health-mini">
            <span>
              transport <strong>{view?.transport_state ?? "—"}</strong>
            </span>
            <span>
              freshness <strong>{view?.freshness_state ?? "—"}</strong>
            </span>
            <span>
              coverage <strong>{view?.coverage_state ?? "—"}</strong>
            </span>
            <span>
              schema <strong>{view?.schema_state ?? "—"}</strong>
            </span>
          </section>
        </aside>
      </main>

      {drawerOpen && selectedEvidence ? (
        <EvidenceDrawer evidence={selectedEvidence} onClose={closeDrawer} />
      ) : null}
    </div>
  );
}
