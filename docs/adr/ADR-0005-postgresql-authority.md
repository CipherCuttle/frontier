# ADR-0005 — PostgreSQL as Sole Initial State Authority
Status: ACCEPTED_CANDIDATE

Decision: PostgreSQL 18 initially stores canonical observations, derived state, source health, receipts and job coordination. Use Psycopg 3 explicit SQL. Redis/Kafka/ClickHouse/Timescale/etc require a measured failing quality attribute, attempted simpler remedies, migration cost and rollback path.