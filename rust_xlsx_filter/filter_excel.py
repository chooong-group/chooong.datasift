"""Kompatibilitätswrapper: altes extract_rows-API, neuer nativer Rust-Filter."""
from __future__ import annotations

import argparse
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from rust_xlsx_filter import iter_matching_rows


def extract_rows(xlsx_path: str | Path, config_path: str | Path) -> Iterator[dict[str, Any]]:
    """Read XLSX rows and execute JSON predicate 100% inside Rust."""
    return iter_matching_rows(xlsx_path, config_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="XLSX-Filter mit Rust-Engine")
    parser.add_argument("xlsx")
    parser.add_argument("filter")
    args = parser.parse_args()
    for matched in extract_rows(args.xlsx, args.filter):
        print(json.dumps(matched, ensure_ascii=False, allow_nan=False))
