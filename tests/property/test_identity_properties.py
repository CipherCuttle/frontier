# ruff: noqa: E402
import pytest

hypothesis = pytest.importorskip("hypothesis")
from hypothesis import given
from hypothesis import strategies as st

from frontier.domain.canonical_json import canonical_json_text


@given(st.dictionaries(st.text(min_size=1), st.integers(), max_size=20))
def test_mapping_insertion_order_does_not_change_canonical_json(value: dict[str, int]) -> None:
    reversed_value = dict(reversed(list(value.items())))
    assert canonical_json_text(value) == canonical_json_text(reversed_value)
