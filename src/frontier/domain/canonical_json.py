from __future__ import annotations

import json
import unicodedata
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import TypeAlias, cast

CanonicalScalar: TypeAlias = None | bool | int | str
CanonicalValue: TypeAlias = CanonicalScalar | list["CanonicalValue"] | dict[str, "CanonicalValue"]


class CanonicalizationError(ValueError):
    """Raised when a value cannot enter frontier-canonical-json-v1."""


def canonical_timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise CanonicalizationError("naive datetime is not canonical")
    utc = value.astimezone(timezone.utc)
    return utc.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def canonical_decimal(value: Decimal) -> str:
    if not value.is_finite():
        raise CanonicalizationError("non-finite decimal is not canonical")
    if value == 0:
        return "0"
    try:
        text = format(value, "f")
    except InvalidOperation as exc:  # pragma: no cover - defensive
        raise CanonicalizationError("invalid decimal") from exc
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    if text.startswith("+"):
        text = text[1:]
    if text.startswith("-0") and text != "0" and not text.startswith("-0."):
        text = "-" + text[2:]
    return text


def _normalize(value: object) -> CanonicalValue:
    if value is None or isinstance(value, (bool, int, str)):
        if isinstance(value, str):
            return unicodedata.normalize("NFC", value)
        return value
    if isinstance(value, float):
        raise CanonicalizationError("binary float is forbidden")
    if isinstance(value, (Decimal, datetime)):
        raise CanonicalizationError("Decimal/datetime must be normalized before canonical JSON")
    if isinstance(value, Mapping):
        mapping = cast(Mapping[object, object], value)
        normalized: dict[str, CanonicalValue] = {}
        for raw_key, raw_value in mapping.items():
            if not isinstance(raw_key, str):
                raise CanonicalizationError("canonical object keys must be strings")
            key = unicodedata.normalize("NFC", raw_key)
            if key in normalized:
                raise CanonicalizationError("duplicate object key after NFC normalization")
            normalized[key] = _normalize(raw_value)
        return {key: normalized[key] for key in sorted(normalized)}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        sequence = cast(Sequence[object], value)
        return [_normalize(item) for item in sequence]
    raise CanonicalizationError(f"unsupported canonical type: {type(value).__name__}")


def canonical_json_bytes(value: object) -> bytes:
    normalized = _normalize(value)
    text = json.dumps(
        normalized,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=False,
    )
    return text.encode("utf-8")


def canonical_json_text(value: object) -> str:
    return canonical_json_bytes(value).decode("utf-8")
