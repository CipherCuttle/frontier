# FRONTIER DECISION VALUE + WTP V0

Status: `CANDIDATE_SUBORDINATE_AUTHORITY`

Parent authority: `FRONTIER_VALUE_OBSERVATORY_V0`.

Scientific benchmark authority: `BENCHMARK_CAPTURE_V0`.

Promotion rule: merge of the governance PR containing this document and its machine-readable preregistration promotes this protocol to `FROZEN_V0`. Until merge, no user study, pricing experiment, or product-value claim may claim conformance to this protocol.

## 1. Purpose

The Value Observatory measures whether FRONTIER surfaces consequential developments earlier than simpler comparators. That is necessary but not sufficient for product value.

This protocol freezes two additional questions before exposing results to users or prices:

1. **Decision value** — does access to a FRONTIER decision packet cause a user to make a better or faster decision than access to a simpler baseline packet?
2. **Revealed willingness to pay (WTP)** — after experiencing the product under a bounded protocol, will an unrelated user exchange real money for continued access at a preregistered price?

The protocol separates predictive skill, decision utility, and commercial demand. None may be substituted for another.

## 2. Non-escalation boundary

This protocol MUST NOT:

- mutate PEF_V1, the permanent naive baseline, `BENCHMARK_CAPTURE_V0`, or any frozen benchmark identity;
- alter canonical public ranking or create a new canonical recommendation surface;
- make an LLM a truth, identity, grouping, ranking, or outcome authority;
- expose active scored benchmark alerts before their longest registered outcome horizon matures;
- use commercial/user reactions as scientific outcome labels for the underlying Value Observatory cohort;
- count a verbal statement of willingness to pay as revealed WTP;
- personalize prices after observing an individual participant's decisions, wealth, employer, or expressed enthusiasm;
- discard participants, losses, non-purchases, refunds, or failures because they make the product look weaker;
- expose one participant to both packet variants inside the same confirmatory cohort;
- repeatedly inspect an ordinary fixed-sample interval or test and stop when it becomes favorable;
- stop a confirmatory cohort early unless a separately frozen sequential rule provides valid repeated-look error control or anytime-valid uncertainty;
- select a favorable domain, segment, pooled result, direction, or cohort after outcomes are observed and call it the primary confirmatory result;
- claim product superiority from this V0 alone.

This phase is diagnostic product research. It does not grant ranking promotion authority.

## 3. Three independent evidence loops

FRONTIER product-value evidence is partitioned into three loops:

### 3.1 Scientific loop

`SEALED EVIDENCE -> PREDICTION/RANKING -> MATURED OUTCOME -> SCORE`

Authority remains with the Value Observatory and its benchmark protocol.

### 3.2 Decision loop

`PACKET -> USER DECISION -> ACTION/ABSTAIN -> MATURED CONSEQUENCE -> UTILITY/REGRET`

This protocol governs the decision loop.

### 3.3 Market loop

`PRODUCT EXPOSURE -> FROZEN OFFER -> REAL PAYMENT DECISION -> USAGE -> RENEWAL/CANCEL`

This protocol governs the market loop.

A scientific win with no decision impact is not automatically commercially valuable. A popular product with no prospective scientific advantage is not automatically scientifically superior.

## 4. Unit of evaluation

The decision-study observation is a `decision_case` with a unique stable ID and a packet generated from evidence whose knowledge horizon is fixed before the participant sees it. Treatment assignment is at the participant level for confirmatory V0 cohorts.

Each case binds:

- case ID;
- domain;
- exact knowledge horizon;
- packet variant derived from the participant's frozen assignment;
- packet schema/protocol digest;
- evidence/benchmark artifact references needed to audit the packet;
- one frozen decision question;
- one frozen action set;
- one frozen utility function or regret rule;
- optional secondary time/confidence measurements;
- maturation rule for the decision outcome.

Decision questions and utility rules are chosen before participant response and may not be changed after the consequence is known.

## 5. Packet variants

V0 supports exactly two experimental packet classes:

1. `BASELINE_PACKET`
   - the strongest cheap/simple comparator available under the case protocol;
   - no hidden FRONTIER experimental features;
   - enough source material to make a competent decision.

2. `FRONTIER_PACKET`
   - may include the same public facts plus FRONTIER's auditable compression;
   - must expose provenance and uncertainty rather than replacing them with prose confidence;
   - must not include post-horizon information unavailable to the baseline at the same case horizon.

