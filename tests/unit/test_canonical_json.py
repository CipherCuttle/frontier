from datetime import datetime, timezone
from decimal import Decimal

import pytest

from frontier.domain.canonical_json import (
    CanonicalizationError,
    canonical_decimal,
    canonical_json_text,
    canonical_timestamp,
)


def test_canonical_json_exact_order_and_escape_mapping() -> None:
    value = {"z": "é", "a": '"\\\b\t\n\f\r\x00\x01\x0b/'}
    assert canonical_json_text(value) == (
        '{"a":"\\"\\\\\\b\\t\\n\\f\\r\\u0000\\u0001\\u000b/","z":"é"}'
    )


def test_nfc_normalization_and_duplicate_rejection() -> None:
    assert canonical_json_text({"e\u0301": "e\u0301"}) == '{"é":"é"}'
    with pytest.raises(CanonicalizationError):
        canonical_json_text({"é": 1, "e\u0301": 2})


def test_float_and_runtime_specific_values_are_rejected() -> None:
    with pytest.raises(CanonicalizationError):
        canonical_json_text({"x": 1.0})
    with pytest.raises(CanonicalizationError):
        canonical_json_text({"x": Decimal("1.0")})
    with pytest.raises(CanonicalizationError):
        canonical_json_text({"x": datetime.now(timezone.utc)})


def test_decimal_and_timestamp_normalizers() -> None:
    assert canonical_decimal(Decimal("1.2300")) == "1.23"
    assert canonical_decimal(Decimal("-0.000")) == "0"
    assert canonical_timestamp(datetime(2026, 9, 5, tzinfo=timezone.utc)) == "2026-09-05T00:00:00.000000Z"
