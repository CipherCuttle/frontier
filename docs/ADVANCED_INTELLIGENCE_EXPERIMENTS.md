# ADVANCED_INTELLIGENCE_EXPERIMENTS

Status: FROZEN_EVALUATION_AUTHORITY_CANDIDATE

Parent authority: `main@e54c36f538e0f28535b853c49d62d2d6c35f5e2c`.

Promotion rule: merge of this authority PR promotes this document to `FROZEN_EVALUATION_AUTHORITY`. No follow-up status-edit commit is required.

This phase freezes the experiment and promotion authority required before any advanced ranking model may be implemented, evaluated for promotion, or exposed as canonical/public ranking authority.

It is subordinate to `docs/CONSTITUTION.md`, `docs/P03_QUALITY_ATTRIBUTES.md`, `docs/P08_DATA_CONTRACT.md`, `docs/BASELINE_INTELLIGENCE_V0.md`, and the current roadmap. If this document conflicts with higher authority, the experiment fails closed.

## Objective

Determine whether an advanced intelligence ranking model adds prospective operator value over `naive-episode-activity-v0` without sacrificing epistemic integrity.

The burden of proof is on the advanced model. Complexity has no presumption of value.

## V0 experiment class

This V0 authority governs advanced **ranking/emergence** candidates operating on the existing point-in-time episode universe produced under current grouping authority.

It does NOT authorize a new episode/entity universe, provenance-root inference, confirmation inference, manipulation verdicts, or assertion-lifecycle inference. Richer entity resolution, provenance inference, confirmation models, manipulation/reflexivity models, or other experiment classes require their own dedicated frozen sub-authority before confirmatory evaluation or promotion.

The preregistration, leakage, replay, shadow-only, and epistemic-non-escalation principles here remain constraints on later experiment classes where applicable, but this V0 promotion gate must not be misrepresented as automatic authority for them.

## Permanent comparator

The control is the retained `baseline-intelligence-v0` projection using ranking policy `naive-episode-activity-v0`.

Every confirmatory comparison MUST use:

- the same canonical episode universe;
- the same `as_of` knowledge horizon;
- the same source registry version and enabled-source set;
- the same health/coverage state available at that horizon;
- the same eligible canonical evidence available at that horizon;
- the same evaluation-domain assignment and outcome-label rules;
- the same preregistered evaluation window.

An advanced candidate may transform or derive features from evidence known by `as_of`, but it may not alter the control's inputs, remove hard cases from only one arm, or obtain a richer future-aware universe.

## Shadow-only status

Until a candidate separately passes this authority's promotion gate, every advanced output is `EXPERIMENTAL_SHADOW`.

Shadow output:

- is not canonical public ranking authority;
- must not replace the naive baseline in RADAR/NOW/TRENDING;
- must not mutate canonical observations, grouping, baseline snapshots, or public-read semantics;
- may be retained as versioned experiment artifacts for replay and evaluation;
- must carry candidate identity, candidate-freeze identity, configuration digest, input snapshot identity, `as_of`, generated time, and output digest.

No experiment may silently acquire authority merely because its code merged.

## Prospective confirmatory rule

A candidate's confirmatory evidence begins only after an immutable preregistration artifact exists in canonical repository history and that preregistration has passed one bounded hostile preregistration review.

The preregistration MUST freeze before the confirmatory window starts:

- experiment/candidate ID;
- algorithm/model version;
- full configuration digest;
- exact feature families;
- prohibited feature families;
- domain mapping;
- evaluation start condition and end condition;
- one positive integer global rank cutoff `K`, applied identically to candidate and control at every eligible snapshot;
- outcome-label definition, `resolution_at` rule, and adjudication procedure;
- exclusions applied identically to candidate and control;
- precision comparison rule;
- lead-time statistic and comparison rule;
- minimum evidence/sample adequacy rule;
- handling of missing/degraded coverage;
- deterministic tie behavior;
- multiplicity policy if more than one candidate is tested.

