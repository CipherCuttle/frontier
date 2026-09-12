# FRONTIER VALUE OBSERVATORY V0

Status: `CANDIDATE_AUTHORITY`

Promotion rule: merge of the governance PR containing this document promotes this authority to `FROZEN_V0`. Until merge, no implementation may claim conformance authority from this document.

## 1. Purpose

FRONTIER has demonstrated a credible point-in-time evidence substrate, acquisition pipeline, deterministic replay/projection machinery, health semantics, receipts, a public read plane, and prospective experimental infrastructure. What remains unproven is the product-level claim that matters most:

> FRONTIER surfaces consequential emerging developments earlier than ordinary aggregation or a competent web-connected general LLM, while preserving enough provenance, uncertainty, coverage state, and historical evidence to audit that claim later.

`FRONTIER_VALUE_OBSERVATORY_V0` exists to make that claim measurable prospectively without mutating the active PEF_V1 confirmatory experiment or silently promoting any new ranking model.

This phase is an observatory and measurement authority, not a new ranking authority.

## 2. Core product thesis under test

FRONTIER's defensible value is not privileged access to secret information. Most individual public facts can also be found by search engines, analysts, or web-connected LLMs once somebody knows what to ask for.

The intended differentiator is the combination of:

- continuous public-world observation rather than one-shot question answering;
- exact `observed_at` knowledge horizons;
- append-only evidence and replayable historical state;
- source-role separation between primary emission, behavioral/discovery, attention, and confirmation;
- explicit source-health and coverage semantics;
- prospective measurement of whether an earlier weak signal later receives independent consequential evidence;
- auditable wins, losses, false alerts, and misses against ordinary discovery baselines.

A future product claim of superiority is forbidden unless supported by prospective evidence captured after the relevant benchmark protocol is frozen.

## 3. Protected active authority

PEF_V1 remains fully protected.

Frozen PEF_V1 experiment:

- experiment: `advanced-ranking-pef-v1`;
- candidate: `prospective-primary-emission-freshness-v1`;
- authority state: `EXPERIMENTAL_SHADOW`;
- ranking window start: first aligned boundary after durable candidate-freeze publication;
- effective current window: `2026-09-10T10:05:00Z` through `2026-10-08T10:05:00Z`;
- label maturation through approximately `2026-10-09T10:05:00Z`;
- no early stopping;
- no extension;
- no backfill of missed confirmatory boundaries.

This observatory MUST NOT:

- alter the PEF_V1 candidate, configuration, implementation identity, registry identity, freeze receipt, or operator authority;
- introduce a materially distinct overlapping confirmatory ranking candidate during the active PEF_V1 window without separately preregistered multiplicity authority;
- add new sources to PEF_V1 inputs;
- reinterpret a PEF_V1 PASS/FAIL/ACTIVE state;
- wire experimental observatory output into public canonical ranking;
- backfill, replay, or shift PEF_V1 confirmatory boundaries.

Observatory logic must remain observational/read-only with respect to PEF_V1 scientific state.

## 4. Primary question

For future-only observations captured under a frozen benchmark protocol:

> At the same alert budget and knowledge horizon, does FRONTIER provide useful lead time on developments that later receive independent downstream evidence, compared with a naive FRONTIER control, ordinary aggregation, and a web-connected general LLM?

The null remains viable:

> FRONTIER provides no practically useful prospective advantage over simpler discovery methods.

The project must preserve evidence that supports either conclusion.

## 5. Ten-stack design commitments

The observatory adopts the following design commitments derived from the current product architecture and the research basis listed below.

