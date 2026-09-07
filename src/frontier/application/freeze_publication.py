from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

from frontier.domain.candidate_freeze import CandidateFreezeReceipt
from frontier.domain.canonical_json import CanonicalValue, canonical_json_bytes, canonical_timestamp
from frontier.domain.digests import Digest, sha256_digest

FREEZE_PUBLICATION_SCHEMA_VERSION = "candidate-freeze-publication-v0"
RANKING_WINDOW_SECONDS = 2_419_200
_FREEZE_RECEIPT_PUBLICATION_PATH_RE = re.compile(
    r"^experiments/advanced_intelligence/pef_v0/candidate_freeze_receipt_v[0-9]+\.json$"
)
_COMMIT_HASH_RE = re.compile(r"^[0-9a-f]{40,64}$")


@dataclass(frozen=True, slots=True)
class CandidateFreezePublication:
    freeze_receipt_id: str
    freeze_receipt_digest: Digest
    implementation_commit: str
    implementation_tree_digest: str
    publication_commit: str
    publication_committer_at: datetime
    schema_version: str = FREEZE_PUBLICATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for value, label in (
            (self.implementation_commit, "implementation commit"),
            (self.implementation_tree_digest, "implementation tree"),
            (self.publication_commit, "publication commit"),
        ):
            if not _COMMIT_HASH_RE.fullmatch(value):
                raise ValueError(f"{label} is not a git hash")
        if (
            self.publication_committer_at.tzinfo is None
            or self.publication_committer_at.utcoffset() is None
        ):
            raise ValueError("publication committer timestamp must be timezone-aware")
        if self.schema_version != FREEZE_PUBLICATION_SCHEMA_VERSION:
            raise ValueError("freeze publication schema mismatch")

    def to_canonical(self) -> dict[str, CanonicalValue]:
        return {
            "freeze_receipt_digest": str(self.freeze_receipt_digest),
            "freeze_receipt_id": self.freeze_receipt_id,
            "implementation_commit": self.implementation_commit,
            "implementation_tree_digest": self.implementation_tree_digest,
            "publication_commit": self.publication_commit,
            "publication_committer_at": canonical_timestamp(self.publication_committer_at),
            "schema_version": self.schema_version,
        }

    @property
    def publication_digest(self) -> Digest:
        return sha256_digest(canonical_json_bytes(self.to_canonical()))


