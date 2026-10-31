"""Integration tests use actual XLSX ZIP/XML files without openpyxl or Excel."""
from __future__ import annotations

import json
from pathlib import Path
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from rust_xlsx_filter import iter_matching_batches, iter_matching_rows


_HEADERS = ["Kunde", "Land", "Umsatz", "Status"]
_SHARED = [*_HEADERS, "ABC GmbH", "DE", "Aktiv", "XYZ AG", "AT", "ABC Berlin", "ABC München", "ABC Hamburg", "Inaktiv", "Offen"]


def _cell(col: str, row: int, value: str | int | float | bool | None, kind: str = "auto") -> str:
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
        z.writestr("[Content_Types].xml", '''<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/worksheets/data42.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
<Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>
</Types>''')
        z.writestr("_rels/.rels", '''<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>''')
        z.writestr("xl/workbook.xml", '''<?xml version="1.0" encoding="UTF-8"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<sheets><sheet name="Meta" sheetId="1" r:id="rId9"/><sheet name="Daten" sheetId="2" r:id="rId42"/></sheets>
</workbook>''')
        z.writestr("xl/_rels/workbook.xml.rels", '''<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId9" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/meta.xml"/>
<Relationship Id="rId42" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/data42.xml"/>
<Relationship Id="rId55" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings" Target="sharedStrings.xml"/>
</Relationships>''')
        z.writestr("xl/worksheets/meta.xml", '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"/>')
        z.writestr("xl/sharedStrings.xml", '''<?xml version="1.0" encoding="UTF-8"?>
<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'''
            + "".join(f"<si><t>{escape(value)}</t></si>" for value in _SHARED)
            + '<si><r><t>ABC &amp; </t></r><r><t>Söhne</t></r><rPh sb="0" eb="1"><t>IGNORED</t></rPh></si>'
            + "</sst>")
        base = header_row
        rows = []
        rows.append(f'<row r="{base}">' + "".join(
            _cell(chr(65 + i), base, i, "shared") for i in range(4)
        ) + "</row>")
        rows.append(f'<row r="{base + 1}">' + "".join([
            _cell("A", base + 1, 4, "shared"),
            _cell("B", base + 1, 5, "shared"),
            _cell("C", base + 1, 5000),
            _cell("D", base + 1, 6, "shared"),
        ]) + "</row>")
        rows.append(f'<row r="{base + 2}">' + "".join([
            _cell("A", base + 2, 7, "shared"), _cell("B", base + 2, 8, "shared"),
            _cell("C", base + 2, 8000), _cell("D", base + 2, 6, "shared"),
        ]) + "</row>")
        rows.append(f'<row r="{base + 3}">' + "".join([
            _cell("A", base + 3, 9, "shared"), _cell("B", base + 3, 5, "shared"),
            _cell("C", base + 3, 750), _cell("D", base + 3, 6, "shared"),
        ]) + "</row>")
        rows.append(f'<row r="{base + 4}">' + "".join([
            _cell("A", base + 4, 10, "shared"), _cell("B", base + 4, 5, "shared"),
            _cell("C", base + 4, 3200, "formula"), _cell("D", base + 4, 6, "shared"),
        ]) + "</row>")
        rows.append(f'<row r="{base + 5}">' + "".join([
            _cell("A", base + 5, 11, "shared"), _cell("B", base + 5, 5, "shared"),
            _cell("C", base + 5, 2500), _cell("D", base + 5, 12, "shared"),
        ]) + "</row>")
        rows.append(f'<row r="{base + 6}">' + "".join([
            _cell("A", base + 6, len(_SHARED), "shared"),
            _cell("B", base + 6, "DE"), _cell("C", base + 6, 1800),
            _cell("D", base + 6, 13, "shared"),
        ]) + "</row>")
        # Sparse row: C cell is not physically present in the XML.
        rows.append(f'<row r="{base + 7}">' + "".join([
            _cell("A", base + 7, "ABC Leer"), _cell("B", base + 7, "DE"),
            _cell("D", base + 7, 6, "shared"),
        ]) + "</row>")
        rows.append(f'<row r="{base + 8}">' + "".join([
            _cell("A", base + 8, "ABC Bool"), _cell("B", base + 8, "DE"),
            _cell("C", base + 8, True), _cell("D", base + 8, 6, "shared"),
        ]) + "</row>")
        if malformed:
            rows.append(f'<row r="{base + 9}">' + _cell("A", base + 9, 99_999, "shared") + "</row>")
        z.writestr("xl/worksheets/data42.xml", '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
                   + "".join(rows) + "</sheetData></worksheet>")


