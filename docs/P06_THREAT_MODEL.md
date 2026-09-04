# P06 Threat / Failure / Manipulation Model

Status: PASS

Protection priorities: canonical observation integrity; historical `as_of` integrity; truthful coverage state; hostile acquisition isolation; algorithm/config identity; then public availability/freshness.

Failure policy states: ACCEPT, REJECT, DEGRADE, QUARANTINE, RETRY_LATER, FAIL_CLOSED.

Critical/high threats and controls:
- SSRF/DNS rebinding/internal network: isolated fetch role, scheme/IP/DNS/redirect validation, no canonical DB credentials.
- Browser compromise: disposable restricted execution, no DB/internal network/secrets.
- Credential exfiltration: least privilege, request/provider scoped secrets.
- XXE/entity expansion: external entities/DTDs disabled, bounded parsing.
- decompression/oversized-body bombs: compressed+expanded byte limits, streaming abort.
- hostile HTML/XSS: upstream HTML not rendered by default.
- source poisoning/sybil/bot/promotion: preserve source/origin concentration and manipulation/reflexivity dimensions; do not equate raw counts with confidence.
- timestamp poisoning: `observed_at` knowledge horizon.
- active-enrichment feedback: collection reason + causal trigger.
- duplicate/lost jobs: idempotency identity and durable replayable job state.
- retry storms: bounded retry budget, exponential backoff+jitter.
- partial projection/snapshot: stage/validate/atomically publish; previous complete snapshot remains current.
- schema migration mismatch: fail closed.
- disk/bloat/log exhaustion: bounded retention, graceful shedding of optional work before canonical integrity.
- backup: backup + recurring restore verification.
- canonical tampering: separated DB roles; routine worker roles do not update/delete append-only observations.
- algorithm/config drift: schema/algorithm/ranking/config/source-registry identity in receipts.
- hindsight leakage: nothing observed after `as_of` may influence that historical state.
- silent coverage loss: health accompanies/reconstructs interpretation.
- market reflexivity: behavioral evidence does not automatically become independent narrative corroboration.
- optional LLM prompt injection: outputs remain non-authoritative and cannot mutate canonical state/rank/tools.

Release blockers include canonical mutation/loss, fetch trust-boundary escape, temporal leakage, partial snapshot publication, fail-open migrations, unreproducible deterministic receipts, secret exposure, and known source failure displayed as complete healthy data.