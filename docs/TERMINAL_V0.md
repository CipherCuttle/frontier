# TERMINAL_V0

Status: FROZEN_IMPLEMENTATION_AUTHORITY

Parent authority: `main@641cca5f0001e5e5b644f574aa09765a9d797589`.

This phase implements the first dense FRONTIER operator terminal over the already-authorized `PUBLIC_READ_PLANE_V0`. It is a disposable presentation/read client. It does not create evidence, modify projections, infer new epistemic facts, or establish a new canonical ranking.

## Objective

Give a technically literate, time-constrained operator one keyboard-first screen for the currently available substrate questions:

- what has appeared recently;
- what baseline activity is moving;
- what evidence belongs to the selected episode;
- which source roles are represented;
- what FRONTIER knew at the selected snapshot horizon;
- whether source/system health or coverage is degraded;
- which claims remain unavailable because provenance-root independence, factual confirmation, entity authority, richer lifecycle, and advanced ranking are not yet authorized.

The terminal must optimize useful operator information divided by attention and interaction cost without turning visual emphasis into hidden intelligence authority.

## Governing authority

This phase is subordinate to:

- `docs/CONSTITUTION.md`;
- `docs/P02_OPERATOR_MODEL.md`;
- `docs/P03_QUALITY_ATTRIBUTES.md`;
- `docs/P04_P05_ARCHITECTURE.md`;
- `docs/P07_GOLDEN_SCENARIOS.md`;
- `docs/PUBLIC_READ_PLANE_V0.md`;
- generated `contracts/public/openapi_v0.json` and `clients/typescript/src/generated/public_read_v0.ts`.

Where higher authority describes capabilities not yet exposed by `PUBLIC_READ_PLANE_V0`, the terminal must display the capability as unavailable rather than inventing it locally.

## Technology boundary

Authorized presentation stack:

- TypeScript with strict type checking;
- React 19;
- Vite;
- browser `fetch` behind a small transport implementing the generated `FrontierPublicReadTransport` interface;
- generated public-read client/types as the API contract authority;
- local component/UI state only.

The terminal may not directly access PostgreSQL, Python internal modules, canonical storage, source fetch endpoints, or private/undocumented API paths.

No GraphQL, Redux/global state framework, server-side rendering framework, websocket authority, analytics SDK, charting framework, component megaframework, or alternate API client generator is authorized in V0 without a measured requirement.

## Read-only boundary

The browser client may issue only GET requests to the public read plane.

No terminal code may send POST, PUT, PATCH, DELETE, mutation RPCs, canonical commands, projection runs, collection triggers, acknowledgements, watches, personalized ranking inputs, or write-side state.

Local browser interaction may change only presentation state such as selected lens, selected row, local text filter, panel visibility, and currently bound snapshot ID.

## Snapshot binding

All intelligence panels for one rendered workspace must remain bound to the same selected public snapshot.

The terminal must expose, without hover-only access:

- `snapshot_id`;
- `receipt_id`;
- `projection_version`;
- `ranking_policy_version`;
- `as_of`;
- `semantic_scope` where supplied.

Short visual forms are allowed in dense chrome, but the full values must be available through a keyboard-reachable audit panel or copyable text.

When changing snapshot binding, dependent episode/evidence/health state must be invalidated and reloaded for that snapshot. Evidence from one snapshot must never be displayed beneath another snapshot's binding.

## Lenses and rank semantics

The only V0 intelligence lenses are the public read-plane lenses:

- RADAR;
- NOW;
- TRENDING.

The terminal must consume these server outputs as-is.

Rules:

1. The server `rank` is displayed as **Baseline rank**.
2. The terminal must not recompute, rescore, weight, reorder, or merge episodes.
3. Local text filtering may hide nonmatching rows but must preserve relative server order and display an explicit `LOCAL FILTER` state.
4. Pagination/virtual presentation must preserve server order.
5. No client-side sort control is authorized in V0.
6. Color, typography, badges, animation, pinning, or row height must not imply a factual confidence/confirmation level unavailable from the response.
7. NOW and TRENDING labels describe the frozen public view policies, not a stronger product claim.

## Episode row information

A dense episode row may render only response-derived values, including:

- baseline rank;
- episode identifier in compact form;
- first/last observed time;
- age;
- mentions 1h / 6h / 24h;
- velocity 6h delta;
- acceleration 6h;
- evidence count;
- source count;
- signal roles;
- source-role diversity;
- backfill/recovered-backlog counts;
- confirmation value exactly as provided;
- evidence-root diversity exactly as provided.