The comparison is invalid if one packet has a later knowledge horizon or a materially larger information budget solely because of treatment assignment.

## 6. Minimum FRONTIER decision-packet contract

A `FRONTIER_PACKET` must be capable of representing:

- **what changed**;
- **why it is unusual relative to the relevant recent baseline**;
- **first observed at / knowledge horizon**;
- **independent provenance roots and role transitions**;
- **counter-evidence, disagreement, or coverage limitations**;
- **calibrated probability or explicitly non-probabilistic uncertainty state**;
- **decision class** from a frozen action set, including `ABSTAIN` where appropriate;
- **expiry or reassessment horizon**;
- **what future observation would materially weaken or falsify the claim**;
- **audit references/digests** binding the packet to the underlying immutable evidence.

The packet is a compression layer over evidence, not a new truth authority.

## 7. Decision-study design

V0 confirmatory cohorts use randomized, blocked, **participant-level** assignment.

Rules:

- each participant is assigned exactly one of `BASELINE_PACKET` or `FRONTIER_PACKET` for the entire confirmatory cohort;
- a participant may not cross over to the other packet variant within that cohort;
- a participant sees each decision case at most once;
- assignment is blocked by participant strata frozen before enrollment, such as preregistered segment and expertise band where those strata are used;
- the case set and case-allocation policy must be the same across treatment arms, except for preregistered protocol failures;
- case order must be frozen or randomized by a treatment-independent preregistered mechanism;
- the participant is not told which packet class is the experimental treatment;
- cases used for confirmatory decision claims must be frozen before assignment;
- case or participant exclusion after assignment is allowed only for preregistered protocol failures and remains reported;
- analyses with repeated cases per participant must account for participant-level clustering or use a preregistered participant-level aggregation;
- before enrollment, the cohort must freeze either a fixed target sample size justified by power/precision analysis or an explicitly sequential design with valid repeated-look error control.

The primary comparison is intention-to-treat by participant assignment.

This participant-level V0 design deliberately gives up some within-person efficiency to prevent FRONTIER exposure from teaching framing, provenance cues, or decision strategies that could contaminate later baseline responses.

## 8. Decision estimand, metrics, multiplicity, and stopping

Every confirmatory decision cohort must freeze exactly one primary estimand before enrollment. The cohort activation artifact must bind:

- target participant population/segment;
- eligible domain/case population;
- unit of analysis;
- primary outcome/utility or regret metric;
- treatment contrast, normally `FRONTIER_PACKET - BASELINE_PACKET`;
- direction/sidedness of the confirmatory claim;
- aggregation across repeated cases, if any;
- analysis model or estimator and participant-clustering treatment;
- material-effect threshold used for the product decision;
- uncertainty interval/test and nominal error level;
- the confirmatory multiplicity family and adjustment/gatekeeping policy.

Per-domain, per-segment, per-cohort, pooled, directional, and alternate-metric claims are secondary unless they are explicitly included in the frozen confirmatory family. Unadjusted secondary analyses must be labeled exploratory and may not be promoted into the primary claim after outcomes are known.

Allowed outcome components include:

- decision correctness when a defensible binary/multiclass truth condition exists;
- expected or realized regret under a frozen cost/loss matrix;
- avoided false-positive action cost;
- avoided miss cost;
- time-to-decision;
- abstention quality;
- confidence calibration when probability estimates are elicited.

Time saved is product value only if the decision quality is not degraded beyond the preregistered tolerance.

### 8.1 Stopping semantics

The default confirmatory V0 design is fixed-sample.

If a sequential design is used, its activation artifact must freeze before enrollment:

- maximum sample size and permitted look schedule or anytime-valid monitoring rule;
- target type-I/error budget and sidedness where a hypothesis claim is made;
- an error-spending boundary, confidence sequence, or other method with documented repeated-look operating characteristics;
- futility stopping, if any;
- the exact software/method version used to compute boundaries or intervals;
- offline validation or simulation demonstrating the claimed null error/coverage behavior for the planned design.

Merely preregistering repeated use of an ordinary fixed-sample p-value or confidence interval is insufficient.

The default reporting set is:

- the frozen primary estimand and estimate;
- primary utility/regret delta between packet variants;
- decision-change rate;
- median and distribution of time-to-decision;
- false-action and missed-action burden;
- abstention rate and abstention quality;
- per-domain and pooled results labeled according to their confirmatory/exploratory status;
- all protocol failures and unresolved outcomes.

No favorable average may replace the full distribution.

