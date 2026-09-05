from __future__ import annotations

import os

from fastapi import FastAPI

from frontier.adapters.postgres.public_read import PostgresPublicReadRepository
from frontier.application.public_read import PublicReadService

from .public_read import create_public_read_app

PUBLIC_READ_DATABASE_ENV = "FRONTIER_PUBLIC_READ_DATABASE_URL"


def create_app() -> FastAPI:
    dsn = os.environ.get(PUBLIC_READ_DATABASE_ENV)
    if not dsn:
        raise RuntimeError(f"{PUBLIC_READ_DATABASE_ENV} is required")
    repository = PostgresPublicReadRepository.connect(dsn)
    app = create_public_read_app(PublicReadService(repository))
    app.state.public_read_repository = repository
    app.router.add_event_handler("shutdown", repository.close)
    return app