def first_confirmatory_boundary(publication_committer_at: datetime) -> datetime:
    if publication_committer_at.tzinfo is None or publication_committer_at.utcoffset() is None:
        raise ValueError("publication_committer_at must be timezone-aware")
    epoch = int(publication_committer_at.astimezone(UTC).timestamp())
    return datetime.fromtimestamp((epoch // 300 + 1) * 300, tz=UTC)


def confirmatory_window_end(publication_committer_at: datetime) -> datetime:
    return first_confirmatory_boundary(publication_committer_at) + timedelta(
        seconds=RANKING_WINDOW_SECONDS
    )


def require_confirmatory_boundary(*, as_of: datetime, publication_committer_at: datetime) -> None:
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("as_of must be timezone-aware")
    as_of_utc = as_of.astimezone(UTC)
    if as_of_utc.microsecond != 0 or int(as_of_utc.timestamp()) % 300 != 0:
        raise ValueError("as_of must align to a UTC epoch multiple of 300 seconds")
    start = first_confirmatory_boundary(publication_committer_at)
    end = start + timedelta(seconds=RANKING_WINDOW_SECONDS)
    if as_of_utc < start or as_of_utc >= end:
        raise ValueError("as_of is outside the fixed preregistered ranking window")


def _git_text(root: Path, args: list[str]) -> str:
    try:
        result = subprocess.run(
            ["git", *args], cwd=root, capture_output=True, text=True, check=True, timeout=30
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise RuntimeError("candidate freeze Git publication cannot be verified") from error
    return result.stdout.strip()


def _matching_receipt_path(root: Path, receipt: CandidateFreezeReceipt) -> Path:
    base = root / "experiments/advanced_intelligence/pef_v0"
    matches: list[Path] = []
    for path in sorted(base.glob("candidate_freeze_receipt_v*.json")):
        try:
            raw = cast(object, json.loads(path.read_text(encoding="utf-8")))
        except OSError, UnicodeDecodeError, json.JSONDecodeError:
            continue
        if raw == receipt.to_canonical():
            matches.append(path)
    if len(matches) != 1:
        raise RuntimeError(
            "exact canonical candidate freeze receipt publication is not uniquely present"
        )
    return matches[0]


def derive_freeze_publication(
    root: Path, receipt: CandidateFreezeReceipt, *, receipt_path: Path | None = None
) -> CandidateFreezePublication:
    path = receipt_path or _matching_receipt_path(root, receipt)
    try:
        relative = path.resolve().relative_to(root.resolve()).as_posix()
    except (OSError, ValueError) as error:
        raise ValueError("candidate freeze receipt must be inside the repository root") from error
    if _FREEZE_RECEIPT_PUBLICATION_PATH_RE.fullmatch(relative) is None:
        raise ValueError(
            "candidate freeze receipt path is not a canonical versioned publication path"
        )
    if receipt.implementation_commit is None or receipt.implementation_tree_digest is None:
        raise RuntimeError("candidate freeze receipt is missing implementation identity")
    try:
        raw = cast(object, json.loads(path.read_text(encoding="utf-8")))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError("candidate freeze receipt publication is unreadable") from error
    if raw != receipt.to_canonical():
        raise RuntimeError("candidate freeze publication file does not equal the bound receipt")
    tree = _git_text(root, ["rev-parse", f"{receipt.implementation_commit}^{{tree}}"])
    if tree != receipt.implementation_tree_digest:
        raise RuntimeError("candidate freeze implementation tree does not match bound commit")
    try:
        ancestor = subprocess.run(
            ["git", "merge-base", "--is-ancestor", receipt.implementation_commit, "HEAD"],
            cwd=root,
            capture_output=True,
            check=False,
            timeout=30,
        )
        if ancestor.returncode != 0:
            raise RuntimeError("frozen implementation is not an ancestor of runtime HEAD")
        diff = subprocess.run(
            [
                "git",
                "diff",
                "--name-status",
                "-z",
                "--no-renames",
                receipt.implementation_commit,
                "HEAD",
                "--",
            ],
            cwd=root,
            capture_output=True,
            check=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise RuntimeError("candidate freeze Git publication cannot be verified") from error
    fields = diff.stdout.split(b"\0")
    if fields and fields[-1] == b"":
        fields.pop()
    if len(fields) != 2:
        raise RuntimeError("runtime tree is not the exact one-file freeze publication delta")
    status = fields[0].decode("ascii")
    changed = fields[1].decode("utf-8")
    if (status, changed) != ("A", relative):
        raise RuntimeError("runtime tree drifted outside the exact freeze receipt publication")
    parts = _git_text(root, ["rev-list", "--parents", "-n", "1", "HEAD"]).split()
    if len(parts) != 3:
        raise RuntimeError(
            "durable freeze publication HEAD must be an exact two-parent merge commit"
        )
    publication_commit, first_parent, _ = parts
    if first_parent != receipt.implementation_commit:
        raise RuntimeError(
            "durable freeze publication first parent is not the frozen implementation"
        )
    committed_at = datetime.fromisoformat(_git_text(root, ["show", "-s", "--format=%cI", "HEAD"]))
    if committed_at.tzinfo is None or committed_at.utcoffset() is None:
        raise RuntimeError("publication committer timestamp is not timezone-aware")
    if committed_at < receipt.frozen_at:
        raise RuntimeError("durable freeze publication timestamp precedes receipt creation")
    return CandidateFreezePublication(
        freeze_receipt_id=receipt.receipt_id,
        freeze_receipt_digest=receipt.receipt_digest,
        implementation_commit=receipt.implementation_commit,
        implementation_tree_digest=receipt.implementation_tree_digest,
        publication_commit=publication_commit,
        publication_committer_at=committed_at,
    )


__all__ = [
    "FREEZE_PUBLICATION_SCHEMA_VERSION",
    "RANKING_WINDOW_SECONDS",
    "CandidateFreezePublication",
    "confirmatory_window_end",
    "derive_freeze_publication",
    "first_confirmatory_boundary",
    "require_confirmatory_boundary",
]
