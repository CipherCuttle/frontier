from __future__ import annotations

from fastapi.testclient import TestClient

from frontier.adapters.api.runtime import (
    CORS_ORIGINS_ENV,
    DATABASE_URL_ENV,
    _cors_origins,
    create_public_read_runtime_app,
    create_runtime_app_from_env,
)


class _RuntimeRepository:
    def __init__(self, *, read_only: bool = True) -> None:
        self.read_only = read_only
        self.closed = False

    def verify_read_only_session(self) -> bool:
        return self.read_only

    def close(self) -> None:
        self.closed = True


def test_runtime_exposes_get_only_meta_with_githack_cors_and_closes_repository() -> None:
    repository = _RuntimeRepository()
    seen_dsn: list[str] = []

    def repository_factory(dsn: str) -> _RuntimeRepository:
        seen_dsn.append(dsn)
        return repository

    app = create_public_read_runtime_app(
        "postgresql://example.invalid/frontier",
        repository_factory=repository_factory,
    )
    with TestClient(app) as client:
        response = client.get("/v0/meta", headers={"Origin": "https://raw.githack.com"})
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == "https://raw.githack.com"
        assert response.json()["mutation_authority"] is False
        assert client.post("/v0/meta").status_code == 405
    assert repository.closed is True
    assert seen_dsn == ["postgresql://example.invalid/frontier"]


def test_runtime_fails_closed_when_database_session_is_not_read_only() -> None:
    repository = _RuntimeRepository(read_only=False)

    try:
        create_public_read_runtime_app(
            "postgresql://example.invalid/frontier",
            repository_factory=lambda _dsn: repository,
        )
    except RuntimeError as error:
        assert str(error) == "public read runtime database session is not read-only"
    else:
        raise AssertionError("runtime should reject a writable session")
    assert repository.closed is True


def test_runtime_factory_requires_database_url(monkeypatch) -> None:
    monkeypatch.delenv(DATABASE_URL_ENV, raising=False)
    try:
        create_runtime_app_from_env()
    except RuntimeError as error:
        assert str(error) == f"{DATABASE_URL_ENV} is required"
    else:
        raise AssertionError("runtime should require a database URL")


def test_cors_origins_fail_closed_on_empty_or_non_https_configuration() -> None:
    for value in ("", " , ", "http://raw.githack.com"):
        try:
            _cors_origins(value)
        except RuntimeError as error:
            assert CORS_ORIGINS_ENV in str(error)
        else:
            raise AssertionError("unsafe CORS configuration should fail closed")
