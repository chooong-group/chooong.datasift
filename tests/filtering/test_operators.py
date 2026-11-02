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
        ("Country", "eq", "AT", ["XYZ Inc"]),
        ("Country", "ne", "DE", ["XYZ Inc"]),
        ("Status", "in", ["Open", "Inactive"], ["ABC Hamburg", "ABC & Sons"]),
        ("Revenue", "gt", 3200, ["ABC Ltd", "XYZ Inc"]),
        ("Revenue", "gte", 3200, ["ABC Ltd", "XYZ Inc", "ABC São Paulo"]),
        ("Revenue", "lt", 2500, ["ABC Berlin", "ABC & Sons"]),
        ("Revenue", "lte", 2500, ["ABC Berlin", "ABC Hamburg", "ABC & Sons"]),
        ("Customer", "contains", "&", ["ABC & Sons"]),
        ("Customer", "starts_with", "XYZ", ["XYZ Inc"]),
        ("Customer", "ends_with", "Inc", ["XYZ Inc"]),
        ("Customer", "regex", "^XYZ.*", ["XYZ Inc"]),
        ("Revenue", "is_empty", None, ["ABC Empty"]),
        (
            "Revenue",
            "not_empty",
            None,
            [
                "ABC Ltd",
                "XYZ Inc",
                "ABC Berlin",
                "ABC São Paulo",
                "ABC Hamburg",
                "ABC & Sons",
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
        {"sheet": "Data", "where": {"all": [condition, {"column": "Customer", "op": "not_empty"}]}},
    )
    assert [row["Customer"] for row in rows] == expected


def test_streamed_filter_with_nested_json(xlsx: Path, mask: dict) -> None:
    actual = list(iter_matching_rows(xlsx, mask, batch_size=1))
    assert [row["Customer"] for row in actual] == ["ABC Ltd", "ABC São Paulo", "ABC & Sons"]
    assert [row["Revenue"] for row in actual] == [5000, 3200, 1800]
    assert all(row["Country"] == "DE" for row in actual)


def test_regex_and_not_and_bool_types(xlsx: Path) -> None:
    mask = {
        "sheet": "Data",
        "where": {
            "all": [
                {"column": "Customer", "op": "regex", "value": "(?i)^abc.*"},
                {"not": {"column": "Status", "op": "eq", "value": "Inactive"}},
                {"column": "Revenue", "op": "lt", "value": 2000},
            ]
        },
    }
    assert [r["Customer"] for r in iter_matching_rows(xlsx, mask)] == ["ABC Berlin", "ABC & Sons"]


def test_in_and_missing_value(xlsx: Path) -> None:
    mask = {
        "sheet": "Data",
        "where": {
            "all": [
                {"column": "Status", "op": "in", "value": ["Open", "Inactive"]},
                {"column": "Customer", "op": "not_empty"},
            ]
        },
    }
    assert len(list(iter_matching_rows(xlsx, mask))) == 2


def test_sparse_empty_and_null_comparisons(xlsx: Path) -> None:
    mask = {
        "sheet": "Data",
        "where": {
            "all": [
                {"column": "Customer", "op": "eq", "value": "ABC Empty"},
                {"column": "Revenue", "op": "is_empty"},
            ]
        },
    }
    assert [dict(row) for row in iter_matching_rows(xlsx, mask)] == [
        {"Customer": "ABC Empty", "Revenue": None}
    ]
    mask["where"]["all"][1] = {"column": "Revenue", "op": "eq", "value": None}
    assert len(list(iter_matching_rows(xlsx, mask))) == 1
