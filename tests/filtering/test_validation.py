"""Public contract checks using real synthetic files."""

from __future__ import annotations

from pathlib import Path

import pytest

from chooong.datasift import (
    FilterMask,
    Operator,
    RecordKind,
    RejectCode,
    ScalarCondition,
    iter_matching_batches,
    iter_matching_rows,
    scan_batches,
)
from tests.fixtures.excel import Sheet, cell, make_workbook, rewrite, worksheet, write_book


def test_unindexed_duplicate_name_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "headers.xlsx"
    make_workbook(path)
    rewrite(path, "xl/sharedStrings.xml", "<t>Status</t>", "<t>Umsatz</t>")
    mask = FilterMask(
        sheet="Daten", where=ScalarCondition(column="Umsatz", op=Operator.EQ, value=5000)
    )
    with pytest.raises(ValueError, match="Unbekannte Spalte"):
        iter_matching_batches(path, mask)


def test_zero_false_defaults_and_schema_rejections(tmp_path: Path) -> None:
    path = tmp_path / "data.xlsx"
    write_book(
        path,
        Sheet(
            "Data",
            worksheet(
                '<row r="1">' + cell("A", 1, "A") + cell("B", 1, "B") + "</row>",
                '<row r="2">' + cell("A", 2, 0) + cell("B", 2, False) + "</row>",
            ),
        ),
    )
    mask = {"sheet": None, "required": ["A", "B"], "defaults": {"A": 9, "B": True}}
    assert [dict(r) for r in iter_matching_rows(path, mask)] == [{"A": 0, "B": False}]
    mask["required"] = ["Missing"]
    with scan_batches(path, mask) as batches:
        records = []
        with pytest.raises(RuntimeError, match="SCHEMA_MISMATCH"):
            records.extend(r for batch in batches for r in batch)
        stats = batches.statistics
    assert records[0].reasons[0].code == RejectCode.SCHEMA_MISMATCH
    assert stats is not None
    assert stats.diagnostics[0].code == "SCHEMA_MISMATCH"


def test_strict_schema_policy_rejects_other_tables(tmp_path) -> None:
    a = tmp_path / "a.csv"
    b = tmp_path / "b.csv"
    a.write_text("A,B\n1,2\n")
    b.write_text("A,C\n3,4\n")
    with scan_batches([a, b], {"sheet": None, "schema_policy": "strict"}) as batches:
        records = []
        with pytest.raises(RuntimeError, match="SCHEMA_MISMATCH"):
            records.extend(r for batch in batches for r in batch)
        assert batches.statistics is not None
        assert not batches.statistics.complete
    assert [r.kind for r in records] == [RecordKind.MATCHED, RecordKind.REJECTED]
    assert records[1].reasons[0].code == RejectCode.SCHEMA_MISMATCH