A row must not synthesize a title, entity name, confidence score, trend trajectory, provenance root, independent-confirmation count, manipulation score, or factual assertion state unless a future public contract explicitly supplies it.

Because current episode projection has no canonical display title, V0 may show a compact episode ID plus evidence-derived preview text only inside the evidence/detail panel. Such preview text is evidence content, not episode/entity identity.

## Epistemic unavailable state

Current public baseline semantics include:

- `confirmation = "UNAVAILABLE"`;
- `evidence_root_diversity = null`.

The terminal must render these as explicit unavailable states. It must not convert source count, source-role diversity, multiple URLs, multiple observations, or multiple domains into factual confirmation or provenance-root independence.

Examples of forbidden labels in V0 unless directly supplied later by the public contract:

- "confirmed";
- "independently confirmed";
- "3 independent sources";
- "origin" as a definitive ancestry claim;
- entity-resolved names;
- "breakout", "mature", or other inferred lifecycle labels;
- confidence percentages.

## Health and coverage

Aggregate transport, freshness, coverage, and schema states are product data and must remain visible in the primary workspace chrome.

Requirements:

- any FAILED/DEGRADED/UNKNOWN state is visibly distinguishable from OK;
- UNKNOWN may not be styled or worded as healthy;
- the operator can open per-source health with one keyboard command from the primary workspace;
- per-source transport/freshness/completeness/schema values remain separate;
- degraded/missing coverage must not cause rows to disappear or activity to be normalized downward in the client;
- terminal copy must not equate missing evidence with observed absence.

## Evidence drill-down

Selecting an episode opens the exact public episode response for the same `snapshot_id`.

The detail surface must expose:

- selected snapshot binding;
- episode baseline metrics;
- exact observation membership returned by the endpoint;
- observation source ID and source item key;
- observation kind;
- observed/retrieved/source-published/effective times when present;
- evidence payload in a readable bounded representation;
- content/fetch digests in audit detail;
- collection occurrences including reason, recovery flag, occurrence status, and visible PIT-safe timestamps;
- observation relations returned by the public read plane.

Critical evidence and audit information must not be hover-only.

The terminal must not supplement the episode with observations from another endpoint, current-latest search, browser discovery, or another snapshot.

## Workspace layout contract

Exact styling remains experimental, but V0 must implement these stable functional regions:

1. **System strip** — application name, selected lens, selected `as_of`, aggregate health/coverage, loading/error state.
2. **Lens rail** — RADAR / NOW / TRENDING with keyboard shortcuts.
3. **Ranked episode table** — dense baseline-order rows and local filter state.
4. **Inspector** — selected episode evidence and audit binding.
5. **Health drawer/panel** — aggregate plus per-source health.
6. **Audit panel** — full snapshot/receipt/version identifiers and semantic scope.
7. **Keyboard help** — discoverable without requiring a pointer.

Desktop V0 prioritizes the dense operator workflow. Narrow screens may stack these regions but must preserve all audit and health information.

## Keyboard contract

Required commands when focus is not inside an editable field:

- `1` => RADAR;
- `2` => NOW;
- `3` => TRENDING;
- `j` or ArrowDown => next visible episode;
- `k` or ArrowUp => previous visible episode;
- `Enter` => open/focus selected episode inspector;
- `Escape` => close inspector/health/audit/help in last-opened priority;
- `/` => focus local filter;
- `h` => toggle health panel;
- `a` => toggle audit panel;
- `?` => toggle keyboard help;
- `r` => refresh the currently selected lens while preserving explicit snapshot binding when one is selected.

Keyboard commands must not fire while typing in input/textarea/select/contenteditable elements except Escape where safe.

Selection must remain visible and keyboard focus must have a visible indicator.

## Loading, empty, and failure states

The terminal fails visibly rather than optimistically.

- Initial loading must not render fabricated placeholder intelligence as real rows.
- A public API error displays an explicit error state and does not silently substitute a previous snapshot as current.
- If cached/in-memory data is retained during an explicit refresh, it must be labeled stale/loading and remain bound to its original snapshot.
- Empty result means zero rows returned by that selected public view, not "nothing is happening".
- Missing COMPLETE snapshot / integrity failure from the API must be surfaced as unavailable public intelligence.

## Local filter

V0 authorizes one optional case-insensitive local text filter over already-rendered episode fields such as episode ID, source IDs, and signal-role strings.

It must:

- never call another intelligence endpoint to expand results;
- never change row rank values;
- preserve relative server order;
- show `LOCAL FILTER` while active;
- expose count `visible / server total`;
- clear with an obvious keyboard/pointer action.

