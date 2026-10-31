"""Actual OOXML workbooks: worksheet order, schema changes and atomic output."""

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from xml.sax.saxutils import quoteattr
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

_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"


def _worksheet(*rows: str) -> str:
    return f'<worksheet xmlns="{_NS}"><sheetData>' + "".join(rows) + "</sheetData></worksheet>"


_FIRST = _worksheet(
    '<row r="1">' + _cell("A", 1, "Land") + _cell("B", 1, "Value") + "</row>",
    '<row r="2">' + _cell("A", 2, "DE") + _cell("B", 2, 101) + "</row>",
    '<row r="3">' + _cell("A", 3, "AT") + _cell("B", 3, 1) + "</row>",
)
_SECOND = _worksheet(
    '<row r="1">'
    + _cell("A", 1, "Value")
    + _cell("C", 1, "Land")
    + _cell("D", 1, "Note")
    + "</row>",
    '<row r="2">' + _cell("A", 2, 202) + _cell("C", 2, "DE") + _cell("D", 2, "second") + "</row>",
    '<row r="3">' + _cell("A", 3, 203) + _cell("C", 3, "DE") + _cell("D", 3, "repeat") + "</row>",
)
_NUMERIC = _worksheet('<row r="1">' + _cell("A", 1, 99) + "</row>")
_UNRELATED = _worksheet('<row r="1">' + _cell("A", 1, "Other") + "</row>")


@dataclass(frozen=True, slots=True)
class _Sheet:
    name: str
    document: str
    kind: Literal["worksheet", "chartsheet"] = "worksheet"
    hidden: bool = False


def _book(path: Path, *sheets: _Sheet) -> None:
    make_workbook(path)
    with ZipFile(path) as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}
    labels: list[str] = []
    relations: list[str] = []
    types: list[str] = []
    for index, sheet in enumerate(sheets):
        part = f"{sheet.kind}s/part-{index + 17}.xml"
        relation_id = f"rId{index + 70}"
        state = ' state="hidden"' if sheet.hidden else ""
        labels.append(
            f'<sheet name={quoteattr(sheet.name)} sheetId="{index + 1}"'
            f' r:id="{relation_id}"{state}/>'
        )
        relations.append(
            f'<Relationship Id="{relation_id}" '
            f'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/{sheet.kind}"'
            f' Target="{part}"/>'
        )
        types.append(
            f'<Override PartName="/xl/{part}" '
            'ContentType="application/vnd.openxmlformats-officedocument.'
            f'spreadsheetml.{sheet.kind}+xml"/>'
        )
        parts["xl/" + part] = sheet.document.encode()
    parts["xl/workbook.xml"] = (
        f'<workbook xmlns="{_NS}" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        "<sheets>" + "".join(labels) + "</sheets></workbook>"
    ).encode()
    parts["xl/_rels/workbook.xml.rels"] = (
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        + "".join(reversed(relations))
        + '<Relationship Id="rShared" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings" '
        'Target="sharedStrings.xml"/></Relationships>'
    ).encode()
    parts["[Content_Types].xml"] = parts["[Content_Types].xml"].replace(
        b"</Types>", "".join(types).encode() + b"</Types>"
    )
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
        for name, content in parts.items():
            archive.writestr(name, content)


def _mask(sheet: str | None = None) -> FilterMask:
    return FilterMask(
        sheet=sheet,
        where=AllOf(
            conditions=(
                ScalarCondition(column="Land", op=Operator.EQ, value="DE"),
                EmptyCondition(column="Value", op=Operator.NOT_EMPTY),
            )
        ),
    )


@pytest.mark.parametrize("batch_size", [1, 2, 1024])
def test_all_sheets_preserve_order_and_resolve_headers_per_sheet(
    tmp_path: Path,
    batch_size: int,
) -> None:
    path = tmp_path / "all.xlsx"
    _book(
        path,
        _Sheet("Empty", _worksheet()),
        _Sheet("Numeric", _NUMERIC),
        _Sheet("MissingHeader", _worksheet('<row r="2">' + _cell("A", 2, "DE") + "</row>")),
        _Sheet("First", _FIRST),
        _Sheet("Unrelated", _UNRELATED),
        _Sheet("Second", _SECOND, hidden=True),
        _Sheet("Chart", f'<chartsheet xmlns="{_NS}"/>', kind="chartsheet"),
    )
    original = path.read_bytes()
    expected = [
        {"Land": "DE", "Value": 101},
        {"Value": 202, "Land": "DE"},
        {"Value": 203, "Land": "DE"},
    ]
    assert [
        dict(row) for row in iter_matching_rows(path, _mask(), batch_size=batch_size)
    ] == expected
    with iter_matching_batches(path, _mask(), batch_size=batch_size) as batches:
        actual = list(batches)
    assert [dict(row) for batch in actual for row in batch] == expected
    assert all(1 <= len(batch) <= batch_size for batch in actual)
    assert path.read_bytes() == original


