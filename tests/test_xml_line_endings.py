"""Excel XML line endings must not alter header discovery or text predicates."""

from pathlib import Path
from typing import Literal
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from test_all_sheets import _book, _Sheet, _worksheet
from test_engine import _cell

from chooong.datasift import (
    AllOf,
    FilterMask,
    Operator,
    ScalarCondition,
    TextCondition,
    iter_matching_rows,
)


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
        header = _cell("C", 7, 0, "shared")
        data = _cell("D", 8, 1, "shared")
    elif storage == "cdata":
        header = f'<c r="C7" t="inlineStr"><is><t><![CDATA[{label}]]></t></is></c>'
        data = f'<c r="D8" t="inlineStr"><is><t><![CDATA[{value}]]></t></is></c>'
    else:
        header = _cell("C", 7, label)
        data = _cell("D", 8, value)
    _book(
        path,
        _Sheet(
            "Offset",
            _worksheet(
                '<row r="2">' + _cell("A", 2, "Synthetic title") + "</row>",
                '<row r="7">' + header + _cell("D", 7, "Note") + "</row>",
                '<row r="8">' + _cell("C", 8, "A") + data + "</row>",
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
    _book(
        path,
        _Sheet(
            "Data",
            _worksheet(
                '<row r="1">' + _cell("C", 1, "Note") + "</row>",
                '<row r="2"><c r="C2" t="inlineStr"><is><t>a&#13;b</t></is></c></row>',
            ),
        ),
    )
    mask = FilterMask(
        sheet=None, where=ScalarCondition(column="Note", op=Operator.EQ, value="a\rb")
    )
    assert [dict(row) for row in iter_matching_rows(path, mask)] == [{"Note": "a\rb"}]