Changing any frozen item creates a new candidate/preregistration and restarts confirmatory evidence for that candidate.

Historical retained snapshots MAY be used for development, debugging, falsification, feature ablation, and power estimation. They MUST NOT be counted as confirmatory promotion evidence for a candidate designed or tuned after those outcomes were observable.

## Candidate freeze before confirmatory launch

Preregistration occurs before implementation, so preregistration alone cannot prove which executable candidate produced future shadow evidence.

After implementation and test, but before the first confirmatory snapshot is counted, an immutable `candidate-freeze` receipt MUST exist in canonical repository history. It binds the reviewed preregistration to the exact candidate implementation used for the confirmatory window.

The candidate-freeze receipt must make recoverable at least:

- experiment ID and candidate ID;
- preregistration artifact identity and reviewed commit SHA;
- candidate algorithm/model version and configuration digest;
- exact implementation commit SHA and repository tree SHA, or an equivalent immutable source digest if implementation is externalized later under separate authority;
- dependency/lockfile digest covering the candidate runtime dependency set;
- executable/build artifact digest when an artifact exists;
- freeze receipt schema version and deterministic receipt ID;
- freeze creation time.

The confirmatory window MUST start strictly after the candidate-freeze receipt is durable. Any change to candidate implementation source, dependency/lock identity, build artifact, algorithm/model version, or configuration after freeze creates a new candidate-freeze identity and restarts confirmatory evidence. Evidence from different freeze identities cannot be pooled as one candidate.

The candidate-freeze receipt does not itself authorize public ranking or change the preregistered evaluation rules.

## Knowledge-horizon and leakage contract

For a candidate output at `as_of = T`, every feature and relation that can influence rank or score must be reconstructible from FRONTIER knowledge with `observed_at <= T` plus configuration already frozen before T.

Forbidden leakage includes, but is not limited to:

- observations first known after T;
- later collection completion/status metadata not knowable at T;
- future source-health observations;
- labels/outcomes created after T fed back into the candidate feature path;
- future grouping/entity/provenance decisions applied retrospectively without point-in-time reconstruction;
- source publication/effective timestamps used as if FRONTIER knew them before `observed_at`;
- BACKFILL or recovered backlog converted into organic prospective activity;
- human adjudication performed after outcomes are known and then injected into the ranking inputs.

Outcome labels MAY be assigned after T for evaluation, but they are evaluator-only data and must never enter the candidate/control ranking path for that confirmatory window.

## Model-independent outcome labels

The positive-outcome definition, `resolution_at` rule, and adjudication procedure MUST be independent of both experiment arms.

They MUST NOT use candidate/control rank, score, detection time, top-K membership, model identity, or any derivative of those outputs as label-defining evidence. Later canonical or external evidence may be used to resolve an outcome only when that evidence source and resolution rule were preregistered independently of model output.

Where human adjudication is used, adjudicators MUST be blinded to candidate/control arm identity, ranks, scores, and detection times while deciding the label. If blinding cannot be established for an opportunity, that opportunity is not eligible for confirmatory promotion evidence; the exclusion and reason remain recorded rather than being silently dropped.

## V0 evaluation-domain taxonomy

P03 requires prospective advantage across multiple domains. V0 does not permit a candidate to invent arbitrary domain IDs.

The initial qualifying evaluation strata are:

- `SOFTWARE_PACKAGES`: the episode has qualifying `PRIMARY_EMISSION` evidence from `pypi.updates` and no qualifying primary-emission authority from another V0 stratum;
- `AI_MODELS`: the episode has qualifying `PRIMARY_EMISSION` evidence from `hf.models` and no qualifying primary-emission authority from another V0 stratum;
- `SECURITY_VULNERABILITIES`: the episode has qualifying `PRIMARY_EMISSION` evidence from `cisa.kev` and no qualifying primary-emission authority from another V0 stratum.

`hn.frontpage` (`ATTENTION`) and `gdelt.frontier` (`DISCOVERY`) may contribute evidence to an episode but do not assign a V0 evaluation domain.

