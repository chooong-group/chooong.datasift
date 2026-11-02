"""Public contract checks using real synthetic files."""

from __future__ import annotations

from pathlib import Path

import pytest

from chooong.datasift import (
    iter_matching_batches,
)
from tests.fixtures.excel import make_workbook


def test_batches_are_bounded(xlsx: Path, mask: dict) -> None:
    batches = list(iter_matching_batches(xlsx, mask, batch_size=2))
    assert list(map(len, batches)) == [2, 1]
    assert batches[0][0]["Customer"] == "ABC Ltd"


def test_corrupt_cell_propagates_error_after_initial_batches(tmp_path: Path) -> None:
    xlsx = tmp_path / "bad.xlsx"
    make_workbook(xlsx, malformed=True)
    mask = {"sheet": "Data", "where": {"column": "Country", "op": "eq", "value": "DE"}}
    batches = iter_matching_batches(xlsx, mask, batch_size=1)
    with pytest.raises(RuntimeError, match="Shared string index"):
        list(batches)
