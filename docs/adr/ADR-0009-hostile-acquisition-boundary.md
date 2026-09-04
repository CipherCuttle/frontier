# ADR-0009 — Hostile Acquisition Trust Boundary
Status: ACCEPTED_CANDIDATE

Decision: internet retrieval occurs through `frontier-fetch`. It must treat URLs, redirects, DNS, HTML/XML/JSON, scripts and sizes as hostile. It must not hold canonical PostgreSQL/admin credentials. Browser fallback requires stronger isolation and cannot be the default acquisition method.