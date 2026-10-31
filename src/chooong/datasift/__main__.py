"""NDJSON command line adapter and composition root."""

import argparse
import json
import os
import sys
import tempfile
from collections.abc import Iterable
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from chooong.datasift import Row, iter_matching_batches


class _Arguments(BaseModel):
    model_config = ConfigDict(extra="forbid")
    xlsx: Path
    mask: Path
    batch_size: int
    output: Path | None


class _TextWriter(Protocol):
    def write(self, text: str, /) -> int: ...


def _write_matches(stream: _TextWriter, batches: Iterable[list[Row]]) -> None:
    for batch in batches:
        for row in batch:
            stream.write(
                json.dumps(dict(row), ensure_ascii=False, allow_nan=False, separators=(",", ":"))
            )
            stream.write("\n")


def _write_atomic(destination: Path, batches: Iterable[list[Row]]) -> None:
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            newline="\n",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as output:
            temp_path = Path(output.name)
            _write_matches(output, batches)
            output.flush()
            os.fsync(output.fileno())
        temp_path.replace(destination)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="XLSX/XLSM mit nativen Rust-Prädikaten filtern")
    parser.add_argument("xlsx", help="Excel-Eingabedatei")
    parser.add_argument("mask", help="JSON-Filterdatei")
    parser.add_argument("--batch-size", type=int, default=1024)
    parser.add_argument("--output", type=Path, help="Atomare NDJSON-Ausgabedatei")
    args = _Arguments.model_validate(vars(parser.parse_args()))
    if args.output is not None and args.output.resolve() in {
        args.xlsx.resolve(),
        args.mask.resolve(),
    }:
        parser.error("--output darf weder Excel-Eingabe noch Filterdatei überschreiben")
    try:
        with iter_matching_batches(args.xlsx, args.mask, batch_size=args.batch_size) as batches:
            if args.output is None:
                _write_matches(sys.stdout, batches)
            else:
                _write_atomic(args.output, batches)
    except (ValueError, RuntimeError, OSError) as error:
        # Validation/reader messages can contain workbook values: keep stderr data-free.
        sys.stderr.write(f"Filterfehler ({type(error).__name__}); Ausgabe unvollständig.\n")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
