# ADR-0002 — Modular Monolith
Status: ACCEPTED_CANDIDATE

Decision: one repository/application authority with runtime roles such as `frontier-fetch`, `frontier-worker`, `frontier-api`, static web and PostgreSQL. Process boundaries for security/fault isolation do not imply microservices. Split only when a module demonstrates independent scaling/deployment requirements that cannot reasonably be met inside the monolith.