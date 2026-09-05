from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class Digest:
    value: str

    def __post_init__(self) -> None:
        if not _DIGEST_RE.fullmatch(self.value):
            raise ValueError("invalid SHA-256 digest text")

    def __str__(self) -> str:
        return self.value


def sha256_digest(data: bytes) -> Digest:
    return Digest("sha256:" + hashlib.sha256(data).hexdigest())


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
