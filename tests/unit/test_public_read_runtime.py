from __future__ import annotations

from typing import cast

import pytest

from frontier.adapters.api.runtime import (
    CORS_ORIGINS_ENV,
    DATABASE_URL_ENV,
    DEFAULT_CORS_ORIGINS,
    create_public_read_runtime_app,
    create_runtime_app_from_env,
    parse_cors_origins,
)
from frontier.adapters.postgres.public_read import PostgresPublicReadRepository


class _RuntimeRepository(PostgresPublicReadRepository):
    def __init__(self, *, read_only: bool = True) -> None:
        self.read_only = read_only
        self.closed = False

    def verify_read_only_session(self) -> bool:
        return self.read_only

    def close(self) -> None:
        self.closed = True


def test_runtime_exposes_only_get_public_contract_and_uses_requested_repository() -> None:
    repository = _RuntimeRepository()
    seen_dsn: list[str] = []

    def repository_factory(dsn: str) -> PostgresPublicReadRepository:
        seen_dsn.append(dsn)
        return repository

    app = create_public_read_runtime_app(
        "postgresql://example.invalid/frontier",
        repository_factory=repository_factory,
    )
    document = cast(dict[str, object], app.openapi())
    paths = cast(dict[str, dict[str, object]], document["paths"])
    assert set(paths["/v0/meta"]) == {"get"}
    assert set(paths["/v0/radar"]) == {"get"}
    assert seen_dsn == ["postgresql://example.invalid/frontier"]


def test_runtime_fails_closed_when_database_session_is_not_read_only() -> None:
    repository = _RuntimeRepository(read_only=False)

    def repository_factory(_dsn: str) -> PostgresPublicReadRepository:
        return repository

    with pytest.raises(
        RuntimeError,
        match="public read runtime database session is not read-only",
    ):
        create_public_read_runtime_app(
            "postgresql://example.invalid/frontier",
            repository_factory=repository_factory,
        )
    assert repository.closed is True


def test_runtime_factory_requires_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(DATABASE_URL_ENV, raising=False)
    with pytest.raises(RuntimeError, match=f"^{DATABASE_URL_ENV} is required$"):
        create_runtime_app_from_env()


def test_cors_origins_default_to_githack_and_fail_closed_on_unsafe_configuration() -> None:
    assert parse_cors_origins(None) == DEFAULT_CORS_ORIGINS
    assert parse_cors_origins("https://example.test/") == ("https://example.test",)
    for value in ("", " , ", "http://raw.githack.com"):
        with pytest.raises(RuntimeError, match=CORS_ORIGINS_ENV):
            parse_cors_origins(value)
