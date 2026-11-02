"""Public contract checks using real synthetic files."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from chooong.datasift import (
    Money,
    RecordKind,
    RejectCode,
    iter_matching_batches,
    iter_matching_rows,
    scan_batches,
)
from tests.fixtures.masks import (
    pipeline_mask,
)
from tests.fixtures.results import partial_scan


@pytest.mark.parametrize("batch_size", [1, 2, 1024])
def test_defaults_conversion_rejects_projection_and_statistics(
    csv_file: Path, tmp_path: Path, batch_size: int
) -> None:
    path = csv_file
    with scan_batches(path, pipeline_mask(), batch_size=batch_size) as batches:
        records = [record for batch in batches for record in batch]
        stats = batches.statistics
    assert [r.kind for r in records] == [
        RecordKind.MATCHED,
        RecordKind.REJECTED,
        RecordKind.MATCHED,
    ]
    rejected = records[1]
    assert rejected.row == 3
    assert rejected.sheet == "csv"
    assert rejected.file == str(path)
    assert rejected.values == {"ID": None, "Amount": "bad", "Country": "AT"}
    assert {r.code for r in rejected.reasons} == {
        RejectCode.REQUIRED_MISSING,
        RejectCode.CONVERSION_FAILED,
    }
    assert stats is not None
    assert stats.complete
    assert (stats.matched, stats.rejected, stats.defaults) == (2, 1, 2)
    assert stats.tables[0].raw_headers == (("ID", 0), ("Amount", 1), ("Country", 2))
    assert stats.tables[0].type_rules["Amount"].currency == "EUR"
    assert (stats.tables[0].data_start_row, stats.tables[0].data_end_row) == (2, 4)
    rows = list(iter_matching_rows(path, pipeline_mask(), batch_size=batch_size))
    assert list(rows[0]) == ["Country", "Amount"]
    assert rows[0]["Amount"] == Money(Decimal("1234.56"), "EUR")
    assert rows[1]["Amount"] == Money(Decimal("0.00"), "EUR")


def test_multiple_files_sorted_and_failure_is_not_success(tmp_path: Path) -> None:
    a = tmp_path / "a.csv"
    b = tmp_path / "b.csv"
    a.write_text("A,B\na,1\n")
    b.write_text("A,B\nb,2\n")
    assert [r["A"] for r in iter_matching_rows([b, a], {"sheet": None})] == ["a", "b"]
    broken = tmp_path / "c.xlsx"
    broken.write_bytes(b"broken")
    with scan_batches(str(tmp_path / "*.*"), {"sheet": None, "file_errors": "continue"}) as batches:
        records = []
        with pytest.raises(RuntimeError, match="unvollständig"):
            records.extend(record for batch in batches for record in batch)
        assert len(records) == 2
        assert batches.statistics is not None
        assert not batches.statistics.complete
        assert batches.statistics.diagnostics[-1].code == "FILE_ERROR"


def test_missing_header_bound_schema_has_incomplete_statistics(tmp_path: Path) -> None:
    path = tmp_path / "missing.csv"
    path.write_text("title\n")
    mask = {"sheet": None, "source": {"header_start_row": 3, "data_start_row": 4}}
    records, statistics = partial_scan(path, mask, 1)
    assert records == []
    assert statistics.diagnostics[0].code == "SCHEMA_MISMATCH"
    with (
        iter_matching_batches(path, mask) as batches,
        pytest.raises(RuntimeError, match="SCHEMA_MISMATCH"),
    ):
        list(batches)
    assert batches.statistics is not None
    assert not batches.statistics.complete
