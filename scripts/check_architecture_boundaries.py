from __future__ import annotations

import ast
import re
from pathlib import Path

PROHIBITED = {"fastapi", "pydantic", "psycopg", "httpx", "playwright"}
DOMAIN = Path("src/frontier/domain")
FETCH_BOUNDARY = Path("src/frontier/adapters/acquisition/fetcher.py")
FETCH_PROHIBITED_ROOTS = {"psycopg", "sqlalchemy"}
FETCH_PROHIBITED_MODULE_PREFIXES = (
    "frontier.adapters.postgres",
    "frontier.application",
)
PUBLIC_API = Path("src/frontier/adapters/api/public_read.py")
PUBLIC_POSTGRES = Path("src/frontier/adapters/postgres/public_read.py")
PUBLIC_API_PROHIBITED_MODULE_PREFIXES = ("frontier.adapters.postgres",)
PUBLIC_POSTGRES_PROHIBITED_MODULE_PREFIXES = (
    "frontier.adapters.postgres.store",
    "frontier.adapters.postgres.grouping",
    "frontier.adapters.postgres.intelligence",
    "frontier.application.intelligence",
)
PUBLIC_POSTGRES_MUTATION_SQL = re.compile(r"\b(?:INSERT|UPDATE|DELETE|TRUNCATE)\b", re.IGNORECASE)


def imported_root(node: ast.AST) -> set[str]:
    roots: set[str] = set()
    if isinstance(node, ast.Import):
        roots.update(alias.name.split(".")[0] for alias in node.names)
    elif isinstance(node, ast.ImportFrom) and node.module:
        roots.add(node.module.split(".")[0])
        if node.module.startswith("frontier.adapters") or node.module.startswith(
            "frontier.contracts"
        ):
            roots.add("frontier.adapters/contracts")
    return roots


def imported_modules(node: ast.AST) -> set[str]:
    if isinstance(node, ast.Import):
        return {alias.name for alias in node.names}
    if isinstance(node, ast.ImportFrom) and node.module:
        return {node.module}
    return set()


def check_domain_boundaries() -> list[str]:
    failures: list[str] = []
    for path in DOMAIN.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            bad = imported_root(node) & (PROHIBITED | {"frontier.adapters/contracts"})
            if bad:
                failures.append(f"{path}: prohibited import(s): {', '.join(sorted(bad))}")
    return failures


def check_fetch_boundary() -> list[str]:
    failures: list[str] = []
    tree = ast.parse(FETCH_BOUNDARY.read_text(encoding="utf-8"), filename=str(FETCH_BOUNDARY))
    for node in ast.walk(tree):
        bad_roots = imported_root(node) & FETCH_PROHIBITED_ROOTS
        if bad_roots:
            failures.append(
                f"{FETCH_BOUNDARY}: fetch role imports privileged dependency: "
                f"{', '.join(sorted(bad_roots))}"
            )
        for module in imported_modules(node):
            if module.startswith(FETCH_PROHIBITED_MODULE_PREFIXES):
                failures.append(
                    f"{FETCH_BOUNDARY}: fetch role crosses trusted "
                    f"application/storage boundary: {module}"
                )
    text = FETCH_BOUNDARY.read_text(encoding="utf-8").lower()
    for forbidden in ("database_url", "postgres://", "postgresql://", "frontier_database_url"):
        if forbidden in text:
            failures.append(
                f"{FETCH_BOUNDARY}: fetch role contains DB coordinate token: {forbidden}"
            )
    return failures


def _check_module_prefixes(path: Path, prohibited: tuple[str, ...], label: str) -> list[str]:
    failures: list[str] = []
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        for module in imported_modules(node):
            if module.startswith(prohibited):
                failures.append(f"{path}: {label} imports prohibited module: {module}")
    return failures


def check_public_read_boundary() -> list[str]:
    failures = _check_module_prefixes(
        PUBLIC_API,
        PUBLIC_API_PROHIBITED_MODULE_PREFIXES,
        "public API transport",
    )
    failures.extend(
        _check_module_prefixes(
            PUBLIC_POSTGRES,
            PUBLIC_POSTGRES_PROHIBITED_MODULE_PREFIXES,
            "public PostgreSQL read adapter",
        )
    )
    tree = ast.parse(
        PUBLIC_POSTGRES.read_text(encoding="utf-8"),
        filename=str(PUBLIC_POSTGRES),
    )
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and PUBLIC_POSTGRES_MUTATION_SQL.search(node.value)
        ):
            failures.append(
                f"{PUBLIC_POSTGRES}: public read SQL contains mutation verb in string literal"
            )
    return failures


def main() -> int:
    failures = check_domain_boundaries() + check_fetch_boundary() + check_public_read_boundary()
    if failures:
        print("\n".join(failures))
        return 1
    print("architecture-boundaries: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
