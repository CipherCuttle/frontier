import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
} from "react";
import {
  createTerminalPublicReadApi,
  experimentalAvailability,
  type EpisodeEvidenceResponse,
  type EpisodeResponse,
  type ExperimentalFeatureBatchSectionResponse,
  type ExperimentalOverviewResponse,
  type ExperimentalShadowRunSectionResponse,
  type FrontierPublicReadTransport,
  type HealthResponse,
  type PublicViewKind,
  type ViewResponse,
} from "./api";
import {
  assertSnapshotBinding,
  buildExperimentHistory,
  buildFeatureExplanations,
  computeRankDeltas,
  displayRankDelta,
  displayUnavailable,
  EXPERIMENTAL_LENS,
  EXPERIMENTAL_LENS_LABEL,
  EXPERIMENTAL_LENS_NOTE,
  filterEpisodes,
  isEditableTarget,
  resolveKeyboardCommand,
  resolveSectionAvailability,
  shortId,
  type ExperimentalRankDelta,
  type PanelKind,
  type TerminalLens,
} from "./model";

interface TerminalAppProps {
  transport: FrontierPublicReadTransport;
}

const LENSES: readonly PublicViewKind[] = ["RADAR", "NOW", "TRENDING"];

function StateBadge({ label, value }: { label: string; value: string }) {
  const normalized = value.toLocaleUpperCase();
  return (
    <span className={`state-badge state-${normalized.toLocaleLowerCase()}`}>
      <span className="state-label">{label}</span>
      <strong>{normalized}</strong>
    </span>
  );
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <span className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </span>
  );
}

