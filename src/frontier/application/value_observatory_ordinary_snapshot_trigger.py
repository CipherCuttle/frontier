from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import cast

REQUEST_SCHEMA_V0 = "frontier-ordinary-prehorizon-probe-request-v0"
REQUEST_DIRECTORY_V0 = ".github/probe-requests/ordinary-prehorizon-v0"
_REQUEST_PATH_RE = re.compile(r"^\.github/probe-requests/ordinary-prehorizon-v0/[^/]+\.json$")
_SNAPSHOT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
_UTC_Z_TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_ALLOWED_BOUNDARY_HOURS = frozenset({0, 6, 12, 18})


@dataclass(frozen=True, slots=True)
class OrdinarySnapshotProbeRequestV0:
    snapshot_id: str
    knowledge_horizon: str


def parse_repository_request_v0(raw: object) -> OrdinarySnapshotProbeRequestV0:
    if not isinstance(raw, dict):
        raise ValueError("probe request must be a JSON object")
    request = cast(dict[str, object], raw)
    expected_keys = {
        "schema_version",
        "snapshot_id",
        "knowledge_horizon",
        "non_scored",
    }
    if set(request) != expected_keys:
        raise ValueError("probe request must contain exactly the frozen V0 keys")
    if request["schema_version"] != REQUEST_SCHEMA_V0:
        raise ValueError("unsupported probe request schema")
    if request["non_scored"] is not True:
        raise ValueError("repository probe request must be explicitly non-scored")

    snapshot_id = request["snapshot_id"]
    if not isinstance(snapshot_id, str) or not _SNAPSHOT_ID_RE.fullmatch(snapshot_id):
        raise ValueError("snapshot_id must be a lowercase stable identifier")

    knowledge_horizon = request["knowledge_horizon"]
    if not isinstance(knowledge_horizon, str) or not _UTC_Z_TIMESTAMP_RE.fullmatch(
        knowledge_horizon
    ):
        raise ValueError("knowledge_horizon must be an exact UTC Z timestamp")
    try:
        parsed_horizon = datetime.fromisoformat(knowledge_horizon[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError("knowledge_horizon must be a valid UTC timestamp") from exc
    if parsed_horizon.utcoffset() != timedelta(0):
        raise ValueError("knowledge_horizon must use UTC")
    if (
        parsed_horizon.hour not in _ALLOWED_BOUNDARY_HOURS
        or parsed_horizon.minute != 0
        or parsed_horizon.second != 0
        or parsed_horizon.microsecond != 0
    ):
        raise ValueError("knowledge_horizon must use a frozen 00/06/12/18 UTC boundary")

    return OrdinarySnapshotProbeRequestV0(
        snapshot_id=snapshot_id,
        knowledge_horizon=knowledge_horizon,
    )


def select_new_repository_request_v0(changed_rows: tuple[tuple[str, str], ...]) -> str:
    request_rows = tuple(
        (status, path) for status, path in changed_rows if _REQUEST_PATH_RE.fullmatch(path)
    )
    if len(request_rows) != 1:
        raise ValueError("repo-triggered probe requires exactly one changed request file")
    status, path = request_rows[0]
    if status != "A":
        raise ValueError("repo-triggered probe requires one newly added immutable request file")
    return path


def _changed_request_rows(root: Path, head_sha: str) -> tuple[tuple[str, str], ...]:
    if not re.fullmatch(r"[0-9a-f]{40}", head_sha):
        raise ValueError("head SHA must be 40 lowercase hex characters")
    result = subprocess.run(
        [
            "git",
            "diff",
            "--name-status",
            "-M",
            f"{head_sha}^",
            head_sha,
        ],
        cwd=root,
        capture_output=True,
        check=True,
        text=True,
        timeout=30,
    )
    rows: list[tuple[str, str]] = []
    for line in result.stdout.splitlines():
        if not line:
            continue
        fields = line.split("\t")
        status = fields[0]
        paths = fields[1:]
        if len(paths) not in {1, 2}:
            raise ValueError("unexpected git name-status row for probe request")
        for path in paths:
            if _REQUEST_PATH_RE.fullmatch(path):
                rows.append((status, path))
    return tuple(rows)


def resolve_repository_request_v0(*, root: Path, head_sha: str) -> OrdinarySnapshotProbeRequestV0:
    rows = _changed_request_rows(root, head_sha)
    request_path = select_new_repository_request_v0(rows)
    raw = json.loads((root / request_path).read_text(encoding="utf-8"))
    return parse_repository_request_v0(raw)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--head-sha", required=True)
    parser.add_argument("--github-output", required=True)
    parser.add_argument("--root", default=".")
    return parser


def main() -> int:
    args = _parser().parse_args()
    request = resolve_repository_request_v0(
        root=Path(args.root).resolve(),
        head_sha=args.head_sha,
    )
    with Path(args.github_output).open("a", encoding="utf-8") as output:
        output.write(f"knowledge_horizon={request.knowledge_horizon}\n")
        output.write(f"snapshot_id={request.snapshot_id}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "OrdinarySnapshotProbeRequestV0",
    "REQUEST_DIRECTORY_V0",
    "REQUEST_SCHEMA_V0",
    "parse_repository_request_v0",
    "resolve_repository_request_v0",
    "select_new_repository_request_v0",
]
