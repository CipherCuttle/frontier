from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import cast

from frontier.domain.canonical_json import CanonicalValue


class JsonValueError(ValueError):
    """Raised when parsed JSON cannot enter a typed acquisition boundary."""


def _typed_json_value(value: object) -> CanonicalValue:
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        raise JsonValueError("binary float is not accepted at this acquisition boundary")
    if isinstance(value, Mapping):
        mapping = cast(Mapping[object, object], value)
        result: dict[str, CanonicalValue] = {}
        for raw_key, raw_value in mapping.items():
            if not isinstance(raw_key, str):
                raise JsonValueError("JSON object key must be a string")
            result[raw_key] = _typed_json_value(raw_value)
        return result
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        sequence = cast(Sequence[object], value)
        return [_typed_json_value(item) for item in sequence]
    raise JsonValueError(f"unsupported JSON value type: {type(value).__name__}")


def parse_typed_json(data: str | bytes) -> CanonicalValue:
    try:
        raw = cast(object, json.loads(data))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise JsonValueError("malformed JSON") from exc
    return _typed_json_value(raw)
