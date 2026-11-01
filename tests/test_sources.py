"""Explicit table scope: actual OOXML, no header heuristics or internal mocks."""

import json
import subprocess
import sys
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from pydantic import ValidationError
from test_contract import _rewrite
from test_engine import _cell, make_workbook

from chooong.datasift import (
    AllOf,
    ColumnBinding,
    EmptyCondition,
    FilterMask,
    Operator,
    ScalarCondition,
    TableSource,
    TextCondition,
    iter_matching_batches,
    iter_matching_rows,
)


def _layout_workbook(path: Path) -> None:
    make_workbook(path)
    rows = [
        '<row r="1">' + _cell("A", 1, "Synthetic title") + "</row>",
        '<row r="3">'
        + _cell("C", 3, "Kunde")
        + _cell("D", 3, "Umsatz")
        + _cell("E", 3, "Umsatz")
        + _cell("G", 3, "Kunde")
        + _cell("H", 3, "Umsatz")
        + "</row>",
        '<row r="4">'
        + _cell("C", 4, "Name")
        + _cell("D", 4, "Aktuell")
        + _cell("E", 4, "Vorjahr")
        + _cell("G", 4, "Name")
        + _cell("H", 4, "Aktuell")
        + "</row>",
        '<row r="5">' + _cell("C", 5, "Comment between header and data") + "</row>",
        '<row r="7">'
        + _cell("C", 7, "ABC One")
        + _cell("D", 7, 120)
        + _cell("E", 7, 80)
        + _cell("G", 7, "XYZ Other")
        + _cell("H", 7, 999)
        + '<c r="M7" t="s"><v>999999</v></c></row>',
        '<row r="8">'
        + _cell("C", 8, "ABC Comment")
        + _cell("D", 8, 1000)
        + _cell("E", 8, 1000)
        + _cell("G", 8, "ABC Comment")
        + _cell("H", 8, 1000)
        + "</row>",
        '<row r="9">'
        + _cell("C", 9, "NO")
        + _cell("D", 9, 50)
        + _cell("E", 9, 40)
        + _cell("G", 9, "ABC Right One")
        + _cell("H", 9, 150)
        + "</row>",
        '<row r="10">'
        + _cell("C", 10, "ABC Two")
        + _cell("D", 10, 200)
        + _cell("E", 10, 180)
        + _cell("G", 10, "ABC Right Two")
        + _cell("H", 10, 250)
        + "</row>",
        '<row r="11">'
        + _cell("C", 11, "ABC Footer")
        + _cell("D", 11, 999)
        + _cell("E", 11, 999)
        + "</row>",
    ]
    with ZipFile(path) as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}
    parts["xl/worksheets/data42.xml"] = (
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        "<sheetData>" + "".join(rows) + '</sheetData><mergeCells count="1">'
        '<mergeCell ref="A1:H1"/></mergeCells></worksheet>'
    ).encode()
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
        for name, content in parts.items():
            archive.writestr(name, content)


def _source_mask() -> FilterMask:
    return FilterMask.model_validate_json(
        (Path(__file__).resolve().parents[1] / "examples/layout-filter.json").read_text()
    )


@pytest.mark.parametrize("batch_size", [1, 2, 1024])
def test_offset_multiline_duplicate_headers_comments_and_neighbor_table(
    tmp_path: Path,
    batch_size: int,
) -> None:
    path = tmp_path / "layout.xlsx"
    _layout_workbook(path)
    original = path.read_bytes()
    expected = [
        {"Kunde": "ABC One", "Umsatz": 120},
        {"Kunde": "ABC Two", "Umsatz": 200},
    ]
    assert [
        dict(row) for row in iter_matching_rows(path, _source_mask(), batch_size=batch_size)
    ] == expected
    with iter_matching_batches(path, _source_mask(), batch_size=batch_size) as batches:
        assert [dict(row) for batch in batches for row in batch] == expected
    assert path.read_bytes() == original


def test_neighbor_table_is_selected_independently(tmp_path: Path) -> None:
    path = tmp_path / "neighbor.xlsx"
    _layout_workbook(path)
    mask = FilterMask(
        sheet="Daten",
        source=TableSource(
            columns=(
                ColumnBinding(name="Kunde", column="G"),
                ColumnBinding(name="Umsatz", column="H"),
            ),
            data_start_row=7,
            data_end_row=10,
            skip_rows=(8,),
        ),
        where=_source_mask().where,
    )
    assert [dict(row) for row in iter_matching_rows(path, mask)] == [
        {"Kunde": "ABC Right One", "Umsatz": 150},
        {"Kunde": "ABC Right Two", "Umsatz": 250},
    ]


