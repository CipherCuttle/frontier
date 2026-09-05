from __future__ import annotations

import ast
from pathlib import Path

PROHIBITED = {"fastapi", "pydantic", "psycopg", "httpx", "playwright"}
DOMAIN = Path("src/frontier/domain")


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


def main() -> int:
    failures: list[str] = []
    for path in DOMAIN.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            bad = imported_root(node) & (PROHIBITED | {"frontier.adapters/contracts"})
            if bad:
                failures.append(f"{path}: prohibited import(s): {', '.join(sorted(bad))}")
    if failures:
        print("\n".join(failures))
        return 1
    print("architecture-boundaries: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
