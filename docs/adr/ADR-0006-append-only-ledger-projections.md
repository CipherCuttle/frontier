# ADR-0006 — Append-Only Ledger + Projections
Status: ACCEPTED_CANDIDATE

Decision: acquire/validate -> append bounded canonical observation -> derive versioned projections. Downstream clustering/trend failures must not erase acquired evidence. Derived state must be replayable/idempotent where applicable; partial snapshots are never published as complete.