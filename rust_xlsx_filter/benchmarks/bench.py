"""Generate large XLSX without loading all rows, then benchmark Rust filtering.

Usage: python benchmarks/bench.py --rows 250000 --batch-size 1024
"""
from __future__ import annotations

import argparse
import json
import tempfile
import time
import zipfile
from pathlib import Path

from rust_xlsx_filter import iter_matching_batches


MASK = {
    "sheet": "Daten",
    "where": {"all": [
        {"column": "Land", "op": "eq", "value": "DE"},
        {"column": "Umsatz", "op": "gte", "value": 9000},
    ]},
}


def generate(path: Path, rows: int) -> None:
    # Bounded memory both for file generation and for reading.
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=3) as z:
        z.writestr("[Content_Types].xml", '''<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="xml" ContentType="application/xml"/>
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>''')
        z.writestr("_rels/.rels", '''<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId0" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>''')
        z.writestr("xl/workbook.xml", '''<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Daten" sheetId="1" r:id="rId1"/></sheets></workbook>''')
        z.writestr("xl/_rels/workbook.xml.rels", '''<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>''')
        with z.open("xl/worksheets/sheet1.xml", "w", force_zip64=True) as out:
            out.write(b'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1">'
                b'<c r="A1" t="inlineStr"><is><t>Kunde</t></is></c>'
                b'<c r="B1" t="inlineStr"><is><t>Land</t></is></c>'
                b'<c r="C1" t="inlineStr"><is><t>Umsatz</t></is></c>'
                b'</row>')
            for i in range(2, rows + 2):
                country = "DE" if i % 2 == 0 else "AT"
                amount = (i * 17) % 10000
                out.write(
                    f'<row r="{i}"><c r="A{i}" t="inlineStr"><is><t>Kunde {i}</t></is></c>'
                    f'<c r="B{i}" t="inlineStr"><is><t>{country}</t></is></c>'
                    f'<c r="C{i}"><v>{amount}</v></c></row>'.encode()
                )
            out.write(b'</sheetData></worksheet>')


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=int, default=250_000)
    parser.add_argument("--batch-size", type=int, default=1024)
    args = parser.parse_args()
    if not 1 <= args.rows <= 1_048_575:
        parser.error("--rows must be 1..1048575, since there is one header row")
    with tempfile.TemporaryDirectory(prefix="xlsx-bench-") as directory:
        path = Path(directory) / "bench.xlsx"
        generate(path, args.rows)
        start = time.perf_counter()
        matched = sum(len(batch) for batch in iter_matching_batches(path, MASK, batch_size=args.batch_size))
        elapsed = time.perf_counter() - start
        print(json.dumps({
            "rows_scanned": args.rows,
            "rows_matched": matched,
            "seconds": round(elapsed, 3),
            "rows_per_second": round(args.rows / max(elapsed, 1e-10)),
            "compressed_file_bytes": path.stat().st_size,
        }, indent=2))


if __name__ == "__main__":
    main()
