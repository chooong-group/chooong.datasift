"""Public contract checks using real synthetic files."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from chooong.datasift import (
    RejectCode,
    iter_matching_rows,
    scan_batches,
)


def test_boolean_not_treated_as_numeric(xlsx: Path) -> None:
    mask = {
        "sheet": "Daten",
        "where": {
            "all": [
                {"column": "Kunde", "op": "eq", "value": "ABC Bool"},
                {"column": "Umsatz", "op": "gte", "value": 1},
            ]
        },
    }
    assert [dict(row) for row in iter_matching_rows(xlsx, mask)] == []
    mask["where"]["all"][1] = {"column": "Umsatz", "op": "eq", "value": True}
    assert len(list(iter_matching_rows(xlsx, mask))) == 1


@pytest.mark.parametrize(
    ("target", "value", "expected"),
    [
        ("integer", "123", 123),
        ("float", "0.5", 0.5),
        ("number", "0.5", 0.5),
        ("boolean", "false", False),
        ("decimal", "0.1234567890123456789012345678", Decimal("0.1234567890123456789012345678")),
        ("currency_code", "EUR", "EUR"),
        ("string", "literal", "literal"),
    ],
)
def test_type_conversion_then_nested_type_filters(tmp_path, target, value, expected) -> None:
    path = tmp_path / "types.csv"
    path.write_text(f"Value,Other\n{value},x\ninvalid,x\n")
    mask = {
        "sheet": None,
        "types": {"Value": {"type": target, "convert": True}},
        "where": {
            "all": [
                {"column": "Value", "op": "is_type", "value": target},
                {"not": {"column": "Value", "op": "not_type", "value": target}},
            ]
        },
    }
    rows = list(iter_matching_rows(path, mask))
    assert rows[0]["Value"] == expected
    assert len(rows) == (2 if target == "string" else 1)


def test_explicit_type_mismatch_is_row_local(csv_file: Path, tmp_path) -> None:
    path = csv_file
    mask = {"sheet": None, "types": {"Amount": {"type": "integer"}}}
    with scan_batches(path, mask) as batches:
        records = [r for batch in batches for r in batch]
    assert records[0].reasons[0].code == RejectCode.TYPE_MISMATCH
    assert len(records) == 3


def test_null_and_unicode_normalization(tmp_path) -> None:
    path = tmp_path / "unicode.csv"
    path.write_text("Cafe\u0301,Value\na,\n")
    mask = {
        "sheet": None,
        "header": {"unicode": "NFC"},
        "where": {"column": "Value", "op": "is_type", "value": "null"},
        "select": ["*"],
    }
    assert dict(next(iter_matching_rows(path, mask))) == {"Café": "a", "Value": None}
