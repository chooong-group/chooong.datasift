"""Automatic schema discovery and mask-only projection through actual OOXML."""

from pathlib import Path

import pytest
from pydantic import ValidationError
from test_all_sheets import _book, _Sheet, _worksheet
from test_engine import _cell

from chooong.datasift import (
    AllOf,
    AnyOf,
    FilterMask,
    Not,
    NumericCondition,
    Operator,
    ScalarCondition,
    TextCondition,
    iter_matching_batches,
    iter_matching_rows,
)


@pytest.mark.parametrize("sheet", [None, "Offset"])
@pytest.mark.parametrize("batch_size", [1, 2, 1024])
def test_offset_multiline_header_projects_only_nested_mask_columns(
    tmp_path: Path,
    sheet: str | None,
    batch_size: int,
) -> None:
    path = tmp_path / "offset.xlsx"
    document = _worksheet(
        '<row r="1">' + _cell("A", 1, "Synthetic report") + "</row>",
        '<row r="3">' + _cell("B", 3, "Country\nCode") + "</row>",
        '<row r="5">' + _cell("D", 5, 123) + "</row>",
        '<row r="7">'
        + _cell("F", 7, "Country\nCode")
        + _cell("H", 7, "Budget\nEUR")
        + _cell("K", 7, "Owner\nStatus")
        + _cell("N", 7, "Comment")
        + _cell("O", 7, "Flag values separately")
        + _cell("P", 7, 2026)
        + "</row>",
        '<row r="8">' + _cell("N", 8, "Comment before actual data") + "</row>",
        '<row r="10">'
        + _cell("F", 10, "DE")
        + _cell("H", 10, 1200)
        + _cell("K", 10, "approved")
        + '<c r="N10" t="s"><v>999999</v></c></row>',
        '<row r="11">'
        + _cell("F", 11, "AT")
        + _cell("H", 11, 1500)
        + _cell("K", 11, "review")
        + "</row>",
        '<row r="13">'
        + _cell("F", 13, "AT")
        + _cell("H", 13, 1600)
        + _cell("K", 13, "approved")
        + "</row>",
    )
    _book(path, _Sheet("Offset", document))
    mask = FilterMask(
        sheet=sheet,
        where=AllOf(
            conditions=(
                AnyOf(
                    conditions=(
                        ScalarCondition(column="Country\nCode", op=Operator.EQ, value="DE"),
                        ScalarCondition(column="Country\nCode", op=Operator.EQ, value="AT"),
                    )
                ),
                NumericCondition(column="Budget\nEUR", op=Operator.GTE, value=900),
                Not(
                    condition=TextCondition(
                        column="Owner\nStatus", op=Operator.CONTAINS, value="review"
                    )
                ),
            )
        ),
    )
    original = path.read_bytes()
    expected = [
        {"Country\nCode": "DE", "Budget\nEUR": 1200, "Owner\nStatus": "approved"},
        {"Country\nCode": "AT", "Budget\nEUR": 1600, "Owner\nStatus": "approved"},
    ]
    assert [dict(row) for row in iter_matching_rows(path, mask, batch_size=batch_size)] == expected
    with iter_matching_batches(path, mask, batch_size=batch_size) as batches:
        assert [dict(row) for batch in batches for row in batch] == expected
    assert path.read_bytes() == original


def test_unused_header_collisions_and_repeated_headers_do_not_add_rows(tmp_path: Path) -> None:
    path = tmp_path / "headers.xlsx"
    _book(
        path,
        _Sheet(
            "Offset",
            _worksheet(
                '<row r="4">'
                + _cell("C", 4, "Country")
                + _cell("D", 4, "Other")
                + _cell("E", 4, "Other")
                + _cell("F", 4, "Other_1")
                + "</row>",
                '<row r="5">' + _cell("C", 5, "DE") + "</row>",
                '<row r="8">' + _cell("C", 8, "Country") + "</row>",
                '<row r="9">' + _cell("C", 9, "AT") + "</row>",
            ),
        ),
    )
    mask = FilterMask(
        sheet=None, where=ScalarCondition(column="Country", op=Operator.NE, value="FR")
    )
    assert [dict(row) for row in iter_matching_rows(path, mask)] == [
        {"Country": "DE"},
        {"Country": "AT"},
    ]


def test_header_row_is_removed_from_the_contract() -> None:
    payload = {
        "sheet": None,
        "header_row": 7,
        "where": {"column": "Country", "op": "eq", "value": "DE"},
    }
    with pytest.raises(ValidationError, match="header_row"):
        iter_matching_batches("missing.xlsx", payload)
    assert "header_row" not in FilterMask.model_json_schema()["properties"]
