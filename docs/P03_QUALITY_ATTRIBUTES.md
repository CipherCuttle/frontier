# P03 Quality Attribute Scenarios

Status: PASS_WITH_CANDIDATE_TARGETS

Priority 0: epistemic integrity, point-in-time correctness, provenance/auditability, hostile-acquisition security.
Priority 1: freshness, coverage awareness, determinism/replay, operator responsiveness, reliability/autonomy.
Priority 2: modifiability, cost control, scalability, accessibility, observability/recoverability.

Key scenarios:
- Early-signal value: advanced model must show positive prospective lead-time advantage versus naive baseline at comparable precision across multiple domains; otherwise sophisticated ranking is unauthorized.
- Syndication: 1 primary + many rewrites must preserve attention propagation while origin diversity stays low.
- Source failure: within <=2 expected collection cycles, source degradation becomes explicit; missing input must not become zero activity.
- Snapshot timeliness candidate: 99% scheduled snapshots within 5 minutes of intended non-HFT boundary.
- Materialized API read candidate: p95 server latency <250ms under healthy conditions.
- Interaction target: good Core Web Vitals responsiveness, with keyboard operations feeling substantially faster where state is local.
- Replay: frozen deterministic inputs/config/version/as_of should produce byte-identical canonical serialization.
- Retraction: old observation remains; correction/retraction appends new knowledge; historical `as_of` remains reproducible.
- Hostile fetch: forbidden network destinations and resource bombs produce 0 successful forbidden accesses.
- Failed derived processor: observations remain durable; replay is idempotent.
- Failed migration: canonical writes fail closed.
- Backfill: historical events imported today do not become live detections.
- New conventional source should not require edits to trend engine/frontend ranking/unrelated adapters.
- Autonomy: healthy deployment should not require routine weekly manual repair.

All numeric targets not externally standardized are candidate requirements until validated by measurement.