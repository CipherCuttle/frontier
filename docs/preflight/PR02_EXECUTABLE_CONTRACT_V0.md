# FRONTIER PR-02 Executable Contract V0

Status: `PREFLIGHT_ONLY`

Runtime implementation authorized: **NO**

Parent: `main@4f8f6f8ad895d5a515dbd592f9386617d43d8f4d`

## Objective

Turn the frozen PR-02 acquisition/source prose into machine-readable contracts before any live socket, HTTP client, scheduler, parser runtime, or canonical database write is implemented.

This package defines the JSON interchange profile for `FetchRequest`, `BoundedFetchResult`, fetch policy bounds, `SourceContract`, and the first source registry containing `pypi.updates` and `cisa.kev`.

It does not implement `frontier-fetch`.

## Authority relationship

`docs/P08_DATA_CONTRACT.md` remains semantic authority. These JSON Schemas are the first executable serialization profile of that authority. Where this preflight package conflicts with P08, P08 wins until a later reviewed governance change explicitly promotes a replacement.

Operational `request_id` remains noncanonical. Fetch-runtime `retrieved_at` and `body_digest` are telemetry/advisory; trusted ingestion must timestamp boundary crossing and recompute SHA-256 over exact returned body bytes before canonical use.

`body_base64` exists only because this preflight uses JSON as the interchange representation. The semantic fetch result still carries bounded opaque bytes.

## Initial source registry

### `pypi.updates`

Official Latest Updates RSS: `https://pypi.org/rss/updates.xml`

PyPI documents RSS as the preferred interface for periodically checking new packages/updates, and documents ETag support on RSS/JSON/Index APIs. The source is therefore A_AUTHORITATIVE_STRUCTURED + PRIMARY_EMISSION.

### `cisa.kev`

Official KEV JSON: `https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json`

Schema: `https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities_schema.json`

The existing preflight authority pins the reviewed CISA schema mirror blob `3d49b7270847e6088d8e49f5087ef5562e7917c9`.

The source is A_AUTHORITATIVE_STRUCTURED + PRIMARY_EMISSION + BEHAVIORAL.

## Security invariants

The executable preflight fails if V0 authorizes non-GET/non-HTTPS access; embeds plaintext-secret-shaped fields or database coordinates; gives a zero-key source a credential ref; enables browser acquisition for PyPI/CISA; omits private/loopback/link-local/metadata address classes; forwards Authorization cross-origin; removes bounded redirect/body/deadline/retry budgets; enables a source whose access state is not ALLOWED; changes the registry without changing its canonical digest; or ships a golden result whose body digest disagrees with its decoded bytes.

## Bounds

`structured-public-v0` is a candidate bounded profile, not a global performance claim: HTTPS only; 3 redirects; 15 s total deadline; 5 s connect/read-idle bounds; 8 MiB response bound; 16 MiB expanded-body bound; 64 KiB header bound; 3 retry attempts; Retry-After capped at one hour; retry implementations require jitter.

Measured PR-02 behavior may tighten these values. Relaxing a security bound requires explicit review against the merged hostile transport fixture authority.

## Source registry version

`sha256:ef82b1eda707621aef63dbf77fea088faaf520a713aa47acd0e5696cf9468582`

This is SHA-256 over `frontier-canonical-json-v1` serialization of the two source contracts sorted by `source_id`.

## Explicit exclusions

No HTTPX/live network calls, DNS resolution, sockets, RSS/XML parser runtime, KEV parser runtime, scheduler, retry implementation, PostgreSQL access, canonical Observation writes, source-health persistence, FastAPI/UI, trend/ranking logic, or changes to parked PR #2.

## Closure gate

This preflight closes when the stdlib validator passes on Python 3.14 and one hostile review finds no Critical/High ambiguity that would allow two incompatible PR-02 fetch/source implementations to both claim compliance.
