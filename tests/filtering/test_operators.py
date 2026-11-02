"""Public contract checks using real synthetic files."""

from __future__ import annotations

from pathlib import Path

import pytest

from chooong.datasift import (
    Operator,
    iter_matching_rows,
)
from tests.fixtures.excel import make_workbook


@pytest.mark.parametrize(
    ("column", "op", "value", "expected"),
    [
        ("Land", "eq", "AT", ["XYZ AG"]),
        ("Land", "ne", "DE", ["XYZ AG"]),
        ("Status", "in", ["Offen", "Inaktiv"], ["ABC Hamburg", "ABC & Söhne"]),
        ("Umsatz", "gt", 3200, ["ABC GmbH", "XYZ AG"]),
        ("Umsatz", "gte", 3200, ["ABC GmbH", "XYZ AG", "ABC München"]),
        ("Umsatz", "lt", 2500, ["ABC Berlin", "ABC & Söhne"]),
        ("Umsatz", "lte", 2500, ["ABC Berlin", "ABC Hamburg", "ABC & Söhne"]),
        ("Kunde", "contains", "&", ["ABC & Söhne"]),
        ("Kunde", "starts_with", "XYZ", ["XYZ AG"]),
        ("Kunde", "ends_with", "AG", ["XYZ AG"]),
        ("Kunde", "regex", "^XYZ.*", ["XYZ AG"]),
        ("Umsatz", "is_empty", None, ["ABC Leer"]),
        (
            "Umsatz",
            "not_empty",
            None,
            [
                "ABC GmbH",
                "XYZ AG",
                "ABC Berlin",
                "ABC München",
                "ABC Hamburg",
                "ABC & Söhne",
                "ABC Bool",
            ],
        ),
    ],
)
def test_operator_wire_contract_against_native_engine(
    tmp_path: Path,
    column: str,
    op: str,
    value: object,
    expected: list[str],
) -> None:
    path = tmp_path / "operators.xlsx"
    make_workbook(path)
    condition: dict[str, object] = {"column": column, "op": op}
    if op not in {Operator.IS_EMPTY, Operator.NOT_EMPTY}:
        condition["value"] = value
    rows = iter_matching_rows(
        path,
        {"sheet": "Daten", "where": {"all": [condition, {"column": "Kunde", "op": "not_empty"}]}},
    )
    assert [row["Kunde"] for row in rows] == expected


def test_streamed_filter_with_nested_json(xlsx: Path, mask: dict) -> None:
    actual = list(iter_matching_rows(xlsx, mask, batch_size=1))
    assert [row["Kunde"] for row in actual] == ["ABC GmbH", "ABC München", "ABC & Söhne"]
    assert [row["Umsatz"] for row in actual] == [5000, 3200, 1800]
    assert all(row["Land"] == "DE" for row in actual)


def test_regex_and_not_and_bool_types(xlsx: Path) -> None:
    mask = {
        "sheet": "Daten",
        "where": {
            "all": [
                {"column": "Kunde", "op": "regex", "value": "(?i)^abc.*"},
                {"not": {"column": "Status", "op": "eq", "value": "Inaktiv"}},
                {"column": "Umsatz", "op": "lt", "value": 2000},
            ]
        },
    }
    assert [r["Kunde"] for r in iter_matching_rows(xlsx, mask)] == ["ABC Berlin", "ABC & Söhne"]


def test_in_and_missing_value(xlsx: Path) -> None:
    mask = {
        "sheet": "Daten",
        "where": {
            "all": [
                {"column": "Status", "op": "in", "value": ["Offen", "Inaktiv"]},
                {"column": "Kunde", "op": "not_empty"},
            ]
        },
    }
    assert len(list(iter_matching_rows(xlsx, mask))) == 2


def test_sparse_empty_and_null_comparisons(xlsx: Path) -> None:
    mask = {
        "sheet": "Daten",
        "where": {
            "all": [
                {"column": "Kunde", "op": "eq", "value": "ABC Leer"},
                {"column": "Umsatz", "op": "is_empty"},
            ]
        },
    }
    assert [dict(row) for row in iter_matching_rows(xlsx, mask)] == [
        {"Kunde": "ABC Leer", "Umsatz": None}
    ]
    mask["where"]["all"][1] = {"column": "Umsatz", "op": "eq", "value": None}
    assert len(list(iter_matching_rows(xlsx, mask))) == 1