No personalized watchlist, saved filter, relevance score, hidden preference, or local ranking is authorized.

## Visual semantics

The desired visual character is a dense technical operator instrument, not a consumer news feed.

Authorized visual priorities:

- information density;
- strong typographic hierarchy;
- monospace/numeric treatment for audit IDs and metrics where useful;
- explicit state labels;
- high scanability;
- restrained motion;
- visibly distinct selection/focus;
- responsive but desktop-first panel composition.

Forbidden visual shortcuts:

- green = confirmed when confirmation is unavailable;
- source-count color scales implying truth/confidence;
- decorative gauges that combine distinct epistemic dimensions;
- unlabeled client-derived scores;
- critical state conveyed only by color;
- critical evidence conveyed only by hover.

## Accessibility baseline

V0 requires:

- semantic landmarks and headings;
- keyboard reachability for every primary function;
- visible focus;
- buttons with accessible names;
- status/error text not conveyed solely by color;
- tables/lists with appropriate semantics;
- reasonable contrast and reduced-motion respect;
- no pointer-only evidence or health affordance.

No claim of formal WCAG conformance is authorized until measured by dedicated accessibility evaluation.

## Performance candidate

The UI must not destroy the P03 responsiveness goal after the API returns.

Candidate V0 measurements:

- local lens-to-lens render after cached response: effectively immediate / no network-bound animation;
- keyboard row navigation updates synchronously from local state;
- 500 rendered fixture episodes remain usable without multi-second interaction stalls;
- no intentional animation longer than 200ms in the critical investigation path;
- production build must complete deterministically in CI from a frozen package lock.

These are terminal-phase candidate checks, not universal performance standards.

## Frozen hostile terminal scenarios

Before runtime evaluation, freeze executable/structural cases covering at least:

1. baseline rank preservation;
2. local filtering preserves rank/order;
3. confirmation UNAVAILABLE remains unavailable;
4. null evidence-root diversity remains unavailable;
5. source count does not become independent confirmation;
6. degraded aggregate health remains visible;
7. UNKNOWN coverage remains visible;
8. per-source multidimensional health remains separate;
9. selected evidence uses the same snapshot ID;
10. snapshot change invalidates incompatible inspector state;
11. API failure is explicit and does not become empty/healthy;
12. empty view does not claim observed absence;
13. only GET transport is used;
14. required keyboard lens/navigation/panel commands exist;
15. keyboard commands ignore editable targets;
16. audit identifiers are keyboard-reachable and not hover-only;
17. critical health is not color-only;
18. no unauthorized advanced semantic labels;
19. 500-row deterministic fixture does not change semantic order;
20. generated public client remains the API type authority.

## Required tests

At minimum:

- strict TypeScript compile;
- production Vite build;
- component/unit tests for lens rank preservation and local filtering;
- keyboard navigation and editable-target guards;
- unavailable epistemic-state rendering;
- aggregate/per-source health rendering;
- same-snapshot episode drill-down request;
- explicit API failure/empty states;
- structural test that terminal transport exposes GET only;
- structural test that terminal imports generated public client/types rather than reproducing the API schema manually;
- hostile frozen terminal corpus validation.

## Exclusions

TERMINAL_V0 does **not** authorize:

- advanced ranking or client reranking;
- factual confirmation inference;
- provenance-root inference;
- entity resolution;
- lifecycle inference;
- personalized feeds/watchlists;
- alerts/notifications;
- account/auth system;
- mutation endpoints;
- canonical writes;
- trading/execution actions;
- social/share mechanics;
- LLM summaries or canonical labels;
- server-side rendering;
- websocket streaming;
- new source acquisition;
- changes to baseline grouping/intelligence semantics.

## Acceptance / kill gates

The phase may close only if:

A. generated public API types are the terminal's remote contract authority;
B. terminal remote transport is GET-only;
C. server baseline rank/order survives rendering and filtering;
D. unavailable epistemic dimensions remain explicitly unavailable;
E. degraded/UNKNOWN health and coverage are visible in the main operator flow;
F. exact-snapshot episode drill-down is preserved;
G. required keyboard path works and critical information is not pointer/hover-only;
H. strict TypeScript, production build, frozen hostile corpus, existing Python verification, and terminal tests pass;
I. one independent hostile review finds no unresolved Critical/High defects after the bounded repair policy;
J. no excluded scope or new intelligence authority enters the phase.

Closure policy remains:

`IMPLEMENT -> TEST -> ONE hostile review -> repair Critical/High -> ONE targeted re-review only if required -> CLOSE -> MOVE FORWARD`
