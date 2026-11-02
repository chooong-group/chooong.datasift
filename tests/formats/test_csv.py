"""Public contract checks using real synthetic files."""

from __future__ import annotations

from pathlib import Path

import pytest

from chooong.datasift import (
    iter_matching_rows,
)


def test_encoding_bom_quotes_newlines_and_invalid_encoding(tmp_path: Path) -> None:
    path = tmp_path / "utf16.csv"
    path.write_bytes('A;B\n"Café\nNorth";"a; b"\n'.encode("utf-16"))
    mask = {
        "sheet": None,
        "header": {"anchors": ["A", "B"]},
        "csv": {"encoding": "utf-16le", "delimiter": ";"},
    }
    rows = list(iter_matching_rows(path, mask))
    assert dict(rows[0]) == {"A": "Café\nNorth", "B": "a; b"}
    path.write_bytes(b"A,B\n\xff,1\n")
    with pytest.raises((ValueError, RuntimeError)):
        list(iter_matching_rows(path, {"sheet": None}))