@pytest.fixture
def xlsx(tmp_path: Path) -> Path:
    file = tmp_path / "sample.xlsx"
    make_workbook(file)
    return file


@pytest.fixture
def mask() -> dict:
    return {
        "sheet": "Daten",
        "where": {"all": [
            {"column": "Kunde", "op": "starts_with", "value": "ABC"},
            {"column": "Land", "op": "eq", "value": "DE"},
            {"column": "Umsatz", "op": "gte", "value": 1000},
            {"any": [
                {"column": "Status", "op": "eq", "value": "Aktiv"},
                {"column": "Status", "op": "eq", "value": "Offen"},
            ]},
        ]},
    }


def test_streamed_filter_with_nested_json(xlsx: Path, mask: dict) -> None:
    actual = list(iter_matching_rows(xlsx, mask, batch_size=1))
    assert [row["Kunde"] for row in actual] == ["ABC GmbH", "ABC München", "ABC & Söhne"]
    assert [row["Umsatz"] for row in actual] == [5000, 3200, 1800]
    assert all(row["Land"] == "DE" for row in actual)


def test_batches_are_bounded(xlsx: Path, mask: dict) -> None:
    batches = list(iter_matching_batches(xlsx, mask, batch_size=2))
    assert list(map(len, batches)) == [2, 1]
    assert batches[0][0]["Kunde"] == "ABC GmbH"


def test_mask_filename_or_json_text(xlsx: Path, mask: dict, tmp_path: Path) -> None:
    path = tmp_path / "mask.json"
    path.write_text(json.dumps(mask), encoding="utf-8")
    assert len(list(iter_matching_rows(xlsx, path))) == 3
    assert len(list(iter_matching_rows(xlsx, path.as_posix()))) == 3
    assert len(list(iter_matching_rows(xlsx, json.dumps(mask)))) == 3


def test_regex_and_not_and_bool_types(xlsx: Path) -> None:
    mask = {"sheet": "Daten", "where": {"all": [
        {"column": "Kunde", "op": "regex", "value": "(?i)^abc.*"},
        {"not": {"column": "Status", "op": "eq", "value": "Inaktiv"}},
        {"column": "Umsatz", "op": "lt", "value": 2000},
    ]}}
    assert [r["Kunde"] for r in iter_matching_rows(xlsx, mask)] == ["ABC Berlin", "ABC & Söhne"]


def test_in_and_missing_value(xlsx: Path) -> None:
    mask = {"sheet": "Daten", "where": {"all": [
        {"column": "Status", "op": "in", "value": ["Offen", "Inaktiv"]},
        {"column": "Kunde", "op": "not_empty"},
    ]}}
    assert len(list(iter_matching_rows(xlsx, mask))) == 2


@pytest.mark.parametrize("condition", [
    {"column": "UNKNOWN", "op": "eq", "value": "hello"},
    {"column": "Umsatz", "op": "gte", "value": "1000"},
    {"column": "Kunde", "op": "regex", "value": "("},
    {"any": []},
    {"column": "Kunde", "op": "contains", "value": "ABC", "evil": "bad"},
])
def test_mask_errors_are_eager(xlsx: Path, condition: dict) -> None:
    with pytest.raises(ValueError):
        iter_matching_batches(xlsx, {"sheet": "Daten", "where": condition})


def test_missing_sheet_error_is_eager(xlsx: Path) -> None:
    with pytest.raises(ValueError, match="Arbeitsblatt"):
        iter_matching_batches(xlsx, {"sheet": "Unbekannt", "where": {"column":"Kunde", "op":"eq", "value":"a"}})


