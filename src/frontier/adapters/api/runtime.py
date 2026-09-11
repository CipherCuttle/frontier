from __future__ import annotations

import atexit
import os
from collections.abc import Callable

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from frontier.adapters.api.public_read import create_public_read_app
from frontier.adapters.postgres.public_read import PostgresPublicReadRepository
from frontier.application.public_read import PublicReadService

DATABASE_URL_ENV = "FRONTIER_PUBLIC_READ_DATABASE_URL"
CORS_ORIGINS_ENV = "FRONTIER_PUBLIC_READ_CORS_ORIGINS"
DEFAULT_CORS_ORIGINS = ("https://raw.githack.com",)


def parse_cors_origins(value: str | None) -> tuple[str, ...]:
    if value is None:
        return DEFAULT_CORS_ORIGINS
    origins = tuple(item.strip().rstrip("/") for item in value.split(",") if item.strip())
    if not origins:
        raise RuntimeError(f"{CORS_ORIGINS_ENV} must contain at least one origin")
    for origin in origins:
        if not origin.startswith("https://"):
            raise RuntimeError(f"{CORS_ORIGINS_ENV} only accepts https origins")
    return origins


def create_public_read_runtime_app(
    database_url: str,
    *,
    allowed_origins: tuple[str, ...] = DEFAULT_CORS_ORIGINS,
    repository_factory: Callable[[str], PostgresPublicReadRepository] = (
        PostgresPublicReadRepository.connect
    ),
) -> FastAPI:
    repository = repository_factory(database_url)
    if not repository.verify_read_only_session():
        repository.close()
        raise RuntimeError("public read runtime database session is not read-only")

    app = create_public_read_app(PublicReadService(repository))
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(allowed_origins),
        allow_credentials=False,
        allow_methods=["GET"],
        allow_headers=[],
    )
    atexit.register(repository.close)
    return app


def create_runtime_app_from_env() -> FastAPI:
    database_url = os.getenv(DATABASE_URL_ENV)
    if not database_url:
        raise RuntimeError(f"{DATABASE_URL_ENV} is required")
    return create_public_read_runtime_app(
        database_url,
        allowed_origins=parse_cors_origins(os.getenv(CORS_ORIGINS_ENV)),
    )
