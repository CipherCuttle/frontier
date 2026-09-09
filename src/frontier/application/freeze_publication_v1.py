from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import cast

from frontier.application.freeze_publication import (
    CandidateFreezePublication,
    require_github_main_publication,
)
from frontier.domain.candidate_freeze_v1 import CandidateFreezeReceiptV1

_FREEZE_V1_RECEIPT_PUBLICATION_PATH_RE = re.compile(
    r"^experiments/advanced_intelligence/pef_v1/candidate_freeze_receipt_v[0-9]+\.json$"
)


def _git_text(root: Path, args: list[str]) -> str:
    try:
        result = subprocess.run(
            ["git", *args], cwd=root, capture_output=True, text=True, check=True, timeout=30
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise RuntimeError("PEF_V1 candidate freeze Git publication cannot be verified") from error
    return result.stdout.strip()


def _matching_receipt_path(root: Path, receipt: CandidateFreezeReceiptV1) -> Path:
    base = root / "experiments/advanced_intelligence/pef_v1"
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
            "exact canonical PEF_V1 candidate freeze receipt publication is not uniquely present"
        )
    return matches[0]


def derive_freeze_publication_v1(
    root: Path,
    receipt: CandidateFreezeReceiptV1,
    *,
    receipt_path: Path | None = None,
) -> CandidateFreezePublication:
    """Prove the exact one-file, two-parent durable publication shape for PEF_V1."""
    path = receipt_path or _matching_receipt_path(root, receipt)
    try:
        relative = path.resolve().relative_to(root.resolve()).as_posix()
    except (OSError, ValueError) as error:
        raise ValueError(
            "PEF_V1 candidate freeze receipt must be inside repository root"
        ) from error
    if _FREEZE_V1_RECEIPT_PUBLICATION_PATH_RE.fullmatch(relative) is None:
        raise ValueError(
            "PEF_V1 candidate freeze receipt path is not a canonical versioned publication path"
        )
    if receipt.implementation_commit is None or receipt.implementation_tree_digest is None:
        raise RuntimeError("PEF_V1 candidate freeze receipt is missing implementation identity")
    try:
        raw = cast(object, json.loads(path.read_text(encoding="utf-8")))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError("PEF_V1 candidate freeze receipt publication is unreadable") from error
    if raw != receipt.to_canonical():
        raise RuntimeError("PEF_V1 freeze publication file does not equal the bound receipt")

    tree = _git_text(root, ["rev-parse", f"{receipt.implementation_commit}^{{tree}}"])
    if tree != receipt.implementation_tree_digest:
        raise RuntimeError("PEF_V1 freeze implementation tree does not match bound commit")
    try:
        ancestor = subprocess.run(
            ["git", "merge-base", "--is-ancestor", receipt.implementation_commit, "HEAD"],
            cwd=root,
            capture_output=True,
            check=False,
            timeout=30,
        )
        if ancestor.returncode != 0:
            raise RuntimeError("frozen PEF_V1 implementation is not an ancestor of runtime HEAD")
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
        raise RuntimeError("PEF_V1 candidate freeze Git publication cannot be verified") from error
    fields = diff.stdout.split(b"\0")
    if fields and fields[-1] == b"":
        fields.pop()
    if len(fields) != 2:
        raise RuntimeError("runtime tree is not the exact one-file PEF_V1 freeze publication delta")
    status = fields[0].decode("ascii")
    changed = fields[1].decode("utf-8")
    if (status, changed) != ("A", relative):
        raise RuntimeError(
            "runtime tree drifted outside the exact PEF_V1 freeze receipt publication"
        )

    parts = _git_text(root, ["rev-list", "--parents", "-n", "1", "HEAD"]).split()
    if len(parts) != 3:
        raise RuntimeError(
            "durable PEF_V1 freeze publication HEAD must be a two-parent merge commit"
        )
    publication_commit, first_parent, _ = parts
    if first_parent != receipt.implementation_commit:
        raise RuntimeError(
            "durable PEF_V1 freeze publication first parent is not the frozen implementation"
        )
    committed_at = datetime.fromisoformat(_git_text(root, ["show", "-s", "--format=%cI", "HEAD"]))
    if committed_at.tzinfo is None or committed_at.utcoffset() is None:
        raise RuntimeError("publication committer timestamp is not timezone-aware")
    if committed_at < receipt.frozen_at:
        raise RuntimeError("durable PEF_V1 freeze publication timestamp precedes receipt creation")
    return CandidateFreezePublication(
        freeze_receipt_id=receipt.receipt_id,
        freeze_receipt_digest=receipt.receipt_digest,
        implementation_commit=receipt.implementation_commit,
        implementation_tree_digest=receipt.implementation_tree_digest,
        publication_commit=publication_commit,
        publication_committer_at=committed_at,
    )


def derive_github_main_freeze_publication_v1(
    root: Path,
    receipt: CandidateFreezeReceiptV1,
    *,
    receipt_path: Path | None = None,
) -> CandidateFreezePublication:
    publication = derive_freeze_publication_v1(root, receipt, receipt_path=receipt_path)
    require_github_main_publication(root, publication)
    return publication


__all__ = [
    "derive_freeze_publication_v1",
    "derive_github_main_freeze_publication_v1",
]
