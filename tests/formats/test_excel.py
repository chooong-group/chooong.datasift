"""Public contract checks using real synthetic files."""

from __future__ import annotations

from pathlib import Path
from typing import Literal
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from chooong.datasift import (
    AllOf,
    FilterMask,
    Operator,
    ScalarCondition,
    TextCondition,
    iter_matching_batches,
    iter_matching_rows,
)
from tests.fixtures.excel import (
    _FIRST,
    _SECOND,
    _UNRELATED,
    Sheet,
    cell,
    layout_workbook,
    make_workbook,
    rewrite,
    worksheet,
    write_book,
)
from tests.fixtures.masks import contract_mask, sheet_mask, source_mask


def test_skipped_schema_does_not_hide_truncated_xml(tmp_path: Path) -> None:
    path = tmp_path / "truncated.xlsx"
    write_book(
        path, Sheet("First", _FIRST), Sheet("Unrelated", _UNRELATED.removesuffix("</worksheet>"))
    )
    with pytest.raises(RuntimeError, match="incomplete"):
        list(iter_matching_rows(path, sheet_mask()))


def test_external_sheet_is_rejected_without_affecting_named_selection(tmp_path: Path) -> None:
    path = tmp_path / "external.xlsx"
    write_book(path, Sheet("First", _FIRST), Sheet("Second", _SECOND))
    rewrite(
        path,
        "xl/_rels/workbook.xml.rels",
        'Target="worksheets/part-18.xml"',
        'Target="https://invalid.example/sheet.xml" TargetMode="External"',
    )
    assert [row["Value"] for row in iter_matching_rows(path, sheet_mask("First"))] == [101]
    with pytest.raises(ValueError, match="External worksheet"):
        iter_matching_batches(path, sheet_mask())


@pytest.mark.parametrize("part", ["xl/worksheets/data42.xml", "xl/sharedStrings.xml"])
def test_truncated_xml_is_not_success(tmp_path: Path, part: str) -> None:
    path = tmp_path / "truncated.xlsx"
    make_workbook(path)
    before = "</worksheet>" if "worksheets" in part else "</sst>"
    rewrite(path, part, before, "")
    with pytest.raises((RuntimeError, ValueError), match="incomplete"):
        list(iter_matching_rows(path, contract_mask(), batch_size=1))


@pytest.mark.parametrize(
    ("part", "before", "after", "error"),
    [
        (
            "xl/workbook.xml",
            "<workbook ",
            '<!DOCTYPE workbook [<!ENTITY ext SYSTEM "file:///secret">]><workbook ',
            "DTD",
        ),
        (
            "xl/_rels/workbook.xml.rels",
            'Target="worksheets/data42.xml"',
            'Target="../../outside.xml"',
            "escape",
        ),
    ],
)
def test_unsafe_xml_and_paths_fail_closed(
    tmp_path: Path,
    part: str,
    before: str,
    after: str,
    error: str,
) -> None:
    path = tmp_path / "unsafe.xlsx"
    make_workbook(path)
    rewrite(path, part, before, after)
    with pytest.raises(ValueError, match=error):
        iter_matching_batches(path, contract_mask())


def test_source_still_rejects_truncated_xml_after_selected_range(tmp_path: Path) -> None:
    path = tmp_path / "truncated.xlsx"
    layout_workbook(path)
    rewrite(path, "xl/worksheets/data42.xml", "</worksheet>", "")
    with pytest.raises(RuntimeError, match="incomplete"):
        list(iter_matching_rows(path, source_mask()))


@pytest.mark.parametrize("storage", ["inline", "shared", "cdata"])
@pytest.mark.parametrize("eol", ["\n", "\r\n", "\r"])
def test_xml_line_endings_preserve_header_and_data_semantics(
    tmp_path: Path,
    storage: Literal["inline", "shared", "cdata"],
    eol: str,
) -> None:
    path = tmp_path / "line-endings.xlsx"
    label = f"Label{eol}Code"
    value = f"first{eol}second"
    if storage == "shared":
        header = cell("C", 7, 0, "shared")
        data = cell("D", 8, 1, "shared")
    elif storage == "cdata":
        header = f'<c r="C7" t="inlineStr"><is><t><![CDATA[{label}]]></t></is></c>'
        data = f'<c r="D8" t="inlineStr"><is><t><![CDATA[{value}]]></t></is></c>'
    else:
        header = cell("C", 7, label)
        data = cell("D", 8, value)
    write_book(
        path,
        Sheet(
            "Offset",
            worksheet(
                '<row r="2">' + cell("A", 2, "Synthetic title") + "</row>",
                '<row r="7">' + header + cell("D", 7, "Note") + "</row>",
                '<row r="8">' + cell("C", 8, "A") + data + "</row>",
            ),
        ),
    )
    if storage == "shared":
        with ZipFile(path) as archive:
            parts = {name: archive.read(name) for name in archive.namelist()}
        parts["xl/sharedStrings.xml"] = (
            '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            f"<si><t>{label}</t></si><si><t>{value}</t></si></sst>"
        ).encode()
        with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
            for name, content in parts.items():
                archive.writestr(name, content)
    mask = FilterMask(
        sheet=None,
        where=AllOf(
            conditions=(
                ScalarCondition(column="Label\nCode", op=Operator.EQ, value="A"),
                TextCondition(column="Note", op=Operator.CONTAINS, value="first\nsecond"),
            )
        ),
    )
    original = path.read_bytes()
    expected = [{"Label\nCode": "A", "Note": "first\nsecond"}]
    assert [dict(row) for row in iter_matching_rows(path, mask, batch_size=1)] == expected
    assert [dict(row) for row in iter_matching_rows(path, mask)] == expected
    assert path.read_bytes() == original


def test_explicit_character_reference_retains_carriage_return(tmp_path: Path) -> None:
    path = tmp_path / "reference.xlsx"
    write_book(
        path,
        Sheet(
            "Data",
            worksheet(
                '<row r="1">' + cell("C", 1, "Note") + "</row>",
                '<row r="2"><c r="C2" t="inlineStr"><is><t>a&#13;b</t></is></c></row>',
            ),
        ),
    )
    mask = FilterMask(
        sheet=None, where=ScalarCondition(column="Note", op=Operator.EQ, value="a\rb")
    )
    assert [dict(row) for row in iter_matching_rows(path, mask)] == [{"Note": "a\rb"}]
