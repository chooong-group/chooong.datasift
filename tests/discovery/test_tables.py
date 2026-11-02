"""Public contract checks using real synthetic files."""

from __future__ import annotations

from pathlib import Path

import pytest

from chooong.datasift import (
    AllOf,
    FilterMask,
    NumericCondition,
    Operator,
    RecordKind,
    ScalarCondition,
    iter_matching_batches,
    iter_matching_rows,
    scan_batches,
)
from tests.fixtures.excel import (
    _LABELS,
    Placement,
    Sheet,
    cell,
    rewrite,
    table_document,
    table_layout,
    worksheet,
    worksheet_rows,
    write_book,
)
from tests.fixtures.masks import table_mask
from tests.fixtures.results import partial_scan


@pytest.mark.parametrize("batch_size", [1, 2, 3, 1024])
@pytest.mark.parametrize("sheet", [None, "Four"])
def test_side_by_side_stacked_and_shifted_tables_each_produce_their_matches(
    tmp_path: Path,
    batch_size: int,
    sheet: str | None,
) -> None:
    path = tmp_path / "many.xlsx"
    table_layout(path)
    original = path.read_bytes()
    amounts = [1002, 2002, 1003, 2003, 3002, 3003, 4002, 4003]
    if sheet is None:
        amounts = [902, 903, *amounts]
    expected = [
        {
            _LABELS[0]: "HR" if amount % 1000 == 2 or amount == 902 else "OPS",
            _LABELS[1]: amount,
            _LABELS[2]: "approved",
        }
        for amount in amounts
    ]
    mask = table_mask(sheet)
    assert [dict(row) for row in iter_matching_rows(path, mask, batch_size=batch_size)] == expected
    with iter_matching_batches(path, mask, batch_size=batch_size) as batches:
        actual = list(batches)
    assert [dict(row) for batch in actual for row in batch] == expected
    assert all(0 < len(batch) <= batch_size for batch in actual)
    assert path.read_bytes() == original


@pytest.mark.parametrize("batch_size", [1, 2, 1024])
def test_different_column_orders_never_mix_buffered_schema_or_table_values(
    tmp_path: Path,
    batch_size: int,
) -> None:
    path = tmp_path / "reordered.xlsx"
    write_book(
        path,
        Sheet(
            "Data",
            table_document(
                Placement(3, ("B", "D", "G"), 1000),
                Placement(3, ("J", "H", "M"), 2000),
            ),
        ),
    )
    rows = list(iter_matching_rows(path, table_mask(), batch_size=batch_size))
    assert [row[_LABELS[1]] for row in rows] == [1002, 2002, 1003, 2003]
    assert [tuple(row) for row in rows] == [_LABELS, (_LABELS[1], _LABELS[0], _LABELS[2])] * 2
    # One table passes only the amount, the other only the status: neither may pass.
    rewrite(path, "xl/worksheets/part-17.xml", "<v>1002</v>", "<v>800</v>")
    rewrite(path, "xl/worksheets/part-17.xml", cell("M", 7, "approved"), cell("M", 7, "review"))
    rows = list(iter_matching_rows(path, table_mask(), batch_size=batch_size))
    assert [row[_LABELS[1]] for row in rows] == [1003, 2003]


@pytest.mark.parametrize("batch_size", [1, 1024])
def test_new_header_does_not_hide_neighbor_table_data_on_same_row(
    tmp_path: Path,
    batch_size: int,
) -> None:
    path = tmp_path / "header-next-to-data.xlsx"
    write_book(
        path,
        Sheet(
            "Data",
            table_document(
                Placement(3, ("B", "D", "G"), 1000),
                Placement(7, ("H", "J", "M"), 2000),
            ),
        ),
    )
    rows = list(iter_matching_rows(path, table_mask(), batch_size=batch_size))
    assert [row[_LABELS[1]] for row in rows] == [1002, 1003, 2002, 2003]


@pytest.mark.parametrize("batch_size", [1, 1024])
def test_later_duplicate_header_schema_is_found_outside_active_columns(
    tmp_path: Path,
    batch_size: int,
) -> None:
    path = tmp_path / "indexed-later.xlsx"
    write_book(
        path,
        Sheet(
            "Data",
            worksheet(
                '<row r="1">' + cell("A", 1, "Amount") + cell("B", 1, "Amount") + "</row>",
                '<row r="2">' + cell("A", 2, 1000) + cell("B", 2, "approved") + "</row>",
                '<row r="4">' + cell("D", 4, "Amount") + cell("E", 4, "Amount") + "</row>",
                '<row r="5">'
                + cell("A", 5, 1500)
                + cell("B", 5, "approved")
                + cell("D", 5, 2000)
                + cell("E", 5, "approved")
                + "</row>",
            ),
        ),
    )
    mask = FilterMask(
        sheet=None,
        where=AllOf(
            conditions=(
                NumericCondition(column="Amount_1", op=Operator.GTE, value=900),
                ScalarCondition(column="Amount_2", op=Operator.EQ, value="approved"),
            )
        ),
    )
    assert [dict(row) for row in iter_matching_rows(path, mask, batch_size=batch_size)] == [
        {"Amount_1": 1000, "Amount_2": "approved"},
        {"Amount_1": 1500, "Amount_2": "approved"},
        {"Amount_1": 2000, "Amount_2": "approved"},
    ]


@pytest.mark.parametrize("batch_size", [1, 2, 1024])
def test_free_discovery_handles_different_side_by_side_and_stacked_schemas(
    tmp_path: Path, batch_size: int
) -> None:
    path = tmp_path / "free.xlsx"
    write_book(
        path,
        Sheet(
            "Data",
            worksheet_rows(
                [
                    ("A title",),
                    ("Name", "Amount", None, "Code", "Count", "Flag"),
                    ("left", 1, None, "right", 2, True),
                    (),
                    ("Another title",),
                    (None, "City", "Population"),
                    (None, "Berlin", 3),
                ]
            ),
        ),
    )
    with scan_batches(path, {"sheet": None}, batch_size=batch_size) as batches:
        records = [r for batch in batches for r in batch]
        assert batches.statistics is not None
        assert batches.statistics.complete
    assert [r.values for r in records] == [
        {"Name": "left", "Amount": 1},
        {"Code": "right", "Count": 2, "Flag": True},
        {"City": "Berlin", "Population": 3},
    ]


def test_free_text_title_and_ambiguous_text_table_are_not_silent_success(tmp_path: Path) -> None:
    path = tmp_path / "ambiguous.xlsx"
    write_book(
        path,
        Sheet(
            "Data",
            worksheet_rows(
                [
                    ("Quarter", "Report"),
                    ("Name", "State"),
                    ("Alice", "Open"),
                    (),
                    ("Code", "Count"),
                    ("ok", 2),
                ]
            ),
        ),
    )
    records, statistics = partial_scan(path, {"sheet": None}, 1)
    assert [r.values for r in records if r.kind == RecordKind.MATCHED] == [
        {"Code": "ok", "Count": 2}
    ]
    assert any(d.code == "AMBIGUOUS_HEADER" for d in statistics.diagnostics)
    assert any(r.values == {"A": "Name", "B": "State"} for r in records)
