"""Generate large XLSX without loading all rows, then benchmark Rust filtering.

Usage: python scripts/bench.py --rows 2000000 --batch-size 1024
"""

from __future__ import annotations

import argparse
import json
import resource
import sys
import tempfile
import time
import zipfile
from pathlib import Path

from chooong.datasift import iter_matching_batches

MAX_DATA_ROWS = 1_048_575


def write_sheet(archive: zipfile.ZipFile, index: int, start: int, rows: int) -> None:
    with archive.open(f"xl/worksheets/sheet{index}.xml", "w", force_zip64=True) as out:
        out.write(
            b'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1">'
            b'<c r="A1" t="inlineStr"><is><t>Kunde</t></is></c>'
            b'<c r="B1" t="inlineStr"><is><t>Land</t></is></c>'
            b'<c r="C1" t="inlineStr"><is><t>Umsatz</t></is></c></row>'
        )
        for offset in range(rows):
            row = offset + 2
            identity = start + offset + 2
            country = "DE" if identity % 2 == 0 else "AT"
            amount = (identity * 17) % 10000
            out.write(
                f'<row r="{row}"><c r="A{row}" t="inlineStr"><is><t>Kunde {identity}</t></is></c>'
                f'<c r="B{row}" t="inlineStr"><is><t>{country}</t></is></c>'
                f'<c r="C{row}"><v>{amount}</v></c></row>'.encode()
            )
        out.write(b"</sheetData></worksheet>")


def generate(path: Path, rows: int) -> None:
    if rows < 1:
        raise ValueError("rows must be positive")
    sheets = (rows + MAX_DATA_ROWS - 1) // MAX_DATA_ROWS
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=3) as archive:
        overrides = "".join(
            f'<Override PartName="/xl/worksheets/sheet{index}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            for index in range(1, sheets + 1)
        )
        archive.writestr(
            "[Content_Types].xml",
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            + overrides
            + "</Types>",
        )
        archive.writestr(
            "_rels/.rels",
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId0" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>',
        )
        entries = "".join(
            f'<sheet name="Daten{index}" sheetId="{index}" r:id="rId{index}"/>'
            for index in range(1, sheets + 1)
        )
        archive.writestr(
            "xl/workbook.xml",
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
            + entries
            + "</sheets></workbook>",
        )
        relationships = "".join(
            f'<Relationship Id="rId{index}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{index}.xml"/>'
            for index in range(1, sheets + 1)
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            + relationships
            + "</Relationships>",
        )
        for index in range(1, sheets + 1):
            start = (index - 1) * MAX_DATA_ROWS
            write_sheet(archive, index, start, min(rows - start, MAX_DATA_ROWS))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=int, default=2_000_000)
    parser.add_argument("--batch-size", type=int, default=1024)
    parser.add_argument("--min-amount", type=int, default=9000)
    args = parser.parse_args()
    if args.rows < 1:
        parser.error("--rows must be positive")
    if args.batch_size < 1:
        parser.error("--batch-size must be positive")
    with tempfile.TemporaryDirectory(prefix="xlsx-bench-") as directory:
        path = Path(directory) / "bench.xlsx"
        generate(path, args.rows)
        mask = {
            "sheet": None,
            "where": {
                "all": [
                    {"column": "Land", "op": "eq", "value": "DE"},
                    {"column": "Umsatz", "op": "gte", "value": args.min_amount},
                ]
            },
        }
        start = time.perf_counter()
        matched = sum(
            len(batch) for batch in iter_matching_batches(path, mask, batch_size=args.batch_size)
        )
        elapsed = time.perf_counter() - start
        print(
            json.dumps(
                {
                    "rows_scanned": args.rows,
                    "rows_matched": matched,
                    "seconds": round(elapsed, 3),
                    "rows_per_second": round(args.rows / max(elapsed, 1e-10)),
                    "compressed_file_bytes": path.stat().st_size,
                    "peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
                    * (1 if sys.platform == "darwin" else 1024),
                    "batch_size": args.batch_size,
                    "min_amount": args.min_amount,
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
