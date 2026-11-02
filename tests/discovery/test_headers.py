"""Public contract checks using real synthetic files."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from chooong.datasift import (
    AllOf,
    AnyOf,
    FilterMask,
    Not,
    NumericCondition,
    Operator,
    RecordKind,
    ScalarCondition,
    TextCondition,
    iter_matching_batches,
    iter_matching_rows,
    scan_batches,
)
from tests.fixtures.excel import (
    _FIRST,
    _NS,
    _NUMERIC,
    _SECOND,
    _UNRELATED,
    Sheet,
    cell,
    indexed_workbook,
    make_workbook,
    worksheet,
    worksheet_rows,
    write_book,
)
from tests.fixtures.masks import indexed_mask, sheet_mask
from tests.fixtures.results import partial_scan


@pytest.mark.parametrize("batch_size", [1, 2, 1024])
def test_all_sheets_preserve_order_and_resolve_headers_per_sheet(
    tmp_path: Path,
    batch_size: int,
) -> None:
    path = tmp_path / "all.xlsx"
    write_book(
        path,
        Sheet("Empty", worksheet()),
        Sheet("Numeric", _NUMERIC),
        Sheet("MissingHeader", worksheet('<row r="2">' + cell("A", 2, "DE") + "</row>")),
        Sheet("First", _FIRST),
        Sheet("Unrelated", _UNRELATED),
        Sheet("Second", _SECOND, hidden=True),
        Sheet("Chart", f'<chartsheet xmlns="{_NS}"/>', kind="chartsheet"),
    )
    original = path.read_bytes()
    expected = [
        {"Country": "DE", "Value": 101},
        {"Value": 202, "Country": "DE"},
        {"Value": 203, "Country": "DE"},
    ]
    assert [
        dict(row) for row in iter_matching_rows(path, sheet_mask(), batch_size=batch_size)
    ] == expected
    with iter_matching_batches(path, sheet_mask(), batch_size=batch_size) as batches:
        actual = list(batches)
    assert [dict(row) for batch in actual for row in batch] == expected
    assert all(1 <= len(batch) <= batch_size for batch in actual)
    assert path.read_bytes() == original


@pytest.mark.parametrize("sheet", [None, "Offset"])
@pytest.mark.parametrize("batch_size", [1, 2, 1024])
def test_offset_multiline_header_projects_only_nested_mask_columns(
    tmp_path: Path,
    sheet: str | None,
    batch_size: int,
) -> None:
    path = tmp_path / "offset.xlsx"
    document = worksheet(
        '<row r="1">' + cell("A", 1, "Synthetic report") + "</row>",
        '<row r="3">' + cell("B", 3, "Country\nCode") + "</row>",
        '<row r="5">' + cell("D", 5, 123) + "</row>",
        '<row r="7">'
        + cell("F", 7, "Country\nCode")
        + cell("H", 7, "Budget\nEUR")
        + cell("K", 7, "Owner\nStatus")
        + cell("N", 7, "Comment")
        + cell("O", 7, "Flag values separately")
        + cell("P", 7, 2026)
        + "</row>",
        '<row r="8">' + cell("N", 8, "Comment before actual data") + "</row>",
        '<row r="10">'
        + cell("F", 10, "DE")
        + cell("H", 10, 1200)
        + cell("K", 10, "approved")
        + '<c r="N10" t="s"><v>999999</v></c></row>',
        '<row r="11">'
        + cell("F", 11, "AT")
        + cell("H", 11, 1500)
        + cell("K", 11, "review")
        + "</row>",
        '<row r="13">'
        + cell("F", 13, "AT")
        + cell("H", 13, 1600)
        + cell("K", 13, "approved")
        + "</row>",
    )
    write_book(path, Sheet("Offset", document))
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
    write_book(
        path,
        Sheet(
            "Offset",
            worksheet(
                '<row r="4">'
                + cell("C", 4, "Country")
                + cell("D", 4, "Other")
                + cell("E", 4, "Other")
                + cell("F", 4, "Other_1")
                + "</row>",
                '<row r="5">' + cell("C", 5, "DE") + "</row>",
                '<row r="8">' + cell("C", 8, "Country") + "</row>",
                '<row r="9">' + cell("C", 9, "AT") + "</row>",
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


def test_unbound_columns_are_not_filter_headers(tmp_path: Path) -> None:
    path = tmp_path / "unknown-header.xlsx"
    make_workbook(path)
    mask = FilterMask(
        sheet="Data", where=ScalarCondition(column="__column_M", op=Operator.EQ, value="x")
    )
    with pytest.raises(ValueError, match="Unknown column"):
        iter_matching_batches(path, mask)


def test_header_row_offset(tmp_path: Path) -> None:
    xlsx = tmp_path / "header-row-two.xlsx"
    make_workbook(xlsx, header_row=2)
    mask = {
        "sheet": "Data",
        "where": {"column": "Status", "op": "eq", "value": "Active"},
    }
    assert len(list(iter_matching_rows(xlsx, mask))) == 6


@pytest.mark.parametrize("header_row", [1, 3])
@pytest.mark.parametrize("batch_size", [1, 2, 1024])
def test_duplicate_headers_are_indexed_for_filters_and_output(
    tmp_path: Path,
    header_row: int,
    batch_size: int,
) -> None:
    path = tmp_path / "duplicates.xlsx"
    indexed_workbook(path, header_row=header_row)
    original = path.read_bytes()
    expected = [
        {"Revenue_1": 5000, "Revenue_2": "Active"},
        {"Revenue_1": 8000, "Revenue_2": "Active"},
        {"Revenue_1": 3200, "Revenue_2": "Active"},
    ]
    assert [
        dict(row) for row in iter_matching_rows(path, indexed_mask(), batch_size=batch_size)
    ] == expected
    with iter_matching_batches(path, indexed_mask(), batch_size=batch_size) as batches:
        assert [dict(row) for batch in batches for row in batch] == expected
    assert path.read_bytes() == original


def test_three_occurrences_retain_physical_order_and_values(tmp_path: Path) -> None:
    path = tmp_path / "three.xlsx"
    indexed_workbook(path, headers=("Customer", "Revenue", "Revenue", "Revenue"))
    mask = FilterMask(
        sheet="Data",
        where=AllOf(
            conditions=(
                ScalarCondition(column="Revenue_1", op=Operator.EQ, value="DE"),
                NumericCondition(column="Revenue_2", op=Operator.GTE, value=1000),
                ScalarCondition(column="Revenue_3", op=Operator.EQ, value="Active"),
            )
        ),
    )
    assert [dict(row) for row in iter_matching_rows(path, mask)] == [
        {"Revenue_1": "DE", "Revenue_2": 5000, "Revenue_3": "Active"},
        {"Revenue_1": "DE", "Revenue_2": 3200, "Revenue_3": "Active"},
    ]


@pytest.mark.parametrize(
    "headers",
    [
        ("Revenue_1", "Country", "Revenue", "Revenue"),
        ("Customer", "Revenue", "Revenue", "Revenue_1"),
    ],
)
def test_index_collision_fails_at_scan_end(
    tmp_path: Path,
    headers: tuple[str, ...],
) -> None:
    path = tmp_path / "collision.xlsx"
    indexed_workbook(path, headers=headers)
    with (
        pytest.raises(RuntimeError, match="SCHEMA_MISMATCH"),
        iter_matching_batches(path, indexed_mask()) as batches,
    ):
        list(batches)


def test_missing_text_header_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "numeric-header.xlsx"
    indexed_workbook(path, headers=("Customer", "Country", 123, "Status"))
    with pytest.raises(ValueError, match="No header"):
        iter_matching_batches(path, indexed_mask())


def test_header_normalization_and_collision_fail_closed(tmp_path: Path) -> None:
    path = tmp_path / "normalized.csv"
    path.write_text(" CODE ,Amount\na,1\n")
    mask = {
        "sheet": None,
        "header": {"trim": True, "lowercase": True, "anchors": ["code", "amount"]},
    }
    assert dict(next(iter_matching_rows(path, mask))) == {"code": "a", "amount": "1"}
    path.write_text(" CODE ,code\na,b\n")
    with pytest.raises((ValueError, RuntimeError), match="SCHEMA_MISMATCH"):
        list(iter_matching_rows(path, mask))


def test_merged_header_expansion_is_native(tmp_path) -> None:
    path = tmp_path / "merged.xlsx"
    document = worksheet(
        '<row r="1">' + cell("A", 1, "Revenue") + "</row>",
        '<row r="2">' + cell("A", 2, "EUR") + cell("B", 2, "USD") + "</row>",
        '<row r="3">' + cell("A", 3, 1) + cell("B", 3, 2) + "</row>",
    ).replace("</worksheet>", '<mergeCells><mergeCell ref="A1:B1"/></mergeCells></worksheet>')
    write_book(path, Sheet("Data", document))
    mask = {
        "sheet": None,
        "sources": [
            {
                "header_start_row": 1,
                "data_start_row": 3,
                "rules": {"header": {"rows": 2, "merged_fill": True}},
            }
        ],
    }
    assert dict(next(iter_matching_rows(path, mask))) == {"Revenue EUR": 1, "Revenue USD": 2}


def test_normalization_collision_quarantines_only_its_table(tmp_path: Path) -> None:
    path = tmp_path / "collision.xlsx"
    write_book(
        path,
        Sheet(
            "Data",
            worksheet_rows(
                [
                    (" CODE ", "code", "Value", None, "code", "Value"),
                    ("x", "y", 1, None, "ok", 2),
                    (),
                    (None, None, None, None, "code", "Value"),
                    (None, None, None, None, "later", 3),
                ]
            ),
        ),
    )
    mask = {
        "sheet": None,
        "header": {"anchors": ["code", "value"], "trim": True, "lowercase": True},
        "select": ["*"],
    }
    records, statistics = partial_scan(path, mask, 1)
    assert [r.values for r in records if r.kind == RecordKind.MATCHED] == [
        {"code": "ok", "value": 2},
        {"code": "later", "value": 3},
    ]
    rejected = [r for r in records if r.kind == RecordKind.REJECTED]
    assert rejected[0].values == {"A": "x", "B": "y", "C": 1}
    assert any(d.code == "SCHEMA_MISMATCH" for d in statistics.diagnostics)


def test_free_multiline_headers_use_same_rule_after_first_table(tmp_path: Path) -> None:
    path = tmp_path / "multi.xlsx"
    write_book(
        path,
        Sheet(
            "Data",
            worksheet_rows(
                [
                    ("Account", "Revenue"),
                    ("ID", "EUR"),
                    ("one", 1),
                    ("Account", "Revenue"),
                    ("ID", "EUR"),
                    ("two", 3),
                    (),
                    ("City", "Population"),
                    ("Name", "Count"),
                    ("Berlin", 2),
                ]
            ),
        ),
    )
    with scan_batches(path, {"sheet": None, "header": {"rows": 2}}) as batches:
        records = [r for batch in batches for r in batch]
    assert [r.values for r in records] == [
        {"Account ID": "one", "Revenue EUR": 1},
        {"Account ID": "two", "Revenue EUR": 3},
        {"City Name": "Berlin", "Population Count": 2},
    ]


def test_indexed_collision_does_not_hide_independent_neighbor(tmp_path: Path) -> None:
    path = tmp_path / "indexed.csv"
    path.write_text("Value_1,Value,Value,,Value_1,Value_2\nx,1,2,,3,4\n")
    records, _ = partial_scan(
        path,
        {
            "sheet": None,
            "where": {
                "all": [
                    {"column": "Value_1", "op": "ne", "value": "x"},
                    {"column": "Value_2", "op": "ne", "value": "x"},
                ]
            },
        },
        1,
    )
    assert [r.values for r in records if r.kind == RecordKind.MATCHED] == [
        {"Value_1": "3", "Value_2": "4"}
    ]


def test_empty_normalized_free_schema_does_not_abort_neighbor(tmp_path: Path) -> None:
    path = tmp_path / "empty-headers.csv"
    path.write_text("  ,  ,,Name,Count\n1,2,,ok,3\n")
    records, _ = partial_scan(path, {"sheet": None, "header": {"trim": True}}, 1)
    assert [r.values for r in records if r.kind == RecordKind.MATCHED] == [
        {"Name": "ok", "Count": "3"}
    ]
