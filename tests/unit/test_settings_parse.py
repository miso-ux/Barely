import pytest

from app.services.errors import InvalidSettingValue
from app.services.settings import DEFAULTS, parse, value_type


def test_money_is_stored_as_decimal_string_with_two_places() -> None:
    assert parse("penalty_amount", "10") == "10.00"
    assert parse("loan_price", "1,5") == "1.50"
    assert parse("loan_price", " 0 ") == "0.00"


def test_bool_and_int_parsing() -> None:
    assert parse("block_debtors", "false") is False
    assert parse("registration_enabled", "on") is True
    assert parse("loan_limit", "12") == 12


def test_list_parsing() -> None:
    assert parse("forbidden_role_combinations", '[["a","b"]]') == [["a", "b"]]


@pytest.mark.parametrize(
    ("key", "raw"),
    [
        ("penalty_amount", "abc"),
        ("penalty_amount", "-1"),
        ("loan_limit", "1.5"),
        ("loan_limit", "-3"),
        ("block_debtors", "maybe"),
        ("forbidden_role_combinations", "{}"),
        ("forbidden_role_combinations", "not json"),
    ],
)
def test_invalid_values_raise(key: str, raw: str) -> None:
    with pytest.raises(InvalidSettingValue):
        parse(key, raw)


def test_every_default_has_a_known_type() -> None:
    assert {value_type(key) for key in DEFAULTS} <= {"money", "bool", "int", "list", "text"}
