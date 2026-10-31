"""Several table instances share a sheet, rows, and an unchanged filter mask."""

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest
from test_all_sheets import _book, _Sheet, _worksheet
from test_contract import _rewrite
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

_LABELS = ("Code\nID", "Amount\nEUR", "Owner\nStatus")


@dataclass(frozen=True, slots=True)
class Placement:
    header_row: int
    columns: tuple[str, str, str]
    base_amount: int
    shared: bool = False


def _document(*tables: Placement) -> str:
    rows: list[str] = []
    for number in range(1, max(table.header_row for table in tables) + 6):
        cells: list[tuple[str, str]] = []
        for table in tables:
            if number == table.header_row:
                for index, (column, label) in enumerate(zip(table.columns, _LABELS, strict=True)):
                    value = (
                        _cell(column, number, index, "shared")
                        if table.shared
                        else _cell(column, number, label)
                    )
                    cells.append((column, value))
            offset = number - table.header_row - 2
            if 0 <= offset <= 3:
                code = ("IT", "MK", "HR", "OPS")[offset]
                status = "review" if offset == 1 else "approved"
                for column, value in zip(
                    table.columns, (code, table.base_amount + offset, status), strict=True
                ):
                    cells.append((column, _cell(column, number, value)))
        if cells:
            cells.sort(key=lambda item: (len(item[0]), item[0]))
            rows.append(f'<row r="{number}">' + "".join(value for _, value in cells) + "</row>")
    return _worksheet(*rows)


def _mask(sheet: str | None = None) -> FilterMask:
    return FilterMask(
        sheet=sheet,
        where=AllOf(
            conditions=(
                AnyOf(
                    conditions=(
                        ScalarCondition(column=_LABELS[0], op=Operator.EQ, value="HR"),
                        ScalarCondition(column=_LABELS[0], op=Operator.EQ, value="OPS"),
                    )
                ),
                NumericCondition(column=_LABELS[1], op=Operator.GTE, value=900),
                Not(
                    condition=TextCondition(column=_LABELS[2], op=Operator.CONTAINS, value="review")
                ),
            )
        ),
    )


def _layout(path: Path) -> None:
    _book(
        path,
        _Sheet("First", _document(Placement(1, ("A", "B", "C"), 900))),
        _Sheet(
            "Four",
            _document(
                Placement(3, ("B", "D", "G"), 1000),
                Placement(3, ("H", "J", "M"), 2000),
                Placement(10, ("B", "D", "G"), 3000),
                Placement(11, ("J", "L", "O"), 4000, shared=True),
            ),
        ),
    )
    for original, label in zip(("Kunde", "Land", "Umsatz"), _LABELS, strict=True):
        _rewrite(path, "xl/sharedStrings.xml", f"<t>{original}</t>", f"<t>{label}</t>")


@pytest.mark.parametrize("batch_size", [1, 2, 3, 1024])
@pytest.mark.parametrize("sheet", [None, "Four"])
def test_side_by_side_stacked_and_shifted_tables_each_produce_their_matches(
    tmp_path: Path,
    batch_size: int,
    sheet: str | None,
) -> None:
    path = tmp_path / "many.xlsx"
    _layout(path)
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
    mask = _mask(sheet)
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
    _book(
        path,
        _Sheet(
            "Data",
            _document(
                Placement(3, ("B", "D", "G"), 1000),
                Placement(3, ("J", "H", "M"), 2000),
            ),
        ),
    )
    rows = list(iter_matching_rows(path, _mask(), batch_size=batch_size))
    assert [row[_LABELS[1]] for row in rows] == [1002, 2002, 1003, 2003]
    assert [tuple(row) for row in rows] == [_LABELS, (_LABELS[1], _LABELS[0], _LABELS[2])] * 2
    # One table passes only the amount, the other only the status: neither may pass.
    _rewrite(path, "xl/worksheets/part-17.xml", "<v>1002</v>", "<v>800</v>")
    _rewrite(path, "xl/worksheets/part-17.xml", _cell("M", 7, "approved"), _cell("M", 7, "review"))
    rows = list(iter_matching_rows(path, _mask(), batch_size=batch_size))
    assert [row[_LABELS[1]] for row in rows] == [1003, 2003]


def test_later_discovered_table_failure_keeps_cli_output_atomic(tmp_path: Path) -> None:
    path = tmp_path / "corrupt.xlsx"
    _layout(path)
    mask = tmp_path / "mask.json"
    mask.write_text(_mask().model_dump_json(by_alias=True))
    target = tmp_path / "out.ndjson"
    target.write_text("previous")
    _rewrite(
        path,
        "xl/worksheets/part-18.xml",
        _cell("O", 16, "approved"),
        '<c r="O16" t="s"><v>999999</v></c>',
    )
    with iter_matching_batches(path, _mask(), batch_size=1) as batches:
        assert next(batches)[0][_LABELS[1]] == 902
        with pytest.raises(RuntimeError, match="Shared-String-Index"):
            list(batches)
    result = subprocess.run(
        [sys.executable, "-m", "chooong.datasift", str(path), str(mask), "--output", str(target)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert target.read_text() == "previous"
    assert not list(tmp_path.glob(".out.ndjson.*.tmp"))


def test_cli_extracts_all_ten_entries(tmp_path: Path) -> None:
    path = tmp_path / "cli.xlsx"
    _layout(path)
    mask = tmp_path / "mask.json"
    mask.write_text(_mask().model_dump_json(by_alias=True))
    target = tmp_path / "out.ndjson"
    result = subprocess.run(
        [sys.executable, "-m", "chooong.datasift", str(path), str(mask), "--output", str(target)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    rows = [json.loads(line) for line in target.read_text().splitlines()]
    assert len(rows) == 10
    assert all(set(row) == set(_LABELS) for row in rows)


@pytest.mark.parametrize("batch_size", [1, 1024])
def test_new_header_does_not_hide_neighbor_table_data_on_same_row(
    tmp_path: Path,
    batch_size: int,
) -> None:
    path = tmp_path / "header-next-to-data.xlsx"
    _book(
        path,
        _Sheet(
            "Data",
            _document(
                Placement(3, ("B", "D", "G"), 1000),
                Placement(7, ("H", "J", "M"), 2000),
            ),
        ),
    )
    rows = list(iter_matching_rows(path, _mask(), batch_size=batch_size))
    assert [row[_LABELS[1]] for row in rows] == [1002, 1003, 2002, 2003]


@pytest.mark.parametrize("batch_size", [1, 1024])
def test_later_duplicate_header_schema_is_found_outside_active_columns(
    tmp_path: Path,
    batch_size: int,
) -> None:
    path = tmp_path / "indexed-later.xlsx"
    _book(
        path,
        _Sheet(
            "Data",
            _worksheet(
                '<row r="1">' + _cell("A", 1, "Amount") + _cell("B", 1, "Amount") + "</row>",
                '<row r="2">' + _cell("A", 2, 1000) + _cell("B", 2, "approved") + "</row>",
                '<row r="4">' + _cell("D", 4, "Amount") + _cell("E", 4, "Amount") + "</row>",
                '<row r="5">'
                + _cell("A", 5, 1500)
                + _cell("B", 5, "approved")
                + _cell("D", 5, 2000)
                + _cell("E", 5, "approved")
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