1. **Socratic / product definition** — optimize for useful early warning, not recency for its own sake.
2. **Hegelian / synthesis** — early emergence and later confirmation remain distinct; uncertainty is not collapsed away to resolve the tension.
3. **Popperian / falsifiability** — every value claim must have a prospectively captured comparator capable of defeating it.
4. **Causal inference** — public exposure caused by FRONTIER must not be counted naively as independent evidence of organic impact.
5. **Systems architecture** — signal roles and provenance roots are primary abstractions; raw source count is insufficient.
6. **Cybernetics / reflexivity** — manipulation and gaming risk are observable product dimensions, not afterthoughts.
7. **Bayesian / calibration** — future probability-style outputs must be calibratable and evaluated with proper scoring rules; subjective confidence labels alone are insufficient.
8. **MDL / information theory** — unusual change relative to a source's own baseline is more informative than raw event volume.
9. **Design of experiments** — novelty, burst, persistence, diffusion, root diversity, and related candidate features must be ablated or introduced through bounded challenger experiments rather than an opaque all-at-once score.
10. **Adversarial / red team** — all benchmark protocols must anticipate spam, mirrors, actor concentration, source outages, famous-entity activity, low-attention high-consequence events, and benchmark contamination.

## 6. Signal model direction

V0 authorizes observation and feature instrumentation for an interpretable emergence vector. It does not authorize a new canonical scalar score.

Candidate dimensions:

| Dimension | Intended meaning | V0 status |
|---|---|---|
| Novelty | how unlike recent source/domain history the episode is | instrumentation authorized |
| Burst | whether event intensity is unusually high relative to source-conditioned history | instrumentation authorized |
| Persistence | whether the signal survives successive windows instead of appearing once | instrumentation authorized |
| Diffusion | whether evidence crosses signal roles or ecosystems | instrumentation authorized |
| Root diversity | whether apparently multiple observations originate from independent provenance roots | instrumentation authorized |
| Adoption | whether independent actors begin using, referencing, implementing, or depending on the development | observational only |
| Confirmation | whether later authoritative evidence corroborates the development | observational only |
| Coverage | whether relevant outcome lanes were healthy enough to interpret silence | existing canonical health semantics retained |
| Manipulation/reflexivity | whether activity is concentrated, duplicated, mirrored, or plausibly manufactured | instrumentation authorized |
| Freshness | how old the current evidence is relative to the knowledge horizon | existing PIT semantics retained |

These dimensions must not be silently collapsed into one magic score. A later ranking candidate requires separate preregistration.

## 7. Source-role transitions

The observatory treats role transitions as higher-value evidence than undifferentiated mention counts.

Illustrative trajectory:

`PRIMARY_EMISSION -> BEHAVIORAL/DISCOVERY -> ATTENTION -> CONFIRMATION/ADOPTION`

Examples in the current registry already support this separation:

- PyPI is eligible `PRIMARY_EMISSION` evidence;
- GitHub ML repository activity is `BEHAVIORAL` / `DISCOVERY` and explicitly not factual confirmation;
- Hacker News front page is `ATTENTION`, not factual truth.

A diversity quota must not be used to cosmetically repair a dominated result page. Presentation diversity may be introduced later, but scientific/ranking evidence must remain honest about what the underlying streams actually produced.

## 8. Observatory benchmark arms

The exact execution protocol, cadence, alert budget `K`, benchmark provider/version rules, and prompt must be frozen in a subordinate `BENCHMARK_CAPTURE_V0` authority before the first scored capture that can support a product-value claim.

At minimum the observatory must support four conceptually distinct arms:

1. `FRONTIER_NAIVE_CONTROL` — the permanent simple baseline.
2. `FRONTIER_EXISTING_EXPERIMENTAL` — existing frozen experimental output such as PEF_V1, observed without modifying its authority.
3. `ORDINARY_AGGREGATION` — a simple timestamped public-discovery comparator that does not reuse FRONTIER's hidden historical state.
4. `WEB_LLM_BENCHMARK` — a timestamped, frozen-prompt web-connected general-LLM benchmark with provider/model/version, retrieval citations, exact capture time, and complete returned set retained.

The LLM benchmark is diagnostic evidence only. No LLM output may become canonical truth or ranking authority.

## 9. Equal-alert-budget rule

Cross-arm comparisons are invalid unless the comparison controls alert budget.

A future benchmark protocol must freeze:

- alert budget `K` per capture or per time unit;
- capture cadence;
- domain scope;
- selection window;
- how ties and unavailable arms are handled;
- how provider/model changes are recorded;
- how benchmark failures are treated.

A 1,000-item FRONTIER feed may not be declared superior to a 20-item LLM list merely because it contains more eventual positives.

## 10. Outcome horizons

