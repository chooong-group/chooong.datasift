"""Deterministic streaming fixture generation, outside measured child processes."""

import csv
import random
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from tests.benchmarks.models import Case, Filter, Format

MAX_DATA_ROWS = 1_048_575
HEADERS = ("ID", "Amount", "Country", "Flag", "Date")


@dataclass(frozen=True, slots=True)
class GeneratedRow:
    identifier: str
    amount: str
    country: str
    flag: str
    date: str

    def cells(self) -> tuple[str, str, str, str, str]:
        return self.identifier, self.amount, self.country, self.flag, self.date


def records(case: Case) -> Iterator[GeneratedRow]:
    randomizer = random.Random(case.seed)
    for index in range(case.rows):
        identifier = f"row-{index}"
        amount = f"{randomizer.randrange(1, 10000)}.50"
        if case.filter == Filter.VALIDATION:
            if index % 20 == 0:
                amount = ""
            elif index % 20 == 18:
                amount = "invalid"
            elif index % 20 == 19:
                identifier = ""
        country = "DE" if index % 100 < case.hit_percent else "AT"
        yield GeneratedRow(identifier, amount, country, "true", "2026-01-01")


def _cell(column: str, row: int, value: str) -> str:
    # All generated labels and scalar strings are deliberately ASCII XML-safe.
    return f'<c r="{column}{row}" t="inlineStr"><is><t>{value}</t></is></c>'


def _entry(name: str) -> ZipInfo:
    entry = ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
    entry.compress_type = ZIP_DEFLATED
    return entry


def _excel(path: Path, case: Case) -> None:
    sheet_count = (case.rows + MAX_DATA_ROWS - 1) // MAX_DATA_ROWS
    source = records(case)
    with ZipFile(path, "x", compression=ZIP_DEFLATED) as archive:
        content_type = (
            "application/vnd.ms-excel.sheet.macroEnabled.main+xml"
            if case.format == Format.XLSM
            else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"
        )
        archive.writestr(
            _entry("[Content_Types].xml"),
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" '
            'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            f'<Override PartName="/xl/workbook.xml" ContentType="{content_type}"/>'
            + "".join(
                f'<Override PartName="/xl/worksheets/sheet{i}.xml" '
                'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                for i in range(sheet_count)
            )
            + "</Types>",
        )
        archive.writestr(
            _entry("_rels/.rels"),
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="workbook" '
            'Type="http://schemas.openxmlformats.org/officeDocument/'
            '2006/relationships/officeDocument" '
            'Target="xl/workbook.xml"/>'
            "</Relationships>",
        )
        archive.writestr(
            _entry("xl/workbook.xml"),
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
            + "".join(
                f'<sheet name="Data{i}" sheetId="{i + 1}" r:id="r{i}"/>' for i in range(sheet_count)
            )
            + "</sheets></workbook>",
        )
        archive.writestr(
            _entry("xl/_rels/workbook.xml.rels"),
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            + "".join(
                f'<Relationship Id="r{i}" '
                'Type="http://schemas.openxmlformats.org/officeDocument/'
                '2006/relationships/worksheet" '
                f'Target="worksheets/sheet{i}.xml"/>'
                for i in range(sheet_count)
            )
            + "</Relationships>",
        )
        for sheet in range(sheet_count):
            with archive.open(
                _entry(f"xl/worksheets/sheet{sheet}.xml"), "w", force_zip64=True
            ) as output:
                output.write(
                    b'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
                )
                output.write(
                    (
                        '<row r="1">'
                        + "".join(_cell(chr(65 + i), 1, h) for i, h in enumerate(HEADERS))
                        + "</row>"
                    ).encode()
                )
                count = min(MAX_DATA_ROWS, case.rows - sheet * MAX_DATA_ROWS)
                for row in range(2, count + 2):
                    values = next(source).cells()
                    output.write(
                        (
                            f'<row r="{row}">'
                            + "".join(
                                _cell(chr(65 + i), row, value) for i, value in enumerate(values)
                            )
                            + "</row>"
                        ).encode()
                    )
                output.write(b"</sheetData></worksheet>")


def generate(path: Path, case: Case) -> None:
    if case.format == Format.CSV:
        with path.open("x", encoding="utf-8", newline="") as output:
            writer = csv.writer(output, lineterminator="\n")
            writer.writerow(HEADERS)
            writer.writerows(row.cells() for row in records(case))
    else:
        _excel(path, case)
