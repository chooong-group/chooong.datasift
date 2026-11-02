"""Public contract checks using real synthetic files."""

from __future__ import annotations

from pathlib import Path

from chooong.datasift import (
    iter_matching_batches,
    iter_matching_rows,
    scan_batches,
)


def test_explicit_row_classes_and_default_order(tmp_path) -> None:
    path = tmp_path / "rows.csv"
    path.write_text("Name,Value\ncomment,x\na,1\nTOTAL:,2\nseparator,-\n")
    mask = {
        "sheet": None,
        "header": {"anchors": ["Name", "Value"]},
        "row_policy": {
            "rules": [
                {"classification": "comment", "rows": [2]},
                {
                    "classification": "total",
                    "where": {"column": "Name", "op": "eq", "value": "TOTAL:"},
                },
                {"classification": "separator", "rows": [5]},
            ]
        },
    }
    with iter_matching_batches(path, mask) as batches:
        assert [dict(r) for batch in batches for r in batch] == [{"Name": "a", "Value": "1"}]
        assert batches.statistics is not None
        assert batches.statistics.row_classes["total"] == 1
    mask["row_policy"]["include"] = ["data", "total"]
    assert len(list(iter_matching_rows(path, mask))) == 2


def test_explicit_classification_rules_cover_all_classes_and_precedence(tmp_path: Path) -> None:
    path = tmp_path / "classes.csv"
    path.write_text("Name,Value\ncomment,1\ntotal,2\nseparator,3\n,\ndata,4\n")
    source = {
        "columns": [{"name": "Name", "column": "A"}, {"name": "Value", "column": "B"}],
        "data_start_row": 2,
    }
    mask = {
        "sheet": None,
        "source": source,
        "row_policy": {
            "include": ["data", "total", "empty"],
            "exclude": ["empty"],
            "rules": [
                {"classification": "comment", "rows": [2]},
                {"classification": "data", "rows": [2]},
                {
                    "classification": "total",
                    "where": {"column": "Name", "op": "eq", "value": "total"},
                },
                {"classification": "separator", "rows": [4]},
                {"classification": "empty", "rows": [5]},
            ],
        },
    }
    with scan_batches(path, mask) as batches:
        records = [r for batch in batches for r in batch]
        stats = batches.statistics
    assert [r.values["Name"] for r in records] == ["total", "data"]
    assert stats is not None
    assert {str(k): v for k, v in stats.row_classes.items()} == {
        "data": 1,
        "empty": 1,
        "comment": 1,
        "total": 1,
        "separator": 1,
    }
