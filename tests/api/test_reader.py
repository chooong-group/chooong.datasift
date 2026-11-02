"""Public contract checks using real synthetic files."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from chooong.datasift import (
    iter_matching_batches,
    iter_matching_rows,
)


def test_mask_filename_or_json_text(xlsx: Path, mask: dict, tmp_path: Path) -> None:
    path = tmp_path / "mask.json"
    path.write_text(json.dumps(mask), encoding="utf-8")
    assert len(list(iter_matching_rows(xlsx, path))) == 3
    assert len(list(iter_matching_rows(xlsx, path.as_posix()))) == 3
    assert len(list(iter_matching_rows(xlsx, json.dumps(mask)))) == 3


def test_missing_sheet_error_is_eager(xlsx: Path) -> None:
    with pytest.raises(ValueError, match="Arbeitsblatt"):
        iter_matching_batches(
            xlsx, {"sheet": "Unbekannt", "where": {"column": "Kunde", "op": "eq", "value": "a"}}
        )
