from datetime import date

import pytest

from docflow.parse import parse_date, parse_money


@pytest.mark.parametrize("text,expected", [
    ("$1,234.50", 1234.50), ("1,234.50 USD", 1234.50), ("USD 1234.50", 1234.50),
    ("Amount Due: $0.00", 0.0), ("no money here", None), (None, None),
])
def test_money(text, expected):
    assert parse_money(text) == expected


@pytest.mark.parametrize("text", ["03/04/2026", "March 4, 2026", "2026-03-04", "04-Mar-2026", "Mar 4, 2026"])
def test_dates(text):
    assert parse_date(text) == date(2026, 3, 4)


def test_bad_date():
    assert parse_date("sometime soon") is None