@pytest.mark.parametrize(
    ("name", "amounts"), [("First", [101]), ("Second", [202, 203]), ("null", [202, 203])]
)
def test_named_sheet_and_literal_null_string_still_select_one_sheet(
    tmp_path: Path,
    name: str,
    amounts: list[int],
) -> None:
    path = tmp_path / "one.xlsx"
    _book(path, _Sheet("First", _FIRST), _Sheet("Second", _SECOND), _Sheet("null", _SECOND))
    assert [row["Value"] for row in iter_matching_rows(path, _mask(name))] == amounts


def test_source_scope_applies_to_every_sheet(tmp_path: Path) -> None:
    path = tmp_path / "source.xlsx"
    _book(path, _Sheet("First", _FIRST), _Sheet("Second", _SECOND))
    mask = FilterMask(
        sheet=None,
        source=TableSource(
            columns=(
                ColumnBinding(name="Country", column="C"),
                ColumnBinding(name="Amount", column="A"),
            ),
            data_start_row=2,
            data_end_row=2,
        ),
        where=ScalarCondition(column="Country", op=Operator.EQ, value="DE"),
    )
    assert [dict(row) for row in iter_matching_rows(path, mask)] == [{"Country": "DE"}]


def test_no_matching_schema_is_an_empty_result(tmp_path: Path) -> None:
    path = tmp_path / "no-schema.xlsx"
    _book(
        path,
        _Sheet("Empty", _worksheet()),
        _Sheet("Numeric", _NUMERIC),
        _Sheet("MissingHeader", _worksheet('<row r="2">' + _cell("A", 2, "DE") + "</row>")),
        _Sheet("Unrelated", _UNRELATED),
    )
    assert list(iter_matching_rows(path, _mask())) == []


def test_invalid_regex_and_missing_sheet_field_fail_eagerly(tmp_path: Path) -> None:
    path = tmp_path / "empty.xlsx"
    _book(path, _Sheet("Empty", _worksheet()))
    mask = FilterMask(sheet=None, where=TextCondition(column="Land", op=Operator.REGEX, value="("))
    with pytest.raises(ValueError, match="Ungültiger Regex"):
        iter_matching_batches(path, mask)
    with pytest.raises(ValidationError):
        iter_matching_batches(path, {"where": {"column": "Land", "op": "eq", "value": "DE"}})


def test_late_sheet_failure_propagates_and_cli_keeps_existing_output(tmp_path: Path) -> None:
    path = tmp_path / "late.xlsx"
    broken = _SECOND.replace(_cell("A", 2, 202), '<c r="A2" t="s"><v>999999</v></c>')
    _book(path, _Sheet("First", _FIRST), _Sheet("Broken", broken))
    with iter_matching_batches(path, _mask(), batch_size=1) as batches:
        assert dict(next(batches)[0]) == {"Land": "DE", "Value": 101}
        with pytest.raises(RuntimeError, match="Shared-String-Index"):
            list(batches)
    mask = tmp_path / "mask.json"
    mask.write_text(_mask().model_dump_json(by_alias=True))
    target = tmp_path / "result.ndjson"
    target.write_text("previous")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "chooong.datasift",
            str(path),
            str(mask),
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
    assert target.read_text() == "previous"
    assert not list(tmp_path.glob(".result.ndjson.*.tmp"))


def test_skipped_schema_does_not_hide_truncated_xml(tmp_path: Path) -> None:
    path = tmp_path / "truncated.xlsx"
    _book(
        path, _Sheet("First", _FIRST), _Sheet("Unrelated", _UNRELATED.removesuffix("</worksheet>"))
    )
    with pytest.raises(RuntimeError, match="unvollständig"):
        list(iter_matching_rows(path, _mask()))


def test_external_sheet_is_rejected_without_affecting_named_selection(tmp_path: Path) -> None:
    path = tmp_path / "external.xlsx"
    _book(path, _Sheet("First", _FIRST), _Sheet("Second", _SECOND))
    _rewrite(
        path,
        "xl/_rels/workbook.xml.rels",
        'Target="worksheets/part-18.xml"',
        'Target="https://invalid.example/sheet.xml" TargetMode="External"',
    )
    assert [row["Value"] for row in iter_matching_rows(path, _mask("First"))] == [101]
    with pytest.raises(ValueError, match="Externes Arbeitsblatt"):
        iter_matching_batches(path, _mask())


def test_cli_merges_all_sheet_hits(tmp_path: Path) -> None:
    path = tmp_path / "cli.xlsx"
    _book(path, _Sheet("First", _FIRST), _Sheet("Second", _SECOND))
    mask = tmp_path / "mask.json"
    mask.write_text(_mask().model_dump_json(by_alias=True))
    target = tmp_path / "result.ndjson"
    result = subprocess.run(
        [sys.executable, "-m", "chooong.datasift", str(path), str(mask), "--output", str(target)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert [row["Value"] for row in map(json.loads, target.read_text().splitlines())] == [
        101,
        202,
        203,
    ]
