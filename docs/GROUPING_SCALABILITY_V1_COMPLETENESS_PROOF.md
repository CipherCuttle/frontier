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

Every eligible explicit relation between two distinct eligible observations is converted to the canonical ordered pair and inserted directly into the left observation's candidate list. Eligibility uses the frozen relation authority/type rules and `created_at <= as_of`. Self-relations are excluded because V0 enumerates only pairs of distinct observations.

Therefore clause 1 cannot be omitted by blocking.

Worst case: `O(r)` relation ingestion for `r` eligible explicit relations, followed by exact pair checks for those candidates. If explicit relations themselves are dense, `r` can be `Theta(n^2)`.

### Same URL

Every observation with a canonical URL is indexed by URL and observed time. For a left observation, V1 retrieves every right observation with the same URL within `FAR_WINDOW` (30 days), inclusive at the boundary.

Every non-explicit V0 same-URL `GROUP` pair must survive the frozen far-window rejection. Therefore clauses 2–5 are all present in this candidate family before exact reassessment.

Worst case: a single homogeneous URL bucket inside the far window produces `Theta(k^2)` candidates for bucket size `k`. V1 does not claim a subquadratic worst case for this dense shape; the improvement is that candidates are streamed per left observation and exhaustive ambiguous/negative pair artifacts are not retained.

### Exact semantic text

Substantive-title observations are indexed by exact frozen `semantic_text(...)` and observed time. Every different-URL exact-semantic V0 `GROUP` pair must have substantive titles and distance `<= NEAR_WINDOW` (72 hours), inclusive at the boundary. V1 retrieves every such pair before exact reassessment.

Therefore clause 6 is complete.

Worst case: a pathological exact-semantic collision bucket inside the near window yields `Theta(k^2)` candidates.

### Equal normalized title

Substantive-title observations are indexed by exact frozen normalized title and observed time. Every different-URL equal-title V0 `GROUP` pair lies within `NEAR_WINDOW`, inclusive at 72 hours. V1 retrieves every such pair.

Therefore clause 7 is complete.

Worst case: a pathological equal-title bucket inside the near window yields `Theta(k^2)` candidates.

### Jaccard >= 0.80

For each substantive title token set `S`, V1 orders tokens by one deterministic global order `(document_frequency, token)` and indexes a prefix of length:

`|S| - ceil(0.80 * |S|) + 1`.

For Jaccard threshold `t`, if `Jaccard(A, B) >= t`, prefixes constructed under the same global token order must intersect. Otherwise the maximum possible overlap after disjoint prefixes is insufficient to reach the threshold.

V1 additionally applies the necessary Jaccard length bounds:

- `|B| >= ceil(0.80 * |A|)`
- `|B| <= floor(|A| / 0.80)`

and the frozen `NEAR_WINDOW`, inclusive at the boundary.

The prefix/length filters only remove pairs that cannot satisfy the V0 Jaccard GROUP clause. Every surviving pair is then evaluated with the exact V1 hot-path predicate.

Therefore clause 8 is complete.

Worst case: if many substantive titles share qualifying prefixes and compatible token counts inside the near window, the postings can still produce `Theta(n^2)` candidate pairs. Prefix filtering is a deterministic completeness-preserving reduction on ordinary sparse/collision-limited data, not a proof of subquadratic worst-case complexity.

## 3. Immutable reference evidence

The candidate suite binds V0 comparisons to immutable reference identities. Where it executes `assess_pair(...)`, the suite first requires the worktree `grouping.py` blob to equal the pinned V0 blob.

Reference evidence is bound in three complementary ways:

1. `fixtures/grouping/oracle_guarded_hybrid_v0.txt` is the exact Git blob `943affde20b08f500f8dba2716ffedfc428f58e1` from the pinned V0 implementation.
2. `fixtures/grouping/corpus_v0.json` is pinned to Git blob `909586dc99fe3c84ccf02f09aebe6f5ea2224b6a`; its pair inputs are replayed against the blob-pinned V0 `assess_pair(...)` reference. Historical fixture labels are not treated as the V0 oracle.
3. An isolated GitHub Actions checkout of exact commit `db206cda7eed92b62c706a10089c2571b4381d66`, after verifying the exact grouping blob, evaluated every non-empty subset of an 11-observation hostile basis. The resulting 2,047 oracle partitions are bound by aggregate SHA-256 `2184f17bfcdd1a0c6ed8df824078a55eb585b47651d493cfca61b056cde4a3ea`. The V1 suite reconstructs the same 2,047 bounded universes and must reproduce that digest exactly.

The hostile basis covers false transitivity, same-URL ATTENTION, exact Jaccard `0.80`, same-artifact version split, punctuation-sensitive conflict, and far-window separation. This is exhaustive over the bounded basis, not randomized sampling.

The suite also contains mutation attacks:

- **S15 candidate omission:** removing a known true Jaccard GROUP candidate must make the immutable-equivalence assertion fail.
- **S16 false GROUP injection:** forcing a known punctuation-conflict pair to GROUP must make the immutable-equivalence assertion fail.

