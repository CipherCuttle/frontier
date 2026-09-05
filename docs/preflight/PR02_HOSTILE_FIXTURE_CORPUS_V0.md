# FRONTIER PR-02 Hostile Acquisition Fixture Corpus V0

Status: PREFLIGHT_FIXTURE_CORPUS_V0
Parent authority: main@8a5eb774bb462e41ce558de99ed3de53f62da499
Runtime implementation authorized by this branch: NO

This corpus exists before PR-02 implementation so the acquisition layer is tested against known failure modes instead of being designed around happy-path responses.

## Rules

- Fixtures are synthetic unless explicitly marked as an upstream schema snapshot.
- No fixture requires live network access.
- XXE/entity-expansion fixtures are inert text fixtures; tests must reject them before external resolution/expansion.
- A syntactically valid response can still produce DEGRADE or QUARANTINE when completeness, source identity, or contract integrity fails.
- ACCEPT never means the external claim is true; it means the acquisition/normalization boundary may admit a bounded observation under the source role.
- `observed_at` remains trusted FRONTIER knowledge time. Source timestamps never grant retroactive knowledge.
- Discovery/attention duplicates must preserve propagation while not manufacturing independent factual roots.

## Source lanes

PR-02 V0 candidates:
- `pypi.updates` — official PyPI RSS, PRIMARY_EMISSION.
- `cisa.kev` — official CISA KEV JSON, PRIMARY_EMISSION + BEHAVIORAL.

Future lanes preflighted here but not authorized for PR-02 V0 runtime:
- `hn` — official Hacker News Firebase, ATTENTION.
- `gdelt.doc` — GDELT DOC ArtList, DISCOVERY.
- `fixture.http` — transport/security behavior only.

## Outcome vocabulary

- ACCEPT — valid bounded acquisition input; downstream semantics still apply.
- REJECT — reject this payload/request without treating the source as globally unusable.
- DEGRADE — source health/coverage degrades; affected evidence is incomplete or invalid.
- QUARANTINE — stop trusting new source output until contract/operator recovery.
- RETRY_LATER — transient provider/transport condition with retry budget.
- FAIL_CLOSED — canonical write/startup path must stop.

`fixtures/acquisition/manifest_v0.json` is the machine-readable case authority.
