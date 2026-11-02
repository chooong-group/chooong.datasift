"""Public contract checks using real synthetic files."""

from __future__ import annotations

from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from chooong.datasift import (
    RecordKind,
    iter_matching_rows,
    scan_batches,
)
from tests.fixtures.excel import (
    Sheet,
    cell,
    rewrite,
    worksheet,
    write_book,
)


@pytest.mark.parametrize(
    ("date1904", "serial", "expected"),
    [
        (False, 59, "1900-02-28"),
        (False, 60, None),
        (False, 61, "1900-03-01"),
        (True, 0, "1904-01-01"),
    ],
)
def test_real_excel_date_systems_and_styles(tmp_path, date1904, serial, expected) -> None:
    from datetime import date

    path = tmp_path / "dates.xlsx"
    document = worksheet(
        '<row r="1">' + cell("A", 1, "Date") + cell("B", 1, "ID") + "</row>",
        f'<row r="2"><c r="A2" s="0"><v>{serial}</v></c>' + cell("B", 2, "x") + "</row>",
    )
    write_book(path, Sheet("Data", document))
    if date1904:
        rewrite(path, "xl/workbook.xml", "<sheets>", '<workbookPr date1904="1"/><sheets>')
    with ZipFile(path) as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}
    parts["xl/styles.xml"] = b'<styleSheet><cellXfs><xf numFmtId="14"/></cellXfs></styleSheet>'
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
        for name, content in parts.items():
            archive.writestr(name, content)
    mask = {"sheet": None, "types": {"Date": {"type": "date"}}}
    with scan_batches(path, mask) as batches:
        records = [r for batch in batches for r in batch]
    if expected is None:
        assert records[0].kind == RecordKind.REJECTED
    else:
        assert records[0].kind == RecordKind.MATCHED
        assert next(iter_matching_rows(path, mask))["Date"] == date.fromisoformat(expected)
    # Explicitly unconfigured scalar output is compatible.
    assert next(iter_matching_rows(path, {"sheet": None}))["Date"] == serial


def test_temporal_text_formats_and_nanoseconds(tmp_path) -> None:
    from datetime import date

    from chooong.datasift import PreciseDateTime

    path = tmp_path / "time.csv"
    path.write_text("Date,Time\n01.11.2026,2026-11-01T12:00:00.123456789\n")
    mask = {
        "sheet": None,
        "types": {
            "Date": {"type": "date", "convert": True, "format": "%d.%m.%Y"},
            "Time": {"type": "datetime", "convert": True},
        },
    }
    row = next(iter_matching_rows(path, mask))
    assert row["Date"] == date(2026, 11, 1)
    assert row["Time"] == PreciseDateTime("2026-11-01T12:00:00.123456789")


def test_timezone_offsets_are_preserved_and_comparisons_use_instants(tmp_path) -> None:
    from datetime import datetime

    path = tmp_path / "timezone.csv"
    path.write_text("Date,Other\n2026-11-01T13:00:00+01:00,x\n")
    mask = {
        "sheet": None,
        "types": {"Date": {"type": "datetime", "convert": True}},
        "where": {
            "column": "Date",
            "op": "eq",
            "value": {"type": "datetime", "value": "2026-11-01T12:00:00Z"},
        },
    }
    row = next(iter_matching_rows(path, mask))
    assert row["Date"] == datetime.fromisoformat("2026-11-01T13:00:00+01:00")
    assert row["Date"].isoformat() == "2026-11-01T13:00:00+01:00"
