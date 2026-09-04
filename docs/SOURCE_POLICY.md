# FRONTIER Source Policy V0

Every production source must pass four gates:
1. Technical — reproducible autonomous access.
2. Policy — intended access/caching/retention/extraction/display/attribution use permitted.
3. Information value — adds nonredundant information.
4. Reliability — can degrade without breaking FRONTIER.

Acquisition classes:
A_AUTHORITATIVE_STRUCTURED — official API/feed/bulk data.
B_OPEN_AGGREGATION — open aggregation/discovery/archive.
C_PERMITTED_EXTRACTION — FRONTIER-operated direct extraction from permitted public resource.
D_FRAGILE_UI_EXTRACTION — rendered third-party UI extraction.

Class D may be supplemental but must never be critical infrastructure.

Signal roles are separate from acquisition class: PRIMARY_EMISSION, DISCOVERY, ATTENTION, BEHAVIORAL, CORROBORATION.

Examples: GDELT is B + DISCOVERY, not automatically independent corroboration. HN may be authoritative for HN activity while remaining ATTENTION evidence about an external event. A provider's technical authority over its own emitted data does not make all claims true.

Source policy must capture expected cadence, transport, authentication/credential reference, raw/extracted retention, public excerpt mode, attribution obligations, browser authorization, failure/stale behavior, and whether it may serve as primary evidence.

No access-control circumvention, CAPTCHA bypass, paywall bypass, stealth/proxy evasion, or unauthorized anti-bot work is allowed.