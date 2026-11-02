"""Reusable deterministic test fixtures."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from xml.sax.saxutils import escape, quoteattr
from zipfile import ZIP_DEFLATED, ZipFile


def worksheet(*rows: str) -> str:
    return f'<worksheet xmlns="{_NS}"><sheetData>' + "".join(rows) + "</sheetData></worksheet>"


@dataclass(frozen=True, slots=True)
class Sheet:
    name: str
    document: str
    kind: Literal["worksheet", "chartsheet"] = "worksheet"
    hidden: bool = False


def write_book(path: Path, *sheets: Sheet) -> None:
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


def cli_inputs(tmp_path: Path) -> tuple[Path, Path]:
    workbook = tmp_path / "sample.xlsx"
    make_workbook(workbook)
    mask = tmp_path / "mask.json"
    mask.write_text(
        json.dumps(
            {
                "sheet": "Data",
                "where": {"column": "Country", "op": "eq", "value": "DE"},
            }
        )
    )
    return workbook, mask


def rewrite(path: Path, member: str, before: str, after: str) -> None:
    with ZipFile(path) as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}
    parts[member] = parts[member].decode().replace(before, after).encode()
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
        for name, content in parts.items():
            archive.writestr(name, content)


def cell(col: str, row: int, value: str | int | float | bool | None, kind: str = "auto") -> str:
    address = f"{col}{row}"
    if value is None:
        return f'<c r="{address}"/>'
    if kind == "shared":
        return f'<c r="{address}" t="s"><v>{int(value)}</v></c>'
    if kind == "formula":
        return f'<c r="{address}"><f>1000+2200</f><v>{value}</v></c>'
    if isinstance(value, bool):
        return f'<c r="{address}" t="b"><v>{int(value)}</v></c>'
    if isinstance(value, (int, float)):
        return f'<c r="{address}"><v>{value}</v></c>'
    return f'<c r="{address}" t="inlineStr"><is><t>{escape(value)}</t></is></c>'


def make_workbook(path: Path, *, malformed: bool = False, header_row: int = 1) -> None:
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as z:
        z.writestr(
            "[Content_Types].xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml"
 ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/worksheets/data42.xml"
 ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
<Override PartName="/xl/sharedStrings.xml"
 ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>
</Types>""",
        )
        z.writestr(
            "_rels/.rels",
            """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1"
 Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"
 Target="xl/workbook.xml"/>
</Relationships>""",
        )
        z.writestr(
            "xl/workbook.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<sheets>
<sheet name="Meta" sheetId="1" r:id="rId9"/>
<sheet name="Data" sheetId="2" r:id="rId42"/>
</sheets>
</workbook>""",
        )
        z.writestr(
            "xl/_rels/workbook.xml.rels",
            """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId9"
 Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"
 Target="worksheets/meta.xml"/>
<Relationship Id="rId42"
 Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"
 Target="worksheets/data42.xml"/>
<Relationship Id="rId55"
 Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings"
 Target="sharedStrings.xml"/>
</Relationships>""",
        )
        z.writestr(
            "xl/worksheets/meta.xml",
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"/>',
        )
        z.writestr(
            "xl/sharedStrings.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">"""
            + "".join(f"<si><t>{escape(value)}</t></si>" for value in _SHARED)
            + "<si><r><t>ABC &amp; </t></r><r><t>Sons</t></r>"
            '<rPh sb="0" eb="1"><t>IGNORED</t></rPh></si>' + "</sst>",
        )
        base = header_row
        rows = []
        rows.append(
            f'<row r="{base}">'
            + "".join(cell(chr(65 + i), base, i, "shared") for i in range(4))
            + "</row>"
        )
        rows.append(
            f'<row r="{base + 1}">'
            + "".join(
                [
                    cell("A", base + 1, 4, "shared"),
                    cell("B", base + 1, 5, "shared"),
                    cell("C", base + 1, 5000),
                    cell("D", base + 1, 6, "shared"),
                ]
            )
            + "</row>"
        )
        rows.append(
            f'<row r="{base + 2}">'
            + "".join(
                [
                    cell("A", base + 2, 7, "shared"),
                    cell("B", base + 2, 8, "shared"),
                    cell("C", base + 2, 8000),
                    cell("D", base + 2, 6, "shared"),
                ]
            )
            + "</row>"
        )
        rows.append(
            f'<row r="{base + 3}">'
            + "".join(
                [
                    cell("A", base + 3, 9, "shared"),
                    cell("B", base + 3, 5, "shared"),
                    cell("C", base + 3, 750),
                    cell("D", base + 3, 6, "shared"),
                ]
            )
            + "</row>"
        )
        rows.append(
            f'<row r="{base + 4}">'
            + "".join(
                [
                    cell("A", base + 4, 10, "shared"),
                    cell("B", base + 4, 5, "shared"),
                    cell("C", base + 4, 3200, "formula"),
                    cell("D", base + 4, 6, "shared"),
                ]
            )
            + "</row>"
        )
        rows.append(
            f'<row r="{base + 5}">'
            + "".join(
                [
                    cell("A", base + 5, 11, "shared"),
                    cell("B", base + 5, 5, "shared"),
                    cell("C", base + 5, 2500),
                    cell("D", base + 5, 12, "shared"),
                ]
            )
            + "</row>"
        )
        rows.append(
            f'<row r="{base + 6}">'
            + "".join(
                [
                    cell("A", base + 6, len(_SHARED), "shared"),
                    cell("B", base + 6, "DE"),
                    cell("C", base + 6, 1800),
                    cell("D", base + 6, 13, "shared"),
                ]
            )
            + "</row>"
        )
        # Sparse row: C cell is not physically present in the XML.
        rows.append(
            f'<row r="{base + 7}">'
            + "".join(
                [
                    cell("A", base + 7, "ABC Empty"),
                    cell("B", base + 7, "DE"),
                    cell("D", base + 7, 6, "shared"),
                ]
            )
            + "</row>"
        )
        rows.append(
            f'<row r="{base + 8}">'
            + "".join(
                [
                    cell("A", base + 8, "ABC Bool"),
                    cell("B", base + 8, "DE"),
                    cell("C", base + 8, True),
                    cell("D", base + 8, 6, "shared"),
                ]
            )
            + "</row>"
        )
        if malformed:
            rows.append(f'<row r="{base + 9}">' + cell("B", base + 9, 99_999, "shared") + "</row>")
        z.writestr(
            "xl/worksheets/data42.xml",
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
            + "".join(rows)
            + "</sheetData></worksheet>",
        )


