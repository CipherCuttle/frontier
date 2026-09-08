# GROUPING SCALABILITY V1 — GROUP-Completeness Proof

Status: IMPLEMENTATION PROOF CANDIDATE

Authority: `docs/GROUPING_SCALABILITY_V1.md`

Pinned reference:

- commit `db206cda7eed92b62c706a10089c2571b4381d66`
- tree `5134857849b03c0dcff4595c8c9fe1059ffe47a6`
- `src/frontier/domain/grouping.py` blob `943affde20b08f500f8dba2716ffedfc428f58e1`
- pair semantics `guarded-hybrid-v0`

This proof concerns candidate-generation completeness and partition equivalence only. It does not authorize a successor PEF run.

## 1. Frozen V0 GROUP clauses

After the V0 explicit-relation override, same-artifact/different-version rejection, and far-window rejection, a pair can be `GROUP` only through one of these clauses:

1. eligible explicit `CORRECTS` / `RETRACTS` relation with `authority=EXPLICIT`;
2. same canonical URL and both observations carry `ATTENTION`;
3. same canonical URL plus exact semantic text;
4. same canonical URL plus equal substantive normalized title;
5. same canonical URL plus substantive title-token Jaccard `>= 0.80`;
6. different URL plus exact semantic text, substantive titles, and distance `<= 72h`;
7. different URL plus equal substantive normalized title and distance `<= 72h`;
8. different URL plus substantive title-token Jaccard `>= 0.80` and distance `<= 72h`.

No other V0 branch returns `GROUP`.

## 2. Candidate-family coverage

### Explicit relation

Every eligible explicit relation is converted to the canonical ordered pair and inserted directly into the left observation's candidate list.

Therefore clause 1 cannot be omitted by blocking.

### Same URL

Every observation with a canonical URL is indexed by URL and observed time.

For a left observation, V1 retrieves every right observation with the same URL within `FAR_WINDOW` (30 days).

Every non-explicit V0 same-URL `GROUP` pair must survive the frozen far-window rejection. Therefore clauses 2–5 are all present in this candidate family before exact reassessment.

### Exact semantic text

Substantive-title observations are indexed by exact frozen `semantic_text(...)` and observed time.

Every different-URL exact-semantic V0 `GROUP` pair must have substantive titles and lie within `NEAR_WINDOW` (72 hours). V1 retrieves every such pair before exact reassessment.

Therefore clause 6 is complete.

### Equal normalized title

Substantive-title observations are indexed by exact frozen normalized title and observed time.

Every different-URL equal-title V0 `GROUP` pair lies within `NEAR_WINDOW`. V1 retrieves every such pair.

Therefore clause 7 is complete.

### Jaccard >= 0.80

For each substantive title token set `S`, V1 orders tokens by one deterministic global order `(document_frequency, token)` and indexes a prefix of length:

`|S| - ceil(0.80 * |S|) + 1`.

For Jaccard threshold `t`, if `Jaccard(A, B) >= t`, prefixes constructed under the same global token order must intersect. Otherwise the maximum possible overlap after disjoint prefixes is insufficient to reach the threshold.

V1 additionally applies the necessary Jaccard length bounds:

- `|B| >= ceil(0.80 * |A|)`
- `|B| <= floor(|A| / 0.80)`

and the frozen `NEAR_WINDOW`.

The prefix/length filters only remove pairs that cannot satisfy the V0 Jaccard GROUP clause. Every surviving pair is then evaluated with the exact V1 hot-path predicate, which is separately checked against the pinned V0 oracle.

Therefore clause 8 is complete.

The executable suite includes an exact-threshold `0.80` attack and bounded randomized pair/partition comparison.

## 3. Exact decision after candidate generation

Candidate generation is allowed to over-generate.

No candidate becomes a group merely because it shares a bucket or prefix. Each candidate is reassessed by the V1 hot-path GROUP predicate.

The suite requires:

- current `src/frontier/domain/grouping.py` Git blob identity equals the pinned V0 oracle blob;
- V1 hot-path GROUP result equals pinned V0 `assess_pair(...).decision == GROUP` for every frozen V0 pair case;
- bounded randomized all-pairs equality.

Thus blocking has no authority to change the final pair decision.

## 4. V0 pair-processing order

V0 constructs `group_pairs`, sorts canonical ordered observation-ID pairs lexicographically, then attempts conservative component unions in that order.

V1 iterates eligible left observation IDs in sorted order and each left candidate right-ID list in sorted order. Non-GROUP candidates are skipped.

Because candidate generation is GROUP-complete, the resulting stream of GROUP pairs has the same lexicographic order as `sorted(v0_group_pairs)` without materializing the full relation set.

## 5. Conservative clique construction

For each GROUP pair, V0 merges two current components only if every cross-component pair is also `GROUP`.

V1 performs the same check. Instead of looking up every cross pair in a precomputed N² dictionary, it evaluates the V1 hot-path GROUP predicate on demand for every cross-member pair.

Because that predicate is required to equal the pinned V0 GROUP relation, the merge predicate is identical.

Therefore, given GROUP-complete candidate generation and the same pair order, V1 produces the same episode membership partition and singleton set as V0.

No transitive relaxation is introduced.

## 6. Why omitted pairs remain epistemically safe

V1 does not write an exhaustive `ambiguous_pairs` array.

Failure to appear in the compact candidate stream is not interpreted as `NO_GROUP`, independence, provenance diversity, or confirmation.

The projection explicitly carries:

`OMITTED_PAIRS_HAVE_NO_NEGATIVE_OR_INDEPENDENCE_MEANING`

and the diagnostic `assess_pair_v1(...)` path delegates to the frozen V0 pair semantics for a requested pair.

Thus compact representation changes storage/computation, not epistemic meaning.

## 7. Receipt scalability

V0's incident failure was caused by retaining millions of ambiguous pair objects and then expanding them again into canonical dictionaries for hashing.

V1:

- never stores exhaustive ambiguous pairs;
- hashes eligible input records incrementally with length-prefixed canonical records;
- binds eligible explicit relations;
- hashes only the compact projection output;
- retains candidate/group pair counts as diagnostics rather than pair arrays.

The frozen scale workflow measures projection construction plus the exact receipt path.

## Falsifiers

This proof is invalidated if any of the following occurs:

- current V0 oracle blob differs from the pinned blob;
- any frozen V0 pair case changes GROUP/non-GROUP status under the V1 hot path;
- any bounded randomized universe produces a partition mismatch;
- the exact Jaccard 0.80 case is omitted;
- a future relation changes historical membership;
- a non-GROUP cross pair is admitted by component union;
- omitted pairs acquire negative/independence meaning;
- the receipt path recreates O(n²) canonical output;
- any frozen scale gate fails.