function EpisodeTable({
  items,
  selectedEpisodeId,
  onSelect,
  onInspect,
}: {
  items: readonly EpisodeResponse[];
  selectedEpisodeId: string | null;
  onSelect: (episodeId: string) => void;
  onInspect: (episodeId: string) => void;
}) {
  return (
    <div className="table-shell">
      <table className="episode-table">
        <thead>
          <tr>
            <th scope="col">Baseline rank</th>
            <th scope="col">Episode</th>
            <th scope="col">Roles</th>
            <th scope="col">1h</th>
            <th scope="col">6h</th>
            <th scope="col">24h</th>
            <th scope="col">Δ6h</th>
            <th scope="col">Accel</th>
            <th scope="col">Evidence</th>
            <th scope="col">Sources</th>
            <th scope="col">Confirmation</th>
            <th scope="col">Root diversity</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => {
            const selected = item.episode_id === selectedEpisodeId;
            return (
              <tr key={item.episode_id} className={selected ? "selected-row" : ""} aria-selected={selected}>
                <td className="rank-cell">#{item.rank}</td>
                <td>
                  <button className="episode-button" type="button" onClick={() => onSelect(item.episode_id)}>
                    {shortId(item.episode_id, 18)}
                  </button>
                  <button
                    className="inspect-button"
                    type="button"
                    aria-label={`Inspect ${item.episode_id}`}
                    onClick={() => onInspect(item.episode_id)}
                  >
                    inspect
                  </button>
                </td>
                <td>{item.signal_roles.length ? item.signal_roles.join(" · ") : "—"}</td>
                <td className="numeric">{item.mentions_1h}</td>
                <td className="numeric">{item.mentions_6h}</td>
                <td className="numeric">{item.mentions_24h}</td>
                <td className="numeric signed">{item.velocity_6h_delta}</td>
                <td className="numeric signed">{item.acceleration_6h}</td>
                <td className="numeric">{item.evidence_count_total}</td>
                <td className="numeric">{item.source_count}</td>
                <td><span className="unavailable">{displayUnavailable(item.confirmation)}</span></td>
                <td><span className="unavailable">{displayUnavailable(item.evidence_root_diversity)}</span></td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function Inspector({ evidence }: { evidence: EpisodeEvidenceResponse }) {
  return (
    <section className="panel-content" aria-labelledby="inspector-title">
      <div className="panel-heading">
        <p className="eyebrow">Exact snapshot episode</p>
        <h2 id="inspector-title">Evidence inspector</h2>
      </div>
      <div className="binding-line">
        <code>{evidence.snapshot.snapshot_id}</code>
        <span>as_of {evidence.snapshot.as_of}</span>
      </div>
      <div className="metric-grid">
        <Metric label="Baseline rank" value={`#${evidence.episode.rank}`} />
        <Metric label="Evidence" value={evidence.episode.evidence_count_total} />
        <Metric label="Sources" value={evidence.episode.source_count} />
        <Metric label="1h" value={evidence.episode.mentions_1h} />
        <Metric label="6h Δ" value={evidence.episode.velocity_6h_delta} />
        <Metric label="Accel" value={evidence.episode.acceleration_6h} />
      </div>
      <div className="epistemic-warning">
        <strong>Confirmation: {displayUnavailable(evidence.episode.confirmation)}</strong>
        <span>Provenance-root diversity: {displayUnavailable(evidence.episode.evidence_root_diversity)}</span>
        <small>Source count is not independent factual confirmation.</small>
      </div>
      <div className="observation-stack">
        {evidence.observations.map((observation, index) => (
          <article className="observation-card" key={observation.observation_id}>
            <header>
              <span className="observation-number">OBS {String(index + 1).padStart(2, "0")}</span>
              <code>{observation.source_id}</code>
              <span>{observation.kind}</span>
            </header>
            <dl className="evidence-meta">
              <div><dt>Observation</dt><dd><code>{observation.observation_id}</code></dd></div>
              <div><dt>Source item</dt><dd>{observation.source_item_key}</dd></div>
              <div><dt>Observed</dt><dd>{observation.observed_at}</dd></div>
              <div><dt>Retrieved</dt><dd>{observation.retrieved_at}</dd></div>
              <div><dt>Published</dt><dd>{observation.source_published_at ?? "UNAVAILABLE"}</dd></div>
              <div><dt>Effective</dt><dd>{observation.effective_at ?? "UNAVAILABLE"}</dd></div>
            </dl>
            <details open={index === 0}>
              <summary>Evidence payload</summary>
              <pre>{JSON.stringify(observation.payload, null, 2)}</pre>
            </details>
            <details>
              <summary>Collection causality ({observation.collection_occurrences.length})</summary>
              {observation.collection_occurrences.length === 0 ? (
                <p>No collection occurrence is visible at this snapshot horizon.</p>
              ) : (
                <ul className="audit-list">
                  {observation.collection_occurrences.map((occurrence) => (
                    <li key={occurrence.run_id}>
                      <code>{occurrence.run_id}</code> · {occurrence.reason} · {occurrence.occurrence_status} · recovered={String(occurrence.recovered_after_gap)} · started {occurrence.started_at} · completed {occurrence.completed_at ?? "NOT YET KNOWN"}
                    </li>
                  ))}
                </ul>
              )}
            </details>
            <details>
              <summary>Relations ({observation.relations.length})</summary>
              {observation.relations.length === 0 ? (
                <p>No relation is visible for this observation at this snapshot horizon.</p>
              ) : (
                <ul className="audit-list">
                  {observation.relations.map((relation) => (
                    <li key={relation.relation_id}>
                      <code>{relation.relation_id}</code> · {relation.relation_type} · authority {relation.authority} · confidence {relation.confidence ?? "UNAVAILABLE"}
                    </li>
                  ))}
                </ul>
              )}
            </details>
            <footer className="digest-line">
              <span>content <code>{observation.content_digest}</code></span>
              <span>fetch <code>{observation.fetch_digest}</code></span>
            </footer>
          </article>
        ))}
      </div>
    </section>
  );
}

function HealthPanel({ health }: { health: HealthResponse }) {
  return (
    <section className="panel-content" aria-labelledby="health-title">
      <div className="panel-heading">
        <p className="eyebrow">Source/system health is product data</p>
        <h2 id="health-title">Health + coverage</h2>
      </div>
      <div className="health-grid">
        <StateBadge label="Transport" value={health.transport_state} />
        <StateBadge label="Freshness" value={health.freshness_state} />
        <StateBadge label="Coverage" value={health.coverage_state} />
        <StateBadge label="Schema" value={health.schema_state} />
      </div>
      <p className="health-note">UNKNOWN means unknown. Missing input is not observed absence.</p>
      <div className="source-health-list">
        {health.sources.map((source) => (
          <article key={source.source_id} className="source-health-card">
            <header><code>{source.source_id}</code><span>{source.as_of}</span></header>
            <div className="source-health-dimensions">
              <StateBadge label="Transport" value={source.transport} />
              <StateBadge label="Freshness" value={source.freshness} />
              <StateBadge label="Completeness" value={source.completeness} />
              <StateBadge label="Schema" value={source.schema} />
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

function AuditPanel({ view }: { view: ViewResponse }) {
  const snapshot = view.snapshot;
  return (
    <section className="panel-content audit-panel" aria-labelledby="audit-title">
      <div className="panel-heading">
        <p className="eyebrow">Public response binding</p>
        <h2 id="audit-title">Audit identity</h2>
      </div>
      <dl className="audit-definition-list">
        <div><dt>Snapshot</dt><dd><code>{snapshot.snapshot_id}</code></dd></div>
        <div><dt>Receipt</dt><dd><code>{snapshot.receipt_id}</code></dd></div>
        <div><dt>Receipt schema</dt><dd>{snapshot.receipt_schema_version}</dd></div>
        <div><dt>Projection</dt><dd>{snapshot.projection_name} / {snapshot.projection_version}</dd></div>
        <div><dt>Schema</dt><dd>{snapshot.schema_version}</dd></div>
        <div><dt>Algorithm</dt><dd>{snapshot.algorithm_version}</dd></div>
        <div><dt>Ranking policy</dt><dd>{snapshot.ranking_policy_version}</dd></div>
        <div><dt>As of</dt><dd>{snapshot.as_of}</dd></div>
        <div><dt>Semantic scope</dt><dd>{view.semantic_scope}</dd></div>
        <div><dt>Configuration digest</dt><dd><code>{snapshot.configuration_digest}</code></dd></div>
        <div><dt>Input digest</dt><dd><code>{snapshot.input_digest}</code></dd></div>
        <div><dt>Output digest</dt><dd><code>{snapshot.output_digest}</code></dd></div>
      </dl>
    </section>
  );
}

function HelpPanel() {
  const commands = [
    ["1 / 2 / 3", "RADAR / NOW / TRENDING baseline lenses"],
    ["x", "EXPERIMENTAL shadow comparison lens (toggle)"],
    ["j / ↓", "next visible episode"],
    ["k / ↑", "previous visible episode"],
    ["Enter", "inspect selected episode"],
    ["/", "focus local filter"],
    ["h", "health panel"],
    ["a", "audit identity"],
    ["?", "keyboard help"],
    ["r", "refresh same snapshot"],
    ["Esc", "close top panel / leave editable field"],
  ];
  return (
    <section className="panel-content" aria-labelledby="help-title">
      <div className="panel-heading"><p className="eyebrow">Keyboard-first</p><h2 id="help-title">Command map</h2></div>
      <dl className="command-list">
        {commands.map(([key, label]) => <div key={key}><dt><kbd>{key}</kbd></dt><dd>{label}</dd></div>)}
      </dl>
    </section>
  );
}

/**
 * EXPERIMENTAL_SHADOW panel state. Experimental data lives entirely outside
 * the baseline view state: entering/leaving the EXPERIMENTAL lens never
 * mutates or replaces baseline lenses, rows, filter, inspector, or panels.
 */
type ExperimentalState =
  | { status: "idle" }
  | { status: "loading" }
  | {
      status: "ready";
      asOf: string;
      snapshotId: string;
      overview: ExperimentalOverviewResponse | null;
      runsSection: ExperimentalShadowRunSectionResponse | null;
      batchesSection: ExperimentalFeatureBatchSectionResponse | null;
      radarItems: EpisodeResponse[] | null;
      failures: readonly string[];
    }
  | { status: "error"; message: string };

function AvailabilityBadge({ label, value }: { label: string; value: string }) {
  return <StateBadge label={label} value={value} />;
}

function RankDeltaTable({ deltas }: { deltas: readonly ExperimentalRankDelta[] }) {
  return (
    <div className="table-shell experimental-table-shell">
      <table className="episode-table experimental-table">
        <thead>
          <tr>
            <th scope="col">Episode</th>
            <th scope="col">Baseline rank</th>
            <th scope="col">Experimental rank</th>
            <th scope="col">Δ rank (experimental − baseline)</th>
          </tr>
        </thead>
        <tbody>
          {deltas.map((delta) => (
            <tr key={delta.episodeId}>
              <td><code>{shortId(delta.episodeId, 18)}</code></td>
              <td className="rank-cell">#{delta.baselineRank}</td>
              <td>
                <span className="unavailable">
                  {delta.experimentalRank === null ? "UNKNOWN" : `#${delta.experimentalRank}`}
                </span>
              </td>
              <td className="numeric signed">{displayRankDelta(delta.delta)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ExperimentalPanel({
  state,
  onBack,
  backLens,
}: {
  state: ExperimentalState;
  onBack: () => void;
  backLens: TerminalLens;
}) {
  if (state.status === "idle") {
    return (
      <div className="experimental-empty">
        <strong>EXPERIMENTAL panel not loaded for this snapshot.</strong>
        <span>Press <kbd>x</kbd> again or refresh (<kbd>r</kbd>) to request the EXPERIMENTAL_SHADOW surfaces.</span>
      </div>
    );
  }
  if (state.status === "loading") {
    return <div role="status" className="loading-banner">Loading EXPERIMENTAL_SHADOW surfaces…</div>;
  }
  if (state.status === "error") {
    return (
      <div role="alert" className="error-banner experimental-error">
        <strong>EXPERIMENTAL SHADOW UNAVAILABLE</strong>
        <span>{state.message}</span>
        <span>Baseline lenses remain available and unchanged.</span>
      </div>
    );
  }

  const overviewAvailability = state.overview?.availability ?? null;
  const runStatus = state.runsSection?.latest ?? state.overview?.latest_shadow_run ?? null;
  const shadowRunAvailability =
    state.runsSection?.availability ??
    resolveSectionAvailability(overviewAvailability, "shadow_run");
  const batchSection = state.batchesSection;
  const batchAvailability =
    batchSection?.availability ??
    resolveSectionAvailability(overviewAvailability, "feature_batch");
  const history = buildExperimentHistory(state.overview);
  const featureBatch = batchSection?.latest ?? state.overview?.latest_feature_batch ?? null;
  const featureExplanations = buildFeatureExplanations(featureBatch);
  const deltas = state.radarItems ? computeRankDeltas(state.radarItems, null) : null;
  const allEmpty =
    history.length > 0 && history.every((entry) => entry.availability === "NO_DATA");

  return (
    <div className="experimental-panel">
      <div className="binding-line">
        <span>experiment <code>{state.overview?.experiment_id ?? "UNKNOWN"}</code></span>
        <span>candidate <code>{state.overview?.candidate_id ?? "UNKNOWN"}</code></span>
        <span>config <code>{state.overview ? shortId(state.overview.configuration_digest, 24) : "UNKNOWN"}</code></span>
        <span>as_of {state.asOf}</span>
        <span>bound snapshot <code>{shortId(state.snapshotId, 14)}</code></span>
      </div>
      <p className="epistemic-warning">
        <strong>{EXPERIMENTAL_LENS_LABEL}</strong>
        <span>{EXPERIMENTAL_LENS_NOTE}</span>
      </p>

      {state.failures.length > 0 ? (
        <div role="alert" className="experimental-failures">
          <strong>EXPERIMENTAL sections unavailable (UNKNOWN):</strong>
          <span>{state.failures.join(" · ")}</span>
        </div>
      ) : null}

      <section aria-labelledby="experimental-runs-title" className="experimental-section">
        <h2 id="experimental-runs-title">Shadow run status</h2>
        <div className="experimental-run-card">
          <AvailabilityBadge label="Shadow run" value={experimentalAvailability(shadowRunAvailability)} />
          {runStatus ? (
            <dl className="audit-definition-list">
              <div><dt>Run</dt><dd><code>{shortId(runStatus.run_id, 20)}</code></dd></div>
              <div><dt>Status</dt><dd>{runStatus.status}</dd></div>
              <div><dt>As of</dt><dd>{runStatus.as_of}</dd></div>
              <div><dt>Candidate artifact</dt><dd><code>{shortId(runStatus.candidate_artifact_id, 20)}</code></dd></div>
              <div><dt>Control snapshot</dt><dd><code>{shortId(runStatus.control_snapshot_id, 20)}</code></dd></div>
              <div><dt>Failure reason</dt><dd>{runStatus.failure_reason ?? "NONE"}</dd></div>
            </dl>
          ) : (
            <span className="unavailable">NO SHADOW RUN DATA for this as_of (not observed absence of experiments).</span>
          )}
        </div>
      </section>

      <section aria-labelledby="experimental-deltas-title" className="experimental-section">
        <h2 id="experimental-deltas-title">Rank deltas (baseline RADAR vs candidate)</h2>
        {deltas === null ? (
          <div className="empty-state">
            <strong>Baseline RADAR view unavailable for this snapshot (UNKNOWN).</strong>
            <span>No rank deltas can be shown without the baseline rows; nothing is fabricated.</span>
          </div>
        ) : deltas.length === 0 ? (
          <div className="empty-state">
            <strong>0 baseline rows returned by RADAR for this snapshot.</strong>
            <span>This is not a claim that nothing is happening.</span>
          </div>
        ) : (
          <>
            <RankDeltaTable deltas={deltas} />
            <p className="experimental-note">
              The EXPERIMENTAL_SHADOW summary read plane exposes run/artifact identity and
              status only — per-episode candidate ranks are UNKNOWN here, so no delta is invented.
            </p>
          </>
        )}
      </section>

      <section aria-labelledby="experimental-features-title" className="experimental-section">
        <h2 id="experimental-features-title">Feature explanations</h2>
        <div className="experimental-feature-head">
          <AvailabilityBadge label="Feature batch" value={batchAvailability} />
          {featureBatch ? <span className="muted">batch <code>{shortId(featureBatch.batch_id, 18)}</code> · status {featureBatch.status}</span> : <span className="unavailable">NO BATCH DATA</span>}
        </div>
        <ul className="experimental-feature-list">
          {featureExplanations.map((feature) => (
            <li key={feature.name}>
              <strong>{feature.name}</strong>
              <span className="unavailable">{feature.value}</span>
              <small>{feature.definition}</small>
              <small>unit {feature.unit}</small>
            </li>
          ))}
        </ul>
      </section>

      <section aria-labelledby="experimental-history-title" className="experimental-section">
        <h2 id="experimental-history-title">Experiment history</h2>
        {history.length === 0 || allEmpty ? (
          <div className="empty-state">
            <strong>NO EXPERIMENTAL DATA for this as_of.</strong>
            <span>No stored shadow runs, artifacts, receipts, batches, or analysis artifacts. This is not observed absence of experiments in the world.</span>
          </div>
        ) : (
          <dl className="experimental-history-list">
            {history.map((entry) => (
              <div key={entry.section}>
                <dt>{entry.section}</dt>
                <dd>
                  <AvailabilityBadge label={entry.section} value={entry.availability} />
                  {entry.id ? <span> · <code>{shortId(entry.id, 16)}</code></span> : null}
                  {entry.status ? <span> · status {entry.status}</span> : null}
                  {entry.asOf ? <span> · as_of {entry.asOf}</span> : null}
                </dd>
              </div>
            ))}
          </dl>
        )}
      </section>

      <footer className="workspace-footer">
        <span>EXPERIMENTAL lens · <button type="button" className="episode-button" onClick={onBack}>back to {backLens} [x]</button></span>
      </footer>
    </div>
  );
}

export function TerminalApp({ transport }: TerminalAppProps) {
  const api = useMemo(() => createTerminalPublicReadApi(transport), [transport]);
  const filterRef = useRef<HTMLInputElement>(null);
  const snapshotRef = useRef<string | null>(null);
  const lastBaselineLensRef = useRef<PublicViewKind>("RADAR");
  const experimentalRequestRef = useRef(0);
  const [lens, setLens] = useState<TerminalLens>("RADAR");
  const [view, setView] = useState<ViewResponse | null>(null);
  const [filter, setFilter] = useState("");
  const [selectedEpisodeId, setSelectedEpisodeId] = useState<string | null>(null);
  const [inspector, setInspector] = useState<EpisodeEvidenceResponse | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [panels, setPanels] = useState<PanelKind[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [experimental, setExperimental] = useState<ExperimentalState>({ status: "idle" });
  const lensRef = useRef<TerminalLens>("RADAR");
  lensRef.current = lens;

  const visibleItems = useMemo(() => filterEpisodes(view?.items ?? [], filter), [view, filter]);
  const selectedIndex = visibleItems.findIndex((item) => item.episode_id === selectedEpisodeId);
  const topPanel = panels.at(-1) ?? null;

  const closePanel = useCallback((panel: PanelKind) => {
    setPanels((current) => current.filter((item) => item !== panel));
  }, []);

  const openPanel = useCallback((panel: PanelKind) => {
    setPanels((current) => [...current.filter((item) => item !== panel), panel]);
  }, []);

  const togglePanel = useCallback((panel: PanelKind) => {
    setPanels((current) =>
      current.includes(panel)
        ? current.filter((item) => item !== panel)
        : [...current, panel],
    );
  }, []);

  const loadView = useCallback(async (nextLens: PublicViewKind, requestedSnapshot?: string) => {
    setLoading(true);
    setError(null);
    try {
      const response = await api.view(nextLens, {
        ...(requestedSnapshot ? { snapshotId: requestedSnapshot } : {}),
        limit: 500,
      });
      if (requestedSnapshot) {
        assertSnapshotBinding(requestedSnapshot, response.snapshot.snapshot_id, "view");
      }
      const priorSnapshot = snapshotRef.current;
      const nextSnapshot = response.snapshot.snapshot_id;
      if (priorSnapshot !== null && priorSnapshot !== nextSnapshot) {
        setInspector(null);
        setHealth(null);
        setPanels([]);
      }
      snapshotRef.current = nextSnapshot;
      setView(response);
      setLens(nextLens);
      setSelectedEpisodeId(response.items[0]?.episode_id ?? null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Public intelligence request failed.");
    } finally {
      setLoading(false);
    }
  }, [api]);

  useEffect(() => {
    void loadView("RADAR");
  }, [loadView]);

  useEffect(() => {
    if (visibleItems.length === 0) {
      setSelectedEpisodeId(null);
      return;
    }
    if (!visibleItems.some((item) => item.episode_id === selectedEpisodeId)) {
      setSelectedEpisodeId(visibleItems[0]?.episode_id ?? null);
    }
  }, [selectedEpisodeId, visibleItems]);

  const inspectEpisode = useCallback(async (episodeId: string) => {
    const currentView = view;
    if (!currentView) return;
    const snapshotId = currentView.snapshot.snapshot_id;
    setError(null);
    try {
      const response = await api.episode(episodeId, snapshotId);
      assertSnapshotBinding(snapshotId, response.snapshot.snapshot_id, "episode inspector");
      setInspector(response);
      setSelectedEpisodeId(episodeId);
      openPanel("inspector");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Episode evidence request failed.");
    }
  }, [api, openPanel, view]);

  const toggleHealth = useCallback(async () => {
    if (panels.includes("health")) {
      closePanel("health");
      return;
    }
    const currentView = view;
    if (!currentView) return;
    const snapshotId = currentView.snapshot.snapshot_id;
    try {
      let nextHealth = health;
      if (!nextHealth || nextHealth.snapshot.snapshot_id !== snapshotId) {
        nextHealth = await api.health(snapshotId);
        assertSnapshotBinding(snapshotId, nextHealth.snapshot.snapshot_id, "health");
        setHealth(nextHealth);
      }
      openPanel("health");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Health request failed.");
    }
  }, [api, closePanel, health, openPanel, panels, view]);

  const moveSelection = useCallback((delta: number) => {
    if (visibleItems.length === 0) return;
    const currentIndex = selectedIndex >= 0 ? selectedIndex : 0;
    const nextIndex = Math.min(visibleItems.length - 1, Math.max(0, currentIndex + delta));
    setSelectedEpisodeId(visibleItems[nextIndex]?.episode_id ?? null);
  }, [selectedIndex, visibleItems]);

  const closeTopPanel = useCallback(() => {
    setPanels((current) => current.slice(0, -1));
  }, []);

  /**
   * Enter the EXPERIMENTAL lens. Snapshot safety: baseline view state
   * (view rows, filter, selection, inspector, panels) is never mutated; the
   * experimental fetch is bound to the currently selected snapshot as_of and
   * stale completions are discarded.
   */
  const enterExperimental = useCallback(async () => {
    const requestId = ++experimentalRequestRef.current;
    const currentView = view;
    const snapshotId = currentView?.snapshot.snapshot_id ?? null;
    setLens(EXPERIMENTAL_LENS);
    if (!currentView || !snapshotId) {
      setExperimental({
        status: "error",
        message:
          "No baseline snapshot is bound; the EXPERIMENTAL comparison needs the selected snapshot as_of.",
      });
      return;
    }
    const asOf = currentView.snapshot.as_of;
    setExperimental({ status: "loading" });
    const results = await Promise.allSettled([
      api.view("RADAR", { snapshotId }),
      api.experimentalOverview(asOf),
      api.experimentalShadowRuns(asOf),
      api.experimentalFeatureBatches(asOf),
    ]);
    if (experimentalRequestRef.current !== requestId || lensRef.current !== EXPERIMENTAL_LENS) {
      return; // superseded: the operator moved on; discard, never render stale shadow data
    }
    const [radarResult, overviewResult, runsResult, batchesResult] = results;
    const failures: string[] = [];
    let radarItems: EpisodeResponse[] | null = null;
    if (radarResult.status === "fulfilled") {
      try {
        assertSnapshotBinding(snapshotId, radarResult.value.snapshot.snapshot_id, "experimental radar baseline");
        radarItems = radarResult.value.items;
      } catch {
        failures.push("baseline RADAR view snapshot binding");
      }
    } else {
      failures.push("baseline RADAR view request");
    }
    if (overviewResult.status === "rejected") failures.push("experimental overview");
    if (runsResult.status === "rejected") failures.push("shadow-runs section");
    if (batchesResult.status === "rejected") failures.push("feature-batches section");
    if (
      overviewResult.status === "rejected" &&
      runsResult.status === "rejected" &&
      batchesResult.status === "rejected"
    ) {
      setExperimental({
        status: "error",
        message: `EXPERIMENTAL_SHADOW surfaces failed (${failures.join(" · ")}); baseline lenses remain unchanged.`,
      });
      return;
    }
    setExperimental({
      status: "ready",
      asOf,
      snapshotId,
      overview: overviewResult.status === "fulfilled" ? overviewResult.value : null,
      runsSection: runsResult.status === "fulfilled" ? runsResult.value : null,
      batchesSection: batchesResult.status === "fulfilled" ? batchesResult.value : null,
      radarItems,
      failures,
    });
  }, [api, view]);

  /** Keyboard/pointer toggle: enter EXPERIMENTAL, or leave back to the last baseline lens. */
  const toggleExperimental = useCallback(() => {
    if (lensRef.current === EXPERIMENTAL_LENS) {
      setLens(lastBaselineLensRef.current);
    } else {
      lastBaselineLensRef.current = lensRef.current;
      void enterExperimental();
    }
  }, [enterExperimental]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const command = resolveKeyboardCommand(event.key, event.target);
      if (!command) return;
      if (isEditableTarget(event.target) && command.kind === "escape") {
        (event.target as HTMLElement).blur();
        return;
      }
      event.preventDefault();
      if (command.kind === "lens") {
        if (command.lens === EXPERIMENTAL_LENS) {
          // EXPERIMENTAL never replaces baseline state: no inspector/panel reset.
          toggleExperimental();
        } else {
          setInspector(null);
          closePanel("inspector");
          void loadView(command.lens, snapshotRef.current ?? undefined);
        }
      } else if (command.kind === "next") {
        moveSelection(1);
      } else if (command.kind === "previous") {
        moveSelection(-1);
      } else if (command.kind === "inspect") {
        if (selectedEpisodeId) void inspectEpisode(selectedEpisodeId);
      } else if (command.kind === "escape") {
        closeTopPanel();
      } else if (command.kind === "filter") {
        filterRef.current?.focus();
      } else if (command.kind === "panel") {
        if (command.panel === "health") void toggleHealth();
        else togglePanel(command.panel);
      } else if (command.kind === "refresh") {
        if (lens === EXPERIMENTAL_LENS) void enterExperimental();
        else void loadView(lens, snapshotRef.current ?? undefined);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [closePanel, closeTopPanel, inspectEpisode, lens, loadView, moveSelection, selectedEpisodeId, toggleExperimental, toggleHealth, togglePanel]);

  const loadLatest = async () => {
    snapshotRef.current = null;
    setInspector(null);
    setHealth(null);
    setPanels([]);
    if (lens === EXPERIMENTAL_LENS) {
      const backLens = lastBaselineLensRef.current;
      setExperimental({ status: "idle" });
      await loadView(backLens);
      return;
    }
    await loadView(lens);
  };

  const handleFilterKeyDown = (event: ReactKeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Escape") {
      event.currentTarget.blur();
      if (filter) setFilter("");
    }
  };

  return (
    <div className="terminal-shell">
      <header className="system-strip">
        <div className="brand-lockup">
          <span className="brand-mark">FRONTIER</span>
          <span className="version-mark">TERMINAL V0</span>
        </div>
        <div className="system-binding" aria-label="Selected snapshot binding">
          <span className={lens === EXPERIMENTAL_LENS ? "lens-indicator experimental-indicator" : "lens-indicator"}>
            {lens === EXPERIMENTAL_LENS ? EXPERIMENTAL_LENS_LABEL : lens}
          </span>
          <span>as_of <code>{view?.snapshot.as_of ?? "UNBOUND"}</code></span>
          <span>snapshot <code>{view ? shortId(view.snapshot.snapshot_id, 14) : "—"}</code></span>
        </div>
        <div className="system-health" aria-label="Aggregate system health">
          {view ? (
            <>
              <StateBadge label="T" value={view.transport_state} />
              <StateBadge label="F" value={view.freshness_state} />
              <StateBadge label="C" value={view.coverage_state} />
              <StateBadge label="S" value={view.schema_state} />
            </>
          ) : <span className="muted">health unbound</span>}
        </div>
        <div className="system-actions">
          <button type="button" onClick={() => void loadLatest()}>latest snapshot</button>
          <button type="button" onClick={() => togglePanel("audit")} disabled={!view}>audit [a]</button>
          <button type="button" onClick={() => void toggleHealth()} disabled={!view}>health [h]</button>
          <button type="button" onClick={() => togglePanel("help")}>keys [?]</button>
        </div>
      </header>

      <main className="workspace">
        <nav className="lens-rail" aria-label="Public intelligence lenses">
          {LENSES.map((item, index) => (
            <button
              type="button"
              key={item}
              className={item === lens ? "active-lens" : ""}
              aria-pressed={item === lens}
              onClick={() => void loadView(item, snapshotRef.current ?? undefined)}
            >
              <span className="keycap">{index + 1}</span>
              <strong>{item}</strong>
              <small>{item === "RADAR" ? "all baseline episodes" : item === "NOW" ? "mentions_1h > 0" : "velocity_6h_delta > 0"}</small>
            </button>
          ))}
          <button
            type="button"
            className={lens === EXPERIMENTAL_LENS ? "experimental-lens active-lens" : "experimental-lens"}
            aria-pressed={lens === EXPERIMENTAL_LENS}
            onClick={toggleExperimental}
          >
            <span className="keycap">x</span>
            <strong>EXPERIMENTAL</strong>
            <small>EXPERIMENTAL_SHADOW comparison</small>
          </button>
          <div className="semantic-guard">
            <strong>BASELINE SUBSTRATE</strong>
            <span>No client rerank.</span>
            <span>No confirmation inference.</span>
            <span className="experimental-guard-line">EXPERIMENTAL lens = shadow, never authority.</span>
          </div>
        </nav>

        <section
          className={lens === EXPERIMENTAL_LENS ? "episode-workspace experimental-workspace" : "episode-workspace"}
          aria-labelledby={lens === EXPERIMENTAL_LENS ? "experimental-title" : "episode-table-title"}
        >
          <div className="workspace-toolbar">
            {lens === EXPERIMENTAL_LENS ? (
              <div>
                <p className="eyebrow">EXPERIMENTAL_SHADOW read surface · not baseline authority</p>
                <h1 id="experimental-title">
                  EXPERIMENTAL / baseline vs shadow candidate
                  <span className="experimental-badge">{EXPERIMENTAL_LENS_LABEL}</span>
                </h1>
              </div>
            ) : (
              <div>
                <p className="eyebrow">Server order · baseline rank is not objective truth</p>
                <h1 id="episode-table-title">{lens} / episode activity</h1>
              </div>
            )}
            {lens === EXPERIMENTAL_LENS ? null : (
            <div className="filter-block">
              <label htmlFor="local-filter">Local filter <kbd>/</kbd></label>
              <input
                id="local-filter"
                ref={filterRef}
                value={filter}
                onChange={(event) => setFilter(event.currentTarget.value)}
                onKeyDown={handleFilterKeyDown}
                placeholder="episode / source / role"
              />
              <span className={filter ? "filter-state active" : "filter-state"}>
                {filter ? "LOCAL FILTER" : "NO LOCAL FILTER"} · {visibleItems.length}/{view?.total ?? 0}
              </span>
            </div>
            )}
          </div>

          {lens === EXPERIMENTAL_LENS ? (
            <ExperimentalPanel
              state={experimental}
              onBack={toggleExperimental}
              backLens={lastBaselineLensRef.current}
            />
          ) : (
            <>
              {error ? <div role="alert" className="error-banner"><strong>PUBLIC INTELLIGENCE UNAVAILABLE</strong><span>{error}</span></div> : null}
              {loading ? <div role="status" className="loading-banner">Loading public read snapshot…</div> : null}
              {!loading && view && visibleItems.length === 0 ? (
                <div className="empty-state">
                  <strong>0 rows returned by {lens} for this snapshot.</strong>
                  <span>This is not a claim that nothing is happening or that evidence is absent.</span>
                </div>
              ) : null}
              {view && visibleItems.length > 0 ? (
                <EpisodeTable
                  items={visibleItems}
                  selectedEpisodeId={selectedEpisodeId}
                  onSelect={setSelectedEpisodeId}
                  onInspect={(episodeId) => void inspectEpisode(episodeId)}
                />
              ) : null}
            </>
          )}

          <footer className="workspace-footer">
            <span>j/k move · Enter inspect · h health · a audit · ? help · r refresh same snapshot · x experimental</span>
            <span>{view?.semantic_scope ?? "UNBOUND"} · policy {view?.view_policy_version ?? "—"}</span>
          </footer>
        </section>

        <aside className={`panel-deck ${topPanel ? "open" : ""}`} aria-live="polite">
          {topPanel ? <button type="button" className="panel-close" onClick={closeTopPanel} aria-label="Close top panel">×</button> : null}
          {topPanel === "inspector" && inspector ? <Inspector evidence={inspector} /> : null}
          {topPanel === "health" && health ? <HealthPanel health={health} /> : null}
          {topPanel === "audit" && view ? <AuditPanel view={view} /> : null}
          {topPanel === "help" ? <HelpPanel /> : null}
        </aside>
      </main>
    </div>
  );
}