def indexed_workbook(
    path: Path,
    headers: tuple[str | int | None, ...] = ("Customer", "Country", "Revenue", "Revenue"),
    header_row: int = 1,
) -> None:
    make_workbook(path, header_row=header_row)
    before = (
        f'<row r="{header_row}">'
        + "".join(cell(chr(65 + i), header_row, i, "shared") for i in range(4))
        + "</row>"
    )
    after = (
        f'<row r="{header_row}">'
        + "".join(cell(chr(65 + i), header_row, label) for i, label in enumerate(headers))
        + "</row>"
    )
    rewrite(path, "xl/worksheets/data42.xml", before, after)


@dataclass(frozen=True, slots=True)
class Placement:
    header_row: int
    columns: tuple[str, str, str]
    base_amount: int
    shared: bool = False


def table_document(*tables: Placement) -> str:
    rows: list[str] = []
    for number in range(1, max(table.header_row for table in tables) + 6):
        cells: list[tuple[str, str]] = []
        for table in tables:
            if number == table.header_row:
                for index, (column, label) in enumerate(zip(table.columns, _LABELS, strict=True)):
                    value = (
                        cell(column, number, index, "shared")
                        if table.shared
                        else cell(column, number, label)
                    )
                    cells.append((column, value))
            offset = number - table.header_row - 2
            if 0 <= offset <= 3:
                code = ("IT", "MK", "HR", "OPS")[offset]
                status = "review" if offset == 1 else "approved"
                record: tuple[str | int, ...] = (code, table.base_amount + offset, status)
                for column, item in zip(table.columns, record, strict=True):
                    cells.append((column, cell(column, number, item)))
        if cells:
            cells.sort(key=lambda item: (len(item[0]), item[0]))
            rows.append(f'<row r="{number}">' + "".join(value for _, value in cells) + "</row>")
    return worksheet(*rows)