The observatory must preserve multiple consequence horizons rather than optimizing a single attention proxy.

Initial direction:

- **~24h early attention/discovery horizon** — did independent attention or discovery emerge after the seed signal?
- **~7d behavioral/adoption horizon** — did independent actors begin using, implementing, referencing, depending on, or operationally reacting to the development?
- **~30d confirmation/impact horizon** — did slower authoritative, institutional, security, research, or ecosystem evidence establish material consequence?

Exact outcome definitions are domain-specific and must be preregistered before they support confirmatory product claims.

Hacker News appearance alone is never a universal definition of importance.

## 11. Outcome-only sidecars

V0 authorizes design of read-only/experimental outcome sidecars that are excluded from PEF_V1 inputs and cannot silently become ranking features.

High-value candidates include:

- Bluesky / ATProto attention or diffusion evidence;
- Crossref scholarly publication metadata;
- OSV structured vulnerability evidence;
- later OpenAlex research behavior/citation evidence if operational/cost constraints are acceptable.

Not every useful source should become a ranking input. Some sources are more scientifically valuable when reserved as independent outcome sensors.

Any new source requires the existing source-policy/trust-boundary review before implementation.

## 12. Cross-source stitching

The observatory authorizes deterministic, explicit cross-source relations that are already present in source metadata or resolvable without speculative semantic identity.

Preferred relations include:

- DOI <-> repository URL;
- package metadata <-> declared source repository;
- repository metadata <-> arXiv/DOI reference;
- exact canonical URL references;
- explicit dependency/reference relations.

Ambiguous identity remains a hypothesis. No LLM/entity-resolution output receives canonical identity authority from this phase.

Cross-role propagation itself is retained as a candidate signal.

## 13. Causal contamination rule

A scored observatory alert that is publicly exposed before its outcome horizon may alter the downstream attention it is attempting to measure.

Therefore a confirmatory value protocol must either:

- keep scored candidate alerts private/shadow until the outcome horizon matures; or
- explicitly model the exposure intervention and exclude contaminated outcomes from claims of organic lead-time value.

FRONTIER-caused attention may be operationally interesting but cannot be silently counted as independent validation.

## 14. Negative-label rule

Silence is not negative evidence when the relevant outcome lane was unavailable, degraded beyond its preregistered acceptance threshold, or otherwise incapable of observing the expected event.

Outcome state must distinguish at least:

- `POSITIVE`;
- `NEGATIVE_WITH_ADEQUATE_COVERAGE`;
- `UNRESOLVED_COVERAGE`.

This preserves the existing constitutional rule that missing data is not observed absence.

## 15. Product-value metrics

The observatory must be capable of reporting, without cherry-picking:

- precision / downstream-outcome yield at equal alert budget;
- miss rate against matured positive opportunities;
- lead time to first independent attention/discovery;
- lead time to later behavioral/adoption evidence;
- lead time to authoritative confirmation where defined;
- false-alert burden;
- coverage-conditioned unresolved fraction;
- wins, ties, and losses versus each comparator;
- per-domain and pooled results;
- result distributions, not only favorable averages;
- calibration/proper scores if later candidates emit probabilities.

The preferred product-facing value curve is verified useful lead time as a function of accepted false-alert burden.

No post-hoc cherry-picked showcase may substitute for the full scored population.

## 16. Required loss reporting

Every scored report must explicitly preserve:

- FRONTIER wins;
- comparator wins;
- FRONTIER misses;
- false alerts;
- unresolved outcomes;
- source/coverage failures;
- benchmark execution failures.

`FRONTIER LOST` is a first-class valid result.

A report that only contains successful case studies is not evidence under this authority.

## 17. Authorized bounded work during PEF_V1

The following work is authorized in separate bounded phases provided it remains outside PEF_V1 scientific authority and does not alter canonical public ranking:

1. `VALUE_OBSERVATORY_ARTIFACT_SCHEMA_V0`
   - immutable timestamped benchmark/capture/outcome artifact schema;
   - exact knowledge horizon and source-health bindings.

2. `SIGNAL_FEATURE_LEDGER_V0`
   - read-only calculation/storage of novelty, burst, persistence, role transition, root-diversity, manipulation, and related experimental features;
   - no public ranking authority.