Episodes with qualifying primary-emission authorities from more than one V0 stratum are `UNQUALIFIED_MIXED` for the multiple-domain promotion gate. Episodes with no qualifying V0 primary-emission authority are `UNQUALIFIED`. They may still be analyzed, but they cannot be used to manufacture the required domain count.

These are evaluation strata, not ontological entity/domain truth.

For V0, `multiple domains` means at least two distinct qualifying strata from the list above, with non-overlapping outcome-label populations. Post-hoc reassignment to rescue results is forbidden.

## Matched global operating point and comparable precision

V0 evaluates the actual global ranking surface. It does not create a separate authoritative per-domain ranking.

Preregistration freezes one positive integer global `K`. At every eligible evaluation snapshot:

- candidate and control rank the same full eligible episode population;
- each arm surfaces exactly the first `min(K, eligible_population_size)` episodes from its global ranking;
- the same `K` is used for candidate and control;
- no arm may abstain, threshold away hard cases, or silently change `K` after the window starts;
- deterministic tie behavior is frozen before the window.

Evaluation results are then stratified by the frozen V0 domain taxonomy without re-ranking inside a domain. Original candidate/control global ranks are preserved.

Precision uses the same positive-outcome definition and eligible opportunity population for both arms.

The V0 global precision floor is `candidate_precision >= control_precision` as a point estimate in every qualifying domain used for promotion.

The candidate-specific statistical uncertainty/non-inferiority rule and minimum sample-adequacy rule are additional preregistration requirements because label rate and opportunity frequency differ by domain. They may be stricter than the V0 global floor but MUST NOT weaken it. They cannot be chosen after confirmatory outcomes are visible.

## Lead-time advantage

For each labeled positive opportunity, `resolution_at` is frozen by the preregistered outcome-label rule.

For each arm, evaluation detection time is the earliest eligible snapshot at or before `resolution_at` where the episode enters that arm's global top `K`. If an arm never surfaces that positive opportunity by `resolution_at`, its evaluation detection time is set to `resolution_at` for lead-time arithmetic and the miss is retained explicitly in evaluation counts.

`lead_time_advantage_seconds = baseline_detection_time - candidate_detection_time`.

Positive means the candidate surfaced the event earlier. Negative means the baseline surfaced it earlier. If both arms miss by `resolution_at`, the value is zero; the opportunity is not silently dropped.

The V0 global lead-time floor is:

- median `lead_time_advantage_seconds > 0` in every qualifying domain used for promotion; and
- pooled median `lead_time_advantage_seconds > 0` across those qualifying domains.

A candidate-specific lead-time rule may be stricter but MUST NOT weaken the V0 global floor. Missing detection, ties, and window boundaries may not be excluded after outcomes are visible.

## Epistemic non-escalation

Advanced ranking authority does not automatically grant authority for any other epistemic dimension.

Unless separately authorized by a dedicated frozen contract:

- confirmation remains unavailable;
- provenance-root diversity remains unavailable;
- source count is not factual independence;
- entity identity remains no stronger than the current grouping/identity authority;
- causal origin/ancestry is not inferred;
- assertion lifecycle is not inferred;
- manipulation/reflexivity risk is not a factual manipulation verdict;
- model score is not confidence, truth probability, completeness, or importance.

The Constitution requires distinct dimensions such as emergence, confirmation, evidence confidence, coverage completeness, manipulation/reflexivity risk, and freshness. An experiment must not collapse them into one magic epistemic score.

## Candidate model constraints

The Constitution's prohibition on LLMs in canonical ranking/truth paths remains binding. LLM ranking is not authorized by this phase.

Initially unauthorized infrastructure remains unauthorized unless separately earned under constitutional reversal criteria.

Candidate features must be versioned and auditable. Hidden remote model behavior, mutable provider state, nondeterministic unseeded ranking, or paid mandatory model APIs are nonconforming.