## 9. Causal contamination and scientific separation

Decision/WTP experiments MUST NOT expose active scored Value Observatory alerts before the longest registered outcome horizon matures.

Eligible material for V0 user studies is therefore one of:

1. fully matured, previously shadowed observatory cases;
2. separate non-scored prospective cases created specifically for product research;
3. historical exploratory cases explicitly labeled exploratory and never reused as confirmatory evidence.

User behavior, purchases, internal sharing, or public discussion generated by this protocol are not independent downstream evidence for the scientific benchmark that generated the packet.

## 10. WTP experiment design

WTP is measured by real economic commitment, not stated preference alone.

Before the first participant receives a price offer, a subordinate content-addressed `PRICE_SCHEDULE_V0` artifact must freeze:

- schedule ID and digest;
- exact product entitlement being sold;
- billing period or fixed pilot duration;
- currency;
- whether quoted price is tax-inclusive or tax-exclusive and the applicable tax treatment;
- at least three non-zero price points for each tested segment, unless a documented feasibility constraint authorizes two;
- assignment probabilities;
- target offer count per segment/price or a valid sequential design under the rules below;
- refund/cancellation terms;
- renewal/continuation terms;
- exact definition and observation window of primary conversion;
- participant eligibility and segment assignment rules.

All price arms within one schedule test the same entitlement, duration, tax basis, refund/cancellation terms, renewal terms, and conversion definition. Only the randomized price may differ unless another factor is explicitly preregistered as a separate factorial experiment.

Each participant receives **at most one primary offer for a given entitlement under a given price schedule**. The `CommercialOfferReceiptV0` must bind participant pseudonymous ID, segment, assigned price, entitlement identity, price-schedule digest, offer time, and conversion observation window. A repeat or negotiated offer before the primary conversion outcome is recorded invalidates that participant for the primary revealed-WTP estimand but remains retained as a protocol deviation.

Price assignment is randomized within a preregistered segment. Decision performance, enthusiasm, employer, wealth, or prior response may not personalize the assigned price.

### 10.1 WTP stopping semantics

The default V0 price experiment uses fixed target offer counts per segment/price cell.

If sequential monitoring is used, the frozen price schedule must provide an anytime-valid confidence sequence, error-spending design, or other method with documented repeated-look operating characteristics for every confirmatory stopping/claim rule. It must also freeze maximum enrollment, look schedule or anytime-valid rule, error/coverage target, and offline operating-characteristic validation.

Repeatedly checking ordinary fixed-sample conversion intervals and stopping a price cell when the result becomes attractive is forbidden even if the checking cadence was written down in advance.

A participant counts as a purchase only after a real payment authorization or settled payment under the frozen offer. Coupons, founder favors, barter, internal team payments, test charges, and manually comped access do not count as revealed WTP.

Refunds and chargebacks remain visible.

## 11. Initial market segments

The first V0 market test may recruit from these product hypotheses, but each participant must be assigned to exactly one segment before pricing:

- `AI_SOFTWARE_RESEARCH_STRATEGY`;
- `TECHNICAL_DILIGENCE_INVESTMENT_RESEARCH`;
- `DEVELOPER_SECURITY_ECOSYSTEM_MONITORING`.

These are hypotheses, not product commitments. Segment-specific results must be reported separately before pooled summaries.

Adding a materially different segment requires a new preregistered segment identifier and must not rewrite prior cohorts.

## 12. WTP estimand, multiplicity, and metrics

Before the first offer, each confirmatory WTP cohort must freeze one primary commercial estimand, its target segment/population, price-schedule cells included, observation window, direction if a hypothesis claim is used, and multiplicity family/policy for any confirmatory segment-, price-, pooled-, or cohort-level claims.

The primary V0 commercial estimand should normally describe the demand curve or a prespecified function of that curve over the frozen price schedule. The highest anecdotal accepted price is not a primary estimand.

Required reporting includes:

- offer count by segment and price;
- completed real-payment conversions by segment and price;
- conversion probability with uncertainty valid for the frozen design;
- refunds/chargebacks;
- post-purchase active usage under a frozen usage definition;
- renewal or continuation when the cohort reaches the relevant boundary;
- cancellation/non-renewal;
- support/manual-intervention burden needed to obtain or retain the purchase;
- protocol deviations including repeat offers, negotiation, and failed payment attempts.

Stated WTP may be collected diagnostically but is reported separately from revealed WTP.

## 13. Decision-to-WTP linkage

