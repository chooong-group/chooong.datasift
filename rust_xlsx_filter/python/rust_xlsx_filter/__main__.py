"""CLI: python -m rust_xlsx_filter input.xlsx filter.json --output matches.ndjson"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import TextIO

from . import iter_matching_batches


def _write_matches(stream: TextIO, batches: object) -> None:
    for batch in batches:
        for row in batch:
            stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False, separators=(",", ":")))
            stream.write("\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Rust XLSX-Filter mit JSON-Maske")
    parser.add_argument("xlsx", help="Excel-Datei .xlsx / .xlsm")
    parser.add_argument("mask", help="JSON-Filterdatei")
    parser.add_argument("--batch-size", type=int, default=1024)
    parser.add_argument("--output", type=Path, help="NDJSON-Ausgabe, atomar erst nach erfolgreichem Scan")
    args = parser.parse_args()
    if args.output is not None and args.output.resolve() == Path(args.xlsx).resolve():
        parser.error("--output darf die XLSX-Eingabedatei nicht überschreiben")

    try:
        batches = iter_matching_batches(args.xlsx, Path(args.mask), batch_size=args.batch_size)
        try:
            if args.output is None:
                _write_matches(sys.stdout, batches)
            else:
                # No partial result file is left behind if the reader fails late.
                temp_path = None
                try:
                    with tempfile.NamedTemporaryFile(
                        "w", encoding="utf-8", newline="\n",
                        dir=args.output.parent, prefix=f".{args.output.name}.",
                        suffix=".tmp", delete=False,
                    ) as output:
                        temp_path = Path(output.name)
                        _write_matches(output, batches)
                    os.replace(temp_path, args.output)
                    temp_path = None
                finally:
                    if temp_path is not None:
                        temp_path.unlink(missing_ok=True)
        finally:
            batches.close()
    except (ValueError, RuntimeError, OSError) as error:
        print(f"Filterfehler: {error}", file=sys.stderr)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