3. `BENCHMARK_CAPTURE_V0`
   - freeze equal-budget protocol, cadence, prompt, provider/version recording, ordinary aggregation comparator, and failure semantics before scored capture begins.

4. `OUTCOME_SIDECARS_V0`
   - separately governed source lanes used only for outcome/diagnostic evidence unless later authority promotes them.

5. `VALUE_REPORT_V0`
   - deterministic generation of all wins/losses/misses/false alerts/unresolved cases from immutable captures.

6. `EMERGENCE_RANKING_V0`
   - explicitly NOT authorized by this document;
   - may be preregistered only through a later ranking authority after the active PEF/multiplicity boundary is handled.

## 18. Anti-overfitting discipline

Feature and candidate iteration must remain bounded.

Rules:

- no outcome-driven threshold tuning on confirmatory data;
- no repeated candidate fishing without multiplicity control;
- candidate features should be introduced through explicit challenger/ablation experiments;
- confirmatory windows must be future-only after candidate freeze;
- benchmark definitions and outcome rules must be frozen before scored use;
- historical exploratory analysis may inform a later preregistration but cannot be relabeled confirmatory.

## 19. What this phase does not authorize

This authority does NOT authorize:

- a new canonical ranking algorithm;
- a new public recommendation surface;
- an LLM in the truth/ranking path;
- embeddings/vector infrastructure;
- paid mandatory data/model APIs;
- source-registry mutation for PEF_V1;
- PEF_V1 window changes;
- public claims that FRONTIER is superior to LLMs or ordinary aggregation;
- entity/provenance promotion;
- automatic semantic entity resolution;
- outcome definitions chosen after seeing the scored results.

## 20. Completion criterion for V0

`FRONTIER_VALUE_OBSERVATORY_V0` is complete when all of the following are true:

- the artifact schema is frozen and implemented;
- benchmark capture protocol is frozen before scored captures;
- benchmark artifacts are immutable and PIT-bound;
- outcome states preserve coverage uncertainty;
- result generation deterministically reports the full population including losses;
- at least one ordinary-aggregation and one web-LLM comparator can be captured prospectively;
- no PEF_V1 or canonical-ranking authority changed;
- one independent hostile review is completed under the project bounded-completion policy.

Completion of V0 proves measurement capability only. It does not itself prove FRONTIER product superiority.

## 21. Next decision after V0

Once enough future-only observatory evidence exists, the decision owner may separately authorize either:

- `FRONTIER_VALUE_PROOF_V1` — confirmatory product-value evaluation with frozen sample adequacy and superiority/noninferiority rules; and/or
- `EMERGENCE_RANKING_V0` — a separately preregistered ranking challenger using evidence learned from observatory instrumentation.

Neither transition is automatic.

## 22. Research basis (informative, not higher authority)

This authority is informed by, but not subordinate to, the following external literature and evaluation traditions:

- Rotolo, Hicks & Martin (2015), *What is an emerging technology?*, Research Policy 44(10), 1827-1843. https://doi.org/10.1016/j.respol.2015.06.006
- Kleinberg (2002), *Bursty and Hierarchical Structure in Streams*, KDD. https://doi.org/10.1145/775047.775061
- Gneiting, Balabdaoui & Raftery (2007), *Probabilistic forecasts, calibration and sharpness*, JRSS B 69(2), 243-268. https://doi.org/10.1111/j.1467-9868.2007.00587.x
- Benjamini & Hochberg (1995), *Controlling the False Discovery Rate*, JRSS B 57(1), 289-300. https://doi.org/10.1111/j.2517-6161.1995.tb02031.x
- Foster & Stine (2008), *alpha-investing: a procedure for sequential control of expected false discoveries*, JRSS B 70(2), 429-444. https://doi.org/10.1111/j.1467-9868.2007.00643.x
- NIST Topic Detection and Tracking evaluation work, including first-story/early-event detection methodology. https://www.nist.gov/publications/topic-detection-and-tracking-evaluation-overview

These references justify design choices but do not themselves authorize implementation or alter FRONTIER governance.
