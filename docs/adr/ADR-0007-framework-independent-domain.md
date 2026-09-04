# ADR-0007 — Framework-Independent Domain
Status: ACCEPTED_CANDIDATE

Decision: canonical domain cannot require FastAPI, Pydantic transport models, Psycopg, HTTPX, Playwright or React. Dependency direction is domain <- application <- adapters/storage <- runtime/API/web. CI must enforce this boundary.