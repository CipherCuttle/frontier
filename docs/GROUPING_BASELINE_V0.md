# GROUPING_BASELINE_V0 Evaluation Authority

Status: FROZEN_EVALUATION_AUTHORITY

Parent authority: `main@b5d9d8208260d3c4eccebe140531b2f47e2d355b`.

## Objective

Establish the simplest defensible deterministic projection that can say that observations
probably concern the same episode without claiming common factual ancestry, entity identity,
or independent corroboration.

This phase is grouping/deduplication only. It is not trend ranking.

## Frozen distinctions

These identifiers and concepts remain separate:

- Observation: one source emission observed by FRONTIER.
- Episode/group: a reversible FRONTIER interpretation that observations concern one occurrence.
- Provenance root: possible source ancestry/origin.
- Entity: persistent real-world/project/person/product identity.

A grouping decision MUST NOT increment factual-root independence, rewrite observation identity,
or create entity authority.

## Knowledge horizon

Only observations with `observed_at <= as_of` may enter a grouping projection.
Relations are likewise eligible only when FRONTIER had durably recorded them by `as_of`.
Source-published/effective timestamps do not grant earlier grouping knowledge.

## Frozen corpus

`fixtures/grouping/corpus_v0.json` is the V0 labeled pair authority.

It deliberately includes:

- duplicate Hacker News attention submissions;
- shared-index/catalog URLs that would cause false merges;
- same-URL revisions and far-separated URL reuse;
- exact-content mirrors;
- GDELT/discovery overlap and weak syndication ambiguity;
- PyPI/Hugging Face version splits;
- generic-title collisions;
- Unicode NFC and confusable cases;
- punctuation-sensitive aliases;
- source-time conflict cases represented only with FRONTIER observed time;
- similar-title non-equivalence.

Labels are exactly:

- `GROUP`: sufficient evidence for the baseline to join the pair;
- `NO_GROUP`: sufficient evidence for the baseline to keep the pair separate;
- `AMBIGUOUS`: evidence is insufficient; the system must retain uncertainty.

`AMBIGUOUS` is a first-class output, not a hidden failure or a forced negative.

## Candidate families

The frozen comparison set is:

1. canonical URL equality;
2. exact semantic text;
3. normalized title equality;
4. token Jaccard;
5. SimHash;
6. MinHash;
7. TF-IDF cosine;
8. a guarded transparent hybrid composed only from the same cheap observable features.

No embeddings, vector database, LLM clustering, entity resolution, or learned ranking is authorized.

## Selection rule

The corpus freezes the selection rule before runtime implementation is committed:

1. reject any candidate that creates a false merge on a frozen `NO_GROUP` or `AMBIGUOUS` case;
2. require pair precision `>= 1.000000`;
3. require group recall `>= 0.800000`;
4. among survivors, maximize group recall;
5. then minimize ambiguous outputs;
6. then prefer the lower-complexity candidate.

The implementation may not weaken labels or thresholds to rescue a candidate.

A separate selection artifact must record the frozen corpus digest, every candidate's metrics,
the selected algorithm version, and the reason for selection.

## Projection requirements

The selected projection must:

- be deterministic and versioned;
- produce deterministic group IDs from version + sorted observation IDs;
- preserve explicit ambiguous pair assessments;
- retain singleton observations rather than dropping them;
- filter by `observed_at` before feature extraction or pair comparison;
- treat correction/retraction relations as append-only knowledge rather than mutation;
- never output provenance-root counts or entity identity;
- produce a canonical projection receipt using the existing receipt primitive;
- fail closed on malformed/duplicate grouping inputs.

The initial O(n^2) pairwise implementation is acceptable for this bounded baseline only.
Sustained workload/scaling remains measured debt; optimization is not authority to change semantics.

## Required metrics / falsifiers

The phase records:

- pair precision;
- group recall;
- false merge count;
- false split count;
- ambiguous count;
- deterministic replay;
- point-in-time leakage checks.

The phase is killed or remains open if no simple candidate clears the frozen precision/recall
gate, if deterministic replay fails, if a future observation leaks into historical `as_of`,
or if grouping output collapses episode, provenance root, or entity identity.

## Explicit exclusions

No trend score, emergence/confirmation score, public API, frontend, graph database, embeddings,
vector store, LLM clustering, or provenance-root inference.
