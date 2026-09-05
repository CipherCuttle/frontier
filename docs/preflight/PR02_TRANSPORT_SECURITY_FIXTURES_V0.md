# FRONTIER PR-02 Transport / Security Hostile Fixture Pack V0

**Status:** `PREFLIGHT_TRANSPORT_SECURITY_FIXTURES_V0`

**Parent preflight head:** `be258e18a27d2966c8296734c12be13f5e56750a`

**Runtime implementation authorized:** NO

This pack exists so the future `frontier-fetch` implementation is written against failure semantics before it makes real network requests.

## Scope

The fixture pack covers transport/security behavior only. It does not implement networking, retry loops, scheduling, parsing, source adapters, or trend logic.

Cases:

- `TS-001` DNS rebinding: public address at policy check, private address at connect time.
- `TS-002` IPv6 loopback.
- `TS-003` IPv6 link-local.
- `TS-004` cloud-metadata IPv4 target.
- `TS-005` IPv4-mapped IPv6 private target.
- `TS-006` unsupported `file://` scheme.
- `TS-007` redirect loop / redirect-budget exhaustion.
- `TS-008` cross-origin redirect must not forward Authorization credentials.
- `TS-009` compressed-body expansion bomb.
- `TS-010` lying `Content-Length` followed by an oversized stream.
- `TS-011` MIME lie: HTML login/interstitial returned as RSS.
- `TS-012` slow/stalled response body exceeding request deadline.
- `TS-013` truncated response body.
- `TS-014` HTTP 429 with usable `Retry-After`.
- `TS-015` absurdly large `Retry-After` that must not grant a provider unbounded scheduling authority.
- `TS-016` HTTP 304 with no local cached entity.
- `TS-017` inconsistent validator: unchanged ETag but changed bytes.
- `TS-018` source recovery backlog delivered as a burst after a two-hour outage.

## Frozen fixture semantics

### Network destination validation

A textual hostname is not sufficient authorization for a connection. The actual destination address used for the connection must remain permitted after DNS resolution and redirect handling.

The fixture contract therefore requires zero connections to loopback, private, link-local or metadata targets, including IPv4-mapped IPv6 forms.

### Redirect credentials

Source credentials are least privilege. A redirect to a different origin must not implicitly forward source Authorization credentials.

### Resource bounds

`Content-Length` is advisory input, not a resource-control boundary. Both streamed bytes and expanded/decompressed bytes remain bounded independently.

A parser or fetcher is never required to buffer the entire hostile body in order to decide that it exceeds policy.

### MIME and schema are separate from transport

An HTTP request can succeed while returning the wrong semantic resource. `TS-011` intentionally has transport health `OK` and schema health `DEGRADED`.

This preserves the P07 rule that source health is multidimensional.

### Timeouts and partial bodies

A request deadline bounds wall-clock acquisition. A timed-out or truncated body cannot become a canonical Observation merely because some bytes were received successfully.

### Retry authority

`Retry-After` should influence scheduling when valid, but it does not grant the provider unlimited control over FRONTIER's future work queue. Retry budgets and source-health visibility remain bounded system policy.

### Validators and cache state

`304 Not Modified` is meaningful only relative to an existing local representation. A `304` with no cached entity must fail closed rather than manufacture an Observation.

ETag/Last-Modified metadata is useful but not metaphysical truth. If bytes demonstrably change while a validator is unchanged, the inconsistency must be visible.

### Recovery bursts

A delivery burst after an outage is not automatically a real-world emergence burst.

Recovered observations retain their source/effective times and collection context, with `recovered_after_gap=true` or equivalent semantics, so later trend logic can distinguish delayed delivery from organic acceleration.

## Kill conditions for future PR-02

Any future implementation fails the transport/security gate if it can:

1. connect to a forbidden internal/metadata destination through direct URL, redirect, DNS rebinding or IPv4-mapped IPv6;
2. forward source credentials across an unauthorized origin boundary;
3. exceed configured compressed, expanded, streamed or deadline bounds;
4. treat HTTP success as semantic source health;
5. publish partial/truncated response content as canonical evidence;
6. retry immediately or without bounded budget during 429/5xx storms;
7. create content from a `304` response when no cached representation exists; or
8. classify an outage-recovery delivery burst as a live breakout solely because the backlog arrived quickly.

## Relationship to PR #2

None. PR #2 remains parked. This preflight branch is based directly on frozen `main` and contains only fixtures, documentation and fixture validation.
