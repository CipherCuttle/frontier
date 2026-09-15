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
- stop a confirmatory cohort early because interim outcomes look favorable or unfavorable unless a separately preregistered sequential rule explicitly authorizes that behavior;
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

The decision-study unit is a `decision_case` with a unique stable ID and a packet generated from evidence whose knowledge horizon is fixed before the participant sees it.

Each case binds:

- case ID;
- domain;
- exact knowledge horizon;
- packet variant;
- packet schema/protocol digest;
- evidence/benchmark artifact references needed to audit the packet;
- one frozen decision question;
- one frozen action set;
- one frozen primary utility function or regret rule;
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

V0 uses randomized, blocked, case-level assignment.

Rules:

- a participant sees each decision case only once;
- assignment is blocked by preregistered domain and case class when those strata exist;
- within a participant, distinct cases may be assigned across both packet variants so participant-specific skill can be modeled without showing the same case twice;
- the participant is not told which packet is the experimental treatment;
- cases used for confirmatory decision claims must be frozen before assignment;
- case exclusion after assignment is allowed only for preregistered protocol failures and remains reported;
- before enrollment, the cohort must freeze either a target sample size justified by power/precision analysis or an explicit sequential precision/stopping rule;
- absent that separately frozen sequential rule, outcome-dependent early stopping is forbidden.

The primary comparison is intention-to-treat by assigned packet variant.

## 8. Decision metrics

Every confirmatory decision cohort must freeze one primary utility/regret metric before enrollment.

Allowed outcome components include:

- decision correctness when a defensible binary/multiclass truth condition exists;
- expected or realized regret under a frozen cost/loss matrix;
- avoided false-positive action cost;
- avoided miss cost;
- time-to-decision;
- abstention quality;
- confidence calibration when probability estimates are elicited.

Time saved is product value only if the decision quality is not degraded beyond the preregistered tolerance.

The default reporting set is:

- primary utility/regret delta between packet variants;
- decision-change rate;
- median and distribution of time-to-decision;
- false-action and missed-action burden;
- abstention rate and abstention quality;
- per-domain and pooled results;
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

Before the first participant receives a price offer, a subordinate `PRICE_SCHEDULE_V0` artifact must freeze:

- product entitlement being sold;
- billing period or fixed pilot duration;
- currency;
- at least three non-zero price points for each tested segment, unless a documented feasibility constraint authorizes two;
- assignment probabilities;
- target offer count per segment/price or a preregistered precision/sequential stopping rule;
- refund/cancellation terms;
- whether tax is included;
- renewal behavior;
- exact definition of conversion.

Price assignment is randomized within a preregistered segment. One participant receives one offer for the same entitlement. There is no participant-level renegotiation before the primary conversion outcome is recorded.

Unless the frozen price schedule contains an explicit sequential rule, price-cell enrollment may not stop early in response to observed conversions or non-conversions.

A participant counts as a purchase only after a real payment authorization or settled payment under the frozen offer. Coupons, founder favors, barter, internal team payments, test charges, and manually comped access do not count as revealed WTP.

Refunds and chargebacks remain visible.

## 11. Initial market segments

The first V0 market test may recruit from these product hypotheses, but each participant must be assigned to exactly one segment before pricing:

- `AI_SOFTWARE_RESEARCH_STRATEGY`;
- `TECHNICAL_DILIGENCE_INVESTMENT_RESEARCH`;
- `DEVELOPER_SECURITY_ECOSYSTEM_MONITORING`.

These are hypotheses, not product commitments. Segment-specific results must be reported separately before pooled summaries.

Adding a materially different segment requires a new preregistered segment identifier and must not rewrite prior cohorts.

## 12. WTP metrics

Required reporting includes:

- offer count by segment and price;
- completed real-payment conversions by segment and price;
- conversion probability with uncertainty;
- refunds/chargebacks;
- post-purchase active usage under a frozen usage definition;
- renewal or continuation when the cohort reaches the relevant boundary;
- cancellation/non-renewal;
- support/manual-intervention burden needed to obtain or retain the purchase.

The primary V0 commercial metric is the observed demand curve over the frozen price schedule, not the highest anecdotal price accepted by one buyer.

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

These relationships are diagnostic in V0 unless separately preregistered as confirmatory hypotheses.

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

- `DecisionCaseV0`;
- `DecisionResponseReceiptV0`;
- `DecisionOutcomeReceiptV0`;
- `PriceScheduleV0`;
- `CommercialOfferReceiptV0`;
- `CommercialOutcomeReceiptV0`.

Artifacts must be content-addressable/digest-bound, retain timestamps, preserve failures/nonresponse, and remain outside canonical ranking authority.

The implementation phase must reuse existing canonical JSON/digest conventions where practical rather than create a parallel serialization system.

## 16. Activation preconditions

No confirmatory decision/WTP cohort may start until:

1. this protocol is merged and `FROZEN_V0`;
2. packet schemas and receipts have an independently reviewed implementation;
3. the exact case-set/case-generation protocol is frozen;
4. the primary decision utility/regret metric is frozen;
5. participant inclusion/exclusion rules are frozen;
6. randomization and failure semantics are frozen;
7. target sample size/precision and stopping semantics are frozen before enrollment or offers;
8. for WTP, `PRICE_SCHEDULE_V0` is frozen before any offer;
9. active scientific benchmark alerts remain protected from exposure contamination;
10. one independent hostile review for the bounded implementation phase is complete.

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