def test_end_of_sheet_and_multiple_aliases_for_same_column(tmp_path: Path) -> None:
    path = tmp_path / "aliases.xlsx"
    _layout_workbook(path)
    mask = FilterMask(
        sheet="Daten",
        source=TableSource(
            columns=(
                ColumnBinding(name="Kunde", column="C"),
                ColumnBinding(name="Copy", column="C"),
            ),
            data_start_row=10,
        ),
        where=AllOf(
            conditions=(
                TextCondition(column="Kunde", op=Operator.STARTS_WITH, value="ABC"),
                EmptyCondition(column="Copy", op=Operator.NOT_EMPTY),
            )
        ),
    )
    assert [dict(row) for row in iter_matching_rows(path, mask)] == [
        {"Kunde": "ABC Two", "Copy": "ABC Two"},
        {"Kunde": "ABC Footer", "Copy": "ABC Footer"},
    ]


@pytest.mark.parametrize(
    "updates",
    [
        {"data_start_row": True},
        {"data_start_row": 0},
        {"data_end_row": 6},
        {"data_end_row": 1048577},
        {"skip_rows": [6]},
        {"skip_rows": [11]},
        {"columns": []},
        {"columns": [{"name": "x", "column": "XFE"}]},
        {"columns": [{"name": "x", "column": "a"}]},
        {"columns": [{"name": "x", "column": "A1"}]},
        {"columns": [{"name": " ", "column": "A"}]},
        {"columns": [{"name": "x", "column": "A"}, {"name": "x", "column": "B"}]},
        {"unexpected": "field"},
    ],
)
def test_invalid_scopes_fail_before_io(updates: dict[str, object]) -> None:
    payload = _source_mask().model_dump(by_alias=True)
    source = _source_mask().source
    assert source is not None
    source_payload = source.model_dump()
    source_payload.update(updates)
    payload["source"] = source_payload
    with pytest.raises(ValidationError):
        iter_matching_batches("missing.xlsx", payload)


def test_source_rejects_conflicting_header_and_unknown_alias(tmp_path: Path) -> None:
    payload = _source_mask().model_dump(by_alias=True)
    payload["header_row"] = 3
    with pytest.raises(ValidationError, match="header_row"):
        iter_matching_batches("missing.xlsx", payload)
    path = tmp_path / "unknown.xlsx"
    _layout_workbook(path)
    mask = FilterMask(
        sheet="Daten",
        source=_source_mask().source,
        where=ScalarCondition(column="Unknown", op=Operator.EQ, value="x"),
    )
    with (
        pytest.raises(RuntimeError, match="SCHEMA_MISMATCH"),
        iter_matching_batches(path, mask) as batches,
    ):
        list(batches)


def test_selected_corruption_is_an_error_and_cli_preserves_existing_output(tmp_path: Path) -> None:
    path = tmp_path / "corrupt-selected.xlsx"
    _layout_workbook(path)
    _rewrite(
        path,
        "xl/worksheets/data42.xml",
        '<c r="D10"><v>200</v></c>',
        '<c r="D10" t="s"><v>999999</v></c>',
    )
    mask_file = tmp_path / "mask.json"
    mask_file.write_text(_source_mask().model_dump_json(by_alias=True))
    target = tmp_path / "target.ndjson"
    target.write_text("previous")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "chooong.datasift",
            str(path),
            str(mask_file),
            "--output",
            str(target),
            "--batch-size",
            "1",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "RuntimeError" in result.stderr
    assert target.read_text() == "previous"
    assert not list(tmp_path.glob(".target.ndjson.*.tmp"))


def test_source_still_rejects_truncated_xml_after_selected_range(tmp_path: Path) -> None:
    path = tmp_path / "truncated.xlsx"
    _layout_workbook(path)
    _rewrite(path, "xl/worksheets/data42.xml", "</worksheet>", "")
    with pytest.raises(RuntimeError, match="unvollständig"):
        list(iter_matching_rows(path, _source_mask()))


def test_layout_example_cli_output(tmp_path: Path) -> None:
    path = tmp_path / "layout-cli.xlsx"
    _layout_workbook(path)
    mask = tmp_path / "mask.json"
    mask.write_text(_source_mask().model_dump_json(by_alias=True))
    output = tmp_path / "output.ndjson"
    result = subprocess.run(
        [sys.executable, "-m", "chooong.datasift", str(path), str(mask), "--output", str(output)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert [json.loads(line) for line in output.read_text().splitlines()] == [
        {"Kunde": "ABC One", "Umsatz": 120},
        {"Kunde": "ABC Two", "Umsatz": 200},
    ]
