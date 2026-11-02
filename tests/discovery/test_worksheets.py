"""Public contract checks using real synthetic files."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from chooong.datasift import (
    FilterMask,
    Operator,
    TextCondition,
    iter_matching_batches,
    iter_matching_rows,
)
from tests.fixtures.excel import (
    _FIRST,
    _NUMERIC,
    _SECOND,
    _UNRELATED,
    Sheet,
    cell,
    worksheet,
    write_book,
)
from tests.fixtures.masks import sheet_mask


@pytest.mark.parametrize(
    ("name", "amounts"), [("First", [101]), ("Second", [202, 203]), ("null", [202, 203])]
)
def test_named_sheet_and_literal_null_string_still_select_one_sheet(
    tmp_path: Path,
    name: str,
    amounts: list[int],
) -> None:
    path = tmp_path / "one.xlsx"
    write_book(path, Sheet("First", _FIRST), Sheet("Second", _SECOND), Sheet("null", _SECOND))
    assert [row["Value"] for row in iter_matching_rows(path, sheet_mask(name))] == amounts


def test_no_matching_schema_is_an_empty_result(tmp_path: Path) -> None:
    path = tmp_path / "no-schema.xlsx"
    write_book(
        path,
        Sheet("Empty", worksheet()),
        Sheet("Numeric", _NUMERIC),
        Sheet("MissingHeader", worksheet('<row r="2">' + cell("A", 2, "DE") + "</row>")),
        Sheet("Unrelated", _UNRELATED),
    )
    assert list(iter_matching_rows(path, sheet_mask())) == []


def test_invalid_regex_and_missing_sheet_field_fail_eagerly(tmp_path: Path) -> None:
    path = tmp_path / "empty.xlsx"
    write_book(path, Sheet("Empty", worksheet()))
    mask = FilterMask(
        sheet=None, where=TextCondition(column="Country", op=Operator.REGEX, value="(")
    )
    with pytest.raises(ValueError, match="Invalid regex"):
        iter_matching_batches(path, mask)
    with pytest.raises(ValidationError):
        iter_matching_batches(path, {"where": {"column": "Country", "op": "eq", "value": "DE"}})
