# FRONTIER PR-02 Source Contract Candidates V0

Status: PREFLIGHT_ONLY
Runtime authorization: NONE

These are candidate constraints for the first acquisition implementation after PR-01 closure. They do not authorize PR-02 runtime code.

## pypi.updates

- Acquisition class: A_AUTHORITATIVE_STRUCTURED
- Signal role: PRIMARY_EMISSION
- Transport: RSS over HTTPS
- Canonical discovery endpoint: `https://pypi.org/rss/updates.xml`
- Authentication: none
- Polling guidance: use RSS for periodic checks; identify FRONTIER with a stable User-Agent and avoid abusive burst traffic.
- Expected identity material: package/project name + release version + canonical release URL, subject to adapter contract.
- Primary hostile cases: malformed XML, DTD/external entities, finite feed-window gaps, duplicate items, future source timestamps, oversized canonical fields.
- Completeness rule: HTTP success and fresh feed timestamps do not prove all releases were observed when the feed window can be outrun.

## cisa.kev

- Acquisition class: A_AUTHORITATIVE_STRUCTURED
- Signal roles: PRIMARY_EMISSION, BEHAVIORAL
- Transport: JSON over HTTPS
- Canonical source: CISA KEV feed; `cisagov/kev-data` may serve as transparent mirror/history evidence, not a distinct corroborating root.
- Authentication: none
- Schema authority reviewed for this fixture corpus: `cisagov/kev-data@develop:known_exploited_vulnerabilities_schema.json`, blob `3d49b7270847e6088d8e49f5087ef5562e7917c9`.
- Expected provider-native identity: `cveID` within catalog entries.
- Primary hostile cases: missing required fields, top-level schema type drift, declared count mismatch, duplicate CVE keys, future/source-date anomalies, historical backfill.
- Completeness rule: catalog `count` must be reconciled with accepted/raw entry cardinality; mismatch degrades completeness even when JSON syntax and transport are healthy.

## Future lanes included only as preflight

### hn

ATTENTION evidence. Two HN items pointing to the same external URL are two attention observations but at most one external factual root. Deleted/dead provider state must be preserved rather than converted into synthetic article content. Additive unknown fields must not automatically break the adapter because the official v0 API explicitly permits additive fields.

### gdelt.doc

DISCOVERY evidence. Multiple GDELT article rows can represent syndication/republishing of one original assertion. URL count and propagation magnitude must therefore remain separate from independent origin count.

## Non-negotiable boundary

No source timestamp, feed position, GDELT `seendate`, HN Unix `time`, or KEV `dateAdded` may make an observation visible before trusted FRONTIER `observed_at`.

## Closure receipt

The preflight fixture authority was subjected to one hostile review. Two bounded governance defects were found and repaired: an incorrect fixture path reference and missing global case-ID uniqueness across the three packs. Final Python 3.14 preflight CI passed on candidate head `709e8b601a378e93d311d514dde2a85d81482a77` with no remaining Critical/High defect in scope.