def test_header_row_offset(tmp_path: Path) -> None:
    xlsx = tmp_path / "header-row-two.xlsx"
    make_workbook(xlsx, header_row=2)
    mask = {"sheet": "Daten", "header_row": 2,
            "where": {"column":"Status", "op":"eq", "value":"Aktiv"}}
    assert len(list(iter_matching_rows(xlsx, mask))) == 6


def test_corrupt_cell_propagates_error_after_initial_batches(tmp_path: Path) -> None:
    xlsx = tmp_path / "bad.xlsx"
    make_workbook(xlsx, malformed=True)
    mask = {"sheet": "Daten", "where": {"column": "Land", "op": "eq", "value": "DE"}}
    batches = iter_matching_batches(xlsx, mask, batch_size=1)
    with pytest.raises(RuntimeError, match="Shared-String-Index"):
        list(batches)


def test_close_stops_worker(xlsx: Path) -> None:
    mask = {"sheet": "Daten", "where": {"column": "Land", "op": "eq", "value": "DE"}}
    batches = iter_matching_batches(xlsx, mask)
    batches.close()
    assert list(batches) == []


def test_sparse_empty_and_null_comparisons(xlsx: Path) -> None:
    mask = {"sheet": "Daten", "where": {"all": [
        {"column": "Kunde", "op": "eq", "value": "ABC Leer"},
        {"column": "Umsatz", "op": "is_empty"},
    ]}}
    assert list(iter_matching_rows(xlsx, mask)) == [
        {"Kunde": "ABC Leer", "Land": "DE", "Umsatz": None, "Status": "Aktiv"}
    ]
    mask["where"]["all"][1] = {"column": "Umsatz", "op": "eq", "value": None}
    assert len(list(iter_matching_rows(xlsx, mask))) == 1


def test_boolean_not_treated_as_numeric(xlsx: Path) -> None:
    mask = {"sheet": "Daten", "where": {"all": [
        {"column": "Kunde", "op": "eq", "value": "ABC Bool"},
        {"column": "Umsatz", "op": "gte", "value": 1},
    ]}}
    assert list(iter_matching_rows(xlsx, mask)) == []
    mask["where"]["all"][1] = {"column": "Umsatz", "op": "eq", "value": True}
    assert len(list(iter_matching_rows(xlsx, mask))) == 1


def test_cli_output_is_atomic_on_success_and_error(
    xlsx: Path, mask: dict, tmp_path: Path,
) -> None:
    import subprocess
    import sys

    mask_file = tmp_path / "mask.json"
    mask_file.write_text(json.dumps(mask), encoding="utf-8")
    destination = tmp_path / "result.ndjson"
    completed = subprocess.run(
        [sys.executable, "-m", "rust_xlsx_filter", str(xlsx), str(mask_file),
         "--output", str(destination), "--batch-size", "1"],
        capture_output=True, text=True, check=False,
    )
    assert completed.returncode == 0, completed.stderr
    actual = [json.loads(line) for line in destination.read_text(encoding="utf-8").splitlines()]
    assert len(actual) == 3

    original_content = destination.read_bytes()
    broken = tmp_path / "corrupt.xlsx"
    make_workbook(broken, malformed=True)
    completed = subprocess.run(
        [sys.executable, "-m", "rust_xlsx_filter", str(broken), str(mask_file),
         "--output", str(destination), "--batch-size", "1"],
        capture_output=True, text=True, check=False,
    )
    assert completed.returncode != 0
    assert destination.read_bytes() == original_content
    assert not list(tmp_path.glob(".result.ndjson.*.tmp"))


def test_cli_cannot_overwrite_input(xlsx: Path, mask: dict, tmp_path: Path) -> None:
    import subprocess
    import sys

    mask_file = tmp_path / "mask.json"
    mask_file.write_text(json.dumps(mask), encoding="utf-8")
    original_bytes = xlsx.read_bytes()
    result = subprocess.run(
        [sys.executable, "-m", "rust_xlsx_filter", str(xlsx), str(mask_file),
         "--output", str(xlsx)],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode != 0
    assert xlsx.read_bytes() == original_bytes
