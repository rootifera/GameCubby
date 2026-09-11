import pytest
from fastapi import HTTPException

from gamecubby_api.utils.search import _result_limit, _result_offset


def test_result_limit_uses_a_safe_default_and_cap():
    assert _result_limit(None) == 100
    assert _result_limit("25") == 25
    assert _result_limit("1000") == 200


@pytest.mark.parametrize("value", ["0", "-1", "many"])
def test_result_limit_rejects_invalid_values(value: str):
    with pytest.raises(HTTPException) as error:
        _result_limit(value)
    assert error.value.status_code == 422


def test_result_offset_defaults_to_zero_and_rejects_invalid_values():
    assert _result_offset(None) == 0
    assert _result_offset("20") == 20
    with pytest.raises(HTTPException):
        _result_offset("-1")
