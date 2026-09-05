# ADVANCED_INTELLIGENCE_EXPERIMENTS

Status: FROZEN_EVALUATION_AUTHORITY_CANDIDATE

Parent authority: `main@e54c36f538e0f28535b853c49d62d2d6c35f5e2c`.

This phase freezes the experiment and promotion authority required before any advanced ranking model may be implemented, evaluated for promotion, or exposed as canonical/public ranking authority.

It is subordinate to `docs/CONSTITUTION.md`, `docs/P03_QUALITY_ATTRIBUTES.md`, `docs/P08_DATA_CONTRACT.md`, `docs/BASELINE_INTELLIGENCE_V0.md`, and the current roadmap. If this document conflicts with higher authority, the experiment fails closed.

## Objective

Determine whether an advanced intelligence model adds prospective operator value over `naive-episode-activity-v0` without sacrificing epistemic integrity.

The burden of proof is on the advanced model. Complexity has no presumption of value.

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
- must carry candidate identity, configuration digest, input snapshot identity, `as_of`, generated time, and output digest.

No experiment may silently acquire authority merely because its code merged.

## Prospective confirmatory rule

A candidate's confirmatory evidence begins only after an immutable preregistration artifact exists in canonical repository history.

The preregistration MUST freeze before the confirmatory window starts:

- experiment/candidate ID;
- algorithm/model version;
- full configuration digest;
- exact feature families;
- prohibited feature families;
- domain mapping;
- evaluation start condition and end condition;
- candidate decision/rank operating point;
- control decision/rank operating point;
- outcome-label definition and adjudication procedure;
- exclusions applied identically to candidate and control;
- precision comparison rule;
- lead-time statistic and comparison rule;
- minimum evidence/sample adequacy rule;
- handling of missing/degraded coverage;
- tie behavior;
- multiplicity policy if more than one candidate is tested.

Changing any frozen item creates a new candidate/preregistration and restarts confirmatory evidence for that candidate.

Historical retained snapshots MAY be used for development, debugging, falsification, feature ablation, and power estimation. They MUST NOT be counted as confirmatory promotion evidence for a candidate designed or tuned after those outcomes were observable.

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

## Domain requirement

P03 requires prospective advantage across multiple domains. For this authority, `multiple domains` means at least two distinct preregistered domain IDs with non-overlapping outcome-label populations.

A domain is an evaluation stratum, not a source count. Multiple feeds carrying the same event do not manufacture multiple domains or multiple truths.

Domain assignment must be deterministic from information available under the preregistered evaluation contract. Post-hoc reassignment to rescue results is forbidden.

## Comparable precision

A candidate may not obtain apparent lead time by emitting a much larger, noisier alert/rank surface than the control.

Each preregistration must freeze matched operating points before confirmatory evaluation. At those operating points:

- candidate and control are evaluated on the same eligible opportunity set;
- precision uses the same positive-outcome definition;
- an `emit nothing` candidate cannot pass;
- a candidate cannot drop difficult opportunities from its denominator;
- a candidate cannot claim comparable precision if its preregistered precision rule fails in either qualifying domain.

The exact statistical/non-inferiority rule and minimum sample adequacy are candidate-specific preregistration fields because label rate and opportunity frequency differ by domain. They cannot be chosen after confirmatory outcomes are visible.

## Lead-time advantage

For an eventual positive outcome, detection time is the earliest eligible snapshot in the confirmatory window where the preregistered operating point surfaces that episode.

`lead_time_advantage_seconds = baseline_detection_time - candidate_detection_time`.

Positive means the candidate surfaced the event earlier. Negative means the baseline surfaced it earlier.

Lead-time comparison is computed only under the preregistered label/matching policy. Missing detection, censoring, ties, and window-boundary handling must be frozen before evaluation.

A model is not promotable unless the preregistered lead-time rule is strictly positive in every domain used to satisfy the multiple-domain gate while the precision rule also passes there.

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
3. COMPLETE candidate/control artifacts only;
4. preregistered operating points and label rules unchanged;
5. comparable-precision rule PASS in at least two qualifying domains;
6. strictly positive preregistered lead-time rule PASS in each of those domains;
7. sample-adequacy rule PASS in each qualifying domain;
8. no hidden post-hoc domain, label, exclusion, threshold, or candidate selection;
9. health/coverage degradation remains explicit and cannot be converted to evidence of absence;
10. no unauthorized confirmation/provenance/entity/lifecycle/truth semantics;
11. deterministic/replay requirements for the candidate class PASS;
12. one hostile review of the evaluation evidence reports no unresolved Critical/High defect.

Passing this gate does not itself change public ranking. Promotion requires a separate bounded authority change naming the winning candidate/version and its public semantics.

Failure leaves `naive-episode-activity-v0` authoritative and the advanced candidate experimental.

## Frozen hostile cases

`fixtures/advanced_intelligence/corpus_v0.json` freezes the attack surface before candidate implementation. It covers future leakage, retrospective tuning, universe mismatch, backfill/recovered contamination, health/coverage coercion, source-count confirmation inflation, domain cherry-picking, denominator gaming, emit-nothing precision, alert-budget mismatch, label leakage, config drift, failed-artifact interpretation, stochastic replay drift, post-hoc threshold changes, multiple-comparison winner's curse, non-independent domains, and unauthorized semantic escalation.

## Explicit exclusions from this authority PR

No advanced model implementation; no learned coefficients; no embeddings/vector database; no entity-resolution promotion; no provenance-root inference; no confirmation inference; no manipulation verdict; no public API change; no terminal ranking change; no canonical database migration; no D007 branch-protection mutation.

## Closure discipline

This authority freeze follows:

`AUTHORIZE -> PREFLIGHT -> VERIFY -> MERGE -> VERIFY MERGED TREE -> MOVE FORWARD`

After it merges, each concrete advanced candidate follows the normal bounded completion policy:

`PREREGISTER -> IMPLEMENT -> TEST -> SHADOW PROSPECTIVE EVALUATION -> ONE hostile review -> fix Critical/High -> ONE targeted re-review only if required -> PROMOTION DECISION`