def table_layout(path: Path) -> None:
    write_book(
        path,
        Sheet("First", table_document(Placement(1, ("A", "B", "C"), 900))),
        Sheet(
            "Four",
            table_document(
                Placement(3, ("B", "D", "G"), 1000),
                Placement(3, ("H", "J", "M"), 2000),
                Placement(10, ("B", "D", "G"), 3000),
                Placement(11, ("J", "L", "O"), 4000, shared=True),
            ),
        ),
    )
    for original, label in zip(("Customer", "Country", "Revenue"), _LABELS, strict=True):
        rewrite(path, "xl/sharedStrings.xml", f"<t>{original}</t>", f"<t>{label}</t>")


def worksheet_rows(values: list[tuple[str | int | float | bool | None, ...]]) -> str:
    result = []
    for number, row in enumerate(values, start=1):
        cells = "".join(cell(chr(65 + index), number, value) for index, value in enumerate(row))
        result.append(f'<row r="{number}">{cells}</row>')
    return worksheet(*result)


def layout_workbook(path: Path) -> None:
    make_workbook(path)
    rows = [
        '<row r="1">' + cell("A", 1, "Synthetic title") + "</row>",
        '<row r="3">'
        + cell("C", 3, "Customer")
        + cell("D", 3, "Revenue")
        + cell("E", 3, "Revenue")
        + cell("G", 3, "Customer")
        + cell("H", 3, "Revenue")
        + "</row>",
        '<row r="4">'
        + cell("C", 4, "Name")
        + cell("D", 4, "Current")
        + cell("E", 4, "PreviousYear")
        + cell("G", 4, "Name")
        + cell("H", 4, "Current")
        + "</row>",
        '<row r="5">' + cell("C", 5, "Comment between header and data") + "</row>",
        '<row r="7">'
        + cell("C", 7, "ABC One")
        + cell("D", 7, 120)
        + cell("E", 7, 80)
        + cell("G", 7, "XYZ Other")
        + cell("H", 7, 999)
        + '<c r="M7" t="s"><v>999999</v></c></row>',
        '<row r="8">'
        + cell("C", 8, "ABC Comment")
        + cell("D", 8, 1000)
        + cell("E", 8, 1000)
        + cell("G", 8, "ABC Comment")
        + cell("H", 8, 1000)
        + "</row>",
        '<row r="9">'
        + cell("C", 9, "NO")
        + cell("D", 9, 50)
        + cell("E", 9, 40)
        + cell("G", 9, "ABC Right One")
        + cell("H", 9, 150)
        + "</row>",
        '<row r="10">'
        + cell("C", 10, "ABC Two")
        + cell("D", 10, 200)
        + cell("E", 10, 180)
        + cell("G", 10, "ABC Right Two")
        + cell("H", 10, 250)
        + "</row>",
        '<row r="11">'
        + cell("C", 11, "ABC Footer")
        + cell("D", 11, 999)
        + cell("E", 11, 999)
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


_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"


_FIRST = worksheet(
    '<row r="1">' + cell("A", 1, "Country") + cell("B", 1, "Value") + "</row>",
    '<row r="2">' + cell("A", 2, "DE") + cell("B", 2, 101) + "</row>",
    '<row r="3">' + cell("A", 3, "AT") + cell("B", 3, 1) + "</row>",
)


_SECOND = worksheet(
    '<row r="1">'
    + cell("A", 1, "Value")
    + cell("C", 1, "Country")
    + cell("D", 1, "Note")
    + "</row>",
    '<row r="2">' + cell("A", 2, 202) + cell("C", 2, "DE") + cell("D", 2, "second") + "</row>",
    '<row r="3">' + cell("A", 3, 203) + cell("C", 3, "DE") + cell("D", 3, "repeat") + "</row>",
)


_NUMERIC = worksheet('<row r="1">' + cell("A", 1, 99) + "</row>")


_UNRELATED = worksheet('<row r="1">' + cell("A", 1, "Other") + "</row>")


_HEADERS = ("Customer", "Country", "Revenue", "Status")


_SHARED = (
    *_HEADERS,
    "ABC Ltd",
    "DE",
    "Active",
    "XYZ Inc",
    "AT",
    "ABC Berlin",
    "ABC São Paulo",
    "ABC Hamburg",
    "Inactive",
    "Open",
)


_LABELS = ("Code\nID", "Amount\nEUR", "Owner\nStatus")
