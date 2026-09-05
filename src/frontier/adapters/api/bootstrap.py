from __future__ import annotations

import os

from fastapi import FastAPI

from frontier.adapters.postgres.experimental_read import (
    PostgresExperimentalReadRepository,
)
from frontier.adapters.postgres.public_read import PostgresPublicReadRepository
from frontier.application.experimental_read import ExperimentalReadService
from frontier.application.public_read import PublicReadService

from .public_read import create_public_read_app

PUBLIC_READ_DATABASE_ENV = "FRONTIER_PUBLIC_READ_DATABASE_URL"


def create_app() -> FastAPI:
    dsn = os.environ.get(PUBLIC_READ_DATABASE_ENV)
    if not dsn:
        raise RuntimeError(f"{PUBLIC_READ_DATABASE_ENV} is required")
    repository = PostgresPublicReadRepository.connect(dsn)
    experimental_repository = PostgresExperimentalReadRepository.connect(dsn)
    app = create_public_read_app(
        PublicReadService(repository),
        experimental_service=ExperimentalReadService(experimental_repository),
    )
    app.state.public_read_repository = repository
    app.state.experimental_read_repository = experimental_repository

    def close_repositories() -> None:
        experimental_repository.close()
        repository.close()

    app.router.add_event_handler("shutdown", close_repositories)
    return app
