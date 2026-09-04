# ADR-0004 — Language-Neutral Acquisition Seam
Status: ACCEPTED_CANDIDATE

Decision: `frontier-fetch` communicates through stable semantic FetchRequest/BoundedFetchResult contracts and no Python-specific object authority. Initial implementation may be Python. Go is the preferred challenger only if measured acquisition freshness/cost/reliability fails after reasonable Python remediation.