The protocol should preserve whether a participant experienced measurable decision value before receiving a price offer, but decision performance must not be used to personalize the offered price.

Analysis may estimate relationships among:

- treatment assignment;
- measured decision utility;
- time saved;
- purchase probability;
- usage;
- renewal.

These relationships are diagnostic in V0 unless separately preregistered inside the confirmatory estimand/multiplicity family.

## 14. Kill criteria and interpretation

V0 is designed to support negative conclusions.

The following are valid results:

- `PREDICTIVE_VALUE_WITHOUT_DECISION_VALUE`;
- `DECISION_VALUE_WITHOUT_REVEALED_WTP`;
- `REVEALED_WTP_WITHOUT_SCIENTIFIC_SUPERIORITY`;
- `SEGMENT_SPECIFIC_VALUE_ONLY`;
- `NO_MATERIAL_VALUE_OBSERVED`.

A future product decision should strongly consider stopping or narrowing a segment when a sufficiently powered/frozen cohort shows no material decision-utility improvement and repeated real-money offers show weak demand at economically viable prices.

No threshold for commercial viability is invented in this document because cost structure and entitlement are not yet frozen. Those thresholds belong in `PRICE_SCHEDULE_V0`/cohort activation artifacts before data collection.

## 15. Required artifacts

Implementation following this governance phase should introduce immutable diagnostic artifacts equivalent to:

- `DecisionCohortActivationV0`;
- `DecisionCaseV0`;
- `DecisionResponseReceiptV0`;
- `DecisionOutcomeReceiptV0`;
- `PriceScheduleV0`;
- `CommercialOfferReceiptV0`;
- `CommercialOutcomeReceiptV0`.

Artifacts must be content-addressable/digest-bound, retain timestamps, preserve failures/nonresponse/protocol deviations, and remain outside canonical ranking authority.

The implementation phase must reuse existing canonical JSON/digest conventions where practical rather than create a parallel serialization system.

## 16. Activation preconditions

No confirmatory decision/WTP cohort may start until:

1. this protocol is merged and `FROZEN_V0`;
2. packet schemas and receipts have an independently reviewed implementation;
3. the exact case-set/case-generation protocol is frozen;
4. one primary estimand/contrast, population, direction, analysis unit, and materiality threshold are frozen;
5. confirmatory multiplicity family and adjustment/gatekeeping policy are frozen;
6. participant inclusion/exclusion rules and blocked participant-level assignment are frozen;
7. case-order/allocation, clustering/aggregation, and failure semantics are frozen;
8. fixed sample size/precision is frozen, or any sequential design has repeated-look-valid error/coverage semantics and offline operating-characteristic validation;
9. for WTP, the content-addressed `PRICE_SCHEDULE_V0` freezes the exact entitlement, price cells, currency/tax basis, duration, renewal/refund terms, one-offer rule, conversion definition/window, and offer-count/stopping design before any offer;
10. active scientific benchmark alerts remain protected from exposure contamination;
11. one independent hostile review for the bounded implementation phase is complete.

## 17. What this phase does not prove

Merge proves only that the decision/WTP experiment is preregistered.

It does not prove:

- FRONTIER predicts better;
- FRONTIER improves decisions;
- users will pay;
- a specific price is viable;
- a specific segment should be pursued;
- a new ranking candidate should be promoted.

Those claims require future-only evidence from the corresponding loop.

## 18. Research basis (informative)

This protocol is informed by:

- Dawid (1984), *Present Position and Potential Developments: Some Personal Views — Statistical Theory — The Prequential Approach*, JRSS A 147(2), 278-292. Sequential predictive systems should be judged by their observable forecasting performance rather than retrospective model stories.
- Gneiting & Raftery (2007), *Strictly Proper Scoring Rules, Prediction, and Estimation*, JASA 102(477), 359-378. Probability forecasts require proper scoring rules and calibration-sensitive evaluation.
- Diebold & Mariano (1995), *Comparing Predictive Accuracy*, Journal of Business & Economic Statistics 13(3), 253-263. Paired forecast-loss differences require comparison methods that respect their dependence structure.
- Raiffa & Schlaifer / later value-of-information literature: information has economic value only through changed decisions and expected utility under a decision problem.
- Becker, DeGroot & Marschak (1964), *Measuring utility by a single-response sequential method*, Behavioral Science 9(3), 226-232. Incentive-compatible revealed-preference methods are preferable to ungrounded hypothetical WTP claims.

These references are informative, not higher authority than repository governance.