Thus candidate generation and exact assessment are checked against a blob-pinned V0 pair oracle plus an independently generated immutable bounded-partition artifact, rather than fixture labels or an unguarded moving worktree.

## 4. Retained PEF_V0 membership evidence

The 11 retained successful PEF_V0 baseline snapshots from `15:00` through `15:50` UTC on 2026-09-08 were replayed through V1 using the exact retained eligible observations. The reference partition for each boundary was derived directly from its persisted frozen-V0 `baseline_intelligence_snapshots.snapshot_json` membership artifact.

GitHub Actions run `34283256979` passed all 11 boundaries with exact equality of:

- eligible observation count;
- episode/member partition count;
- sorted observation-membership partition SHA-256.

The retained artifacts are used only as equivalence evidence. They are not pooled into or treated as confirmatory evidence for any successor experiment.

## 5. V0 pair-processing order

V0 constructs `group_pairs`, sorts canonical ordered observation-ID pairs lexicographically, then attempts conservative component unions in that order.

V1 iterates eligible left observation IDs in sorted order and each left candidate right-ID list in sorted order. Non-GROUP candidates are skipped.

Because candidate generation is GROUP-complete, the resulting stream of GROUP pairs has the same lexicographic order as `sorted(v0_group_pairs)` without materializing the full relation set.

## 6. Conservative clique construction

For each GROUP pair, V0 merges two current components only if every cross-component pair is also `GROUP`.

V1 performs the same check. Instead of looking up every cross pair in a precomputed N-squared dictionary, it evaluates the V1 hot-path GROUP predicate on demand for every cross-member pair.

Because the GROUP predicate is constrained by the blob-pinned V0 pair oracle and immutable partition artifacts, the merge predicate is required to remain identical to V0. The exhaustive bounded digest includes a false-transitivity basis, and a direct hostile test requires the A-B / B-C / not-A-C shape to preserve the conservative partition.

Therefore, given GROUP-complete candidate generation and the same pair order, V1 produces the same episode membership partition and singleton set as V0. No transitive relaxation is introduced.

Worst case: for `g` candidate GROUP edges, a conservative merge attempt can inspect cross-component member pairs. A safe upper bound is `O(g * n^2)` pair-predicate work, which is `O(n^4)` in a pathological adversarial graph. Homogeneous true cliques are substantially better because successful unions and already-shared roots reduce repeated cross checks, but no stronger asymptotic guarantee is claimed. The frozen scale gates bound the operational shapes accepted by this authority.

## 7. Why omitted pairs remain epistemically safe

V1 does not write an exhaustive `ambiguous_pairs` array.

Failure to appear in the compact candidate stream is not interpreted as `NO_GROUP`, independence, provenance diversity, or confirmation. The projection explicitly carries:

`OMITTED_PAIRS_HAVE_NO_NEGATIVE_OR_INDEPENDENCE_MEANING`

The deterministic diagnostic `assess_pair_v1(...)` remains available for a requested pair. Its worktree dependency is guarded by the pinned source-blob identity. Pair-equivalence tests deliberately use that same blob-pinned V0 `assess_pair(...)` implementation as the reference, while the 2,047-case partition digest supplies an independently generated immutable membership artifact.

Thus compact representation changes storage/computation, not epistemic meaning.

## 8. Receipt scalability

V0's incident failure was caused by retaining millions of ambiguous pair objects and then expanding them again into canonical dictionaries for hashing.

V1:

- never stores exhaustive ambiguous pairs;
- hashes eligible input records incrementally with length-prefixed canonical records;
- binds eligible explicit relations;
- hashes only the compact projection output;
- retains candidate/group pair counts as diagnostics rather than pair arrays.

Preparation/index memory is linear in retained inputs plus index postings. A per-left candidate set can grow to `O(n)` in a dense bucket, but V1 does not retain an `O(n^2)` candidate/ambiguity output graph.

The frozen scale workflow measures projection construction plus the exact receipt path. The dense 5,000 same-URL ATTENTION gate additionally requires the mathematically pinned V0 result: one group, zero ungrouped observations, and exactly `n(n-1)/2` GROUP pairs. Resource success without that reference membership is a failure.

## 9. Falsifiers

This proof is invalidated if any of the following occurs:

- the vendored immutable V0 oracle fixture no longer has blob `943affde20b08f500f8dba2716ffedfc428f58e1`;
- the frozen pair corpus no longer has blob `909586dc99fe3c84ccf02f09aebe6f5ea2224b6a`;
- any blob-pinned V0 pair-corpus GROUP decision differs under V1;
- the 2,047-case exhaustive bounded partition digest differs from `2184f17bfcdd1a0c6ed8df824078a55eb585b47651d493cfca61b056cde4a3ea`;
- the S15 omission or S16 injection mutation no longer trips the equivalence guard;
- any retained 15:00–15:50 boundary membership partition differs from its persisted frozen-V0 artifact;
- the exact Jaccard 0.80 case is omitted;
- a future relation changes historical membership;
- a non-GROUP cross pair is admitted by component union;
- omitted pairs acquire negative/independence meaning;
- the receipt path recreates an O(n-squared) canonical output;
- dense 5,000 reference membership changes even if resource limits still pass;
- any frozen scale gate fails.