## Experiment artifact identity

Experiment outputs are derived artifacts, not observations.

Every retained confirmatory candidate artifact must make recoverable at least:

- experiment schema version;
- experiment ID;
- candidate ID;
- candidate-freeze receipt ID;
- exact implementation commit/tree or equivalent immutable source digest;
- dependency/lockfile digest;
- executable/build artifact digest when applicable;
- candidate algorithm/model version;
- configuration digest;
- source registry version;
- input baseline snapshot ID and receipt ID;
- `as_of`;
- generated time;
- input digest;
- output digest;
- status (`COMPLETE` or `FAILED`);
- shadow-authority state (`EXPERIMENTAL_SHADOW`).

Only COMPLETE artifacts may participate in evaluation. Failed/partial candidate output cannot be interpreted as an empty ranking or a successful no-signal decision.

Frozen candidate inputs/config/version/`as_of` must replay deterministically where the candidate class is declared deterministic. Any intentionally stochastic candidate must preregister all randomness/seed semantics and prove reproducible evaluation artifacts.

## Promotion gate

A candidate receives no ranking authority unless one immutable evaluation receipt demonstrates all of the following against the preregistered confirmatory window:

1. no point-in-time/leakage violation;
2. same eligible universe/horizon as the naive comparator;
3. one candidate-freeze identity bound every counted candidate artifact and existed before the confirmatory window;
4. COMPLETE candidate/control artifacts only;
5. the same preregistered global `K`, model-independent label rules, exclusions and tie behavior remained frozen;
6. V0 point precision is at least the control precision in at least two qualifying V0 domains;
7. candidate-specific statistical precision/sample-adequacy rules PASS in each qualifying domain;
8. median lead-time advantage is strictly positive in each qualifying domain and pooled across them;
9. no hidden post-hoc domain, label, exclusion, threshold, rank-budget, candidate implementation, or candidate selection;
10. health/coverage degradation remains explicit and cannot be converted to evidence of absence;
11. no unauthorized confirmation/provenance/entity/lifecycle/truth semantics;
12. deterministic/replay requirements for the candidate class PASS;
13. preregistration hostile review was completed before the confirmatory window;
14. one hostile review of the final evaluation evidence reports no unresolved Critical/High defect.

Passing this gate does not itself change public ranking. Promotion requires a separate bounded authority change naming the winning candidate/version and its public semantics.

Failure leaves `naive-episode-activity-v0` authoritative and the advanced candidate experimental.

## Frozen hostile cases

`fixtures/advanced_intelligence/corpus_v0.json` freezes the attack surface before candidate implementation. It covers future leakage, retrospective tuning, implementation drift, model-dependent labels, universe mismatch, backfill/recovered contamination, health/coverage coercion, source-count confirmation inflation, domain cherry-picking, denominator gaming, emit-nothing precision, unequal global rank budgets, label leakage, config drift, failed-artifact interpretation, stochastic replay drift, post-hoc threshold changes, multiple-comparison winner's curse, non-independent domains, and unauthorized semantic escalation.

## Explicit exclusions from this authority PR

No advanced model implementation; no learned coefficients; no embeddings/vector database; no entity-resolution promotion; no provenance-root inference; no confirmation inference; no manipulation verdict; no public API change; no terminal ranking change; no canonical database migration; no D007 branch-protection mutation.

## Closure discipline

This authority freeze follows:

`AUTHORIZE -> PREFLIGHT -> ONE hostile authority review -> fix Critical/High -> ONE targeted re-review only if required -> VERIFY -> MERGE -> VERIFY MERGED TREE -> MOVE FORWARD`

After it merges, each concrete advanced ranking candidate follows:

`PREREGISTER -> ONE hostile preregistration review -> IMPLEMENT -> TEST -> CANDIDATE_FREEZE -> SHADOW PROSPECTIVE EVALUATION -> ONE hostile evaluation review -> fix Critical/High -> ONE targeted re-review only if required -> PROMOTION DECISION`
