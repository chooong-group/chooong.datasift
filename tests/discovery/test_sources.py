"""Public contract checks using real synthetic files."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from chooong.datasift import (
    AllOf,
    ColumnBinding,
    EmptyCondition,
    FilterMask,
    Operator,
    RecordKind,
    ScalarCondition,
    TableSource,
    TextCondition,
    iter_matching_batches,
    iter_matching_rows,
    scan_batches,
)
from tests.fixtures.excel import _FIRST, _SECOND, Sheet, layout_workbook, write_book
from tests.fixtures.masks import source_mask
from tests.fixtures.results import partial_scan


def test_source_scope_applies_to_every_sheet(tmp_path: Path) -> None:
    path = tmp_path / "source.xlsx"
    write_book(path, Sheet("First", _FIRST), Sheet("Second", _SECOND))
    mask = FilterMask(
        sheet=None,
        source=TableSource(
            columns=(
                ColumnBinding(name="Country", column="C"),
                ColumnBinding(name="Amount", column="A"),
            ),
            data_start_row=2,
            data_end_row=2,
        ),
        where=ScalarCondition(column="Country", op=Operator.EQ, value="DE"),
    )
    assert [dict(row) for row in iter_matching_rows(path, mask)] == [{"Country": "DE"}]


def test_multi_source_overlaps_and_sheet_selection(csv_file: Path, tmp_path: Path) -> None:
    path = csv_file
    source = {"columns": [{"name": "value", "column": "A"}], "data_start_row": 2, "data_end_row": 2}
    mask = {"sheet": None, "sources": [dict(source, name="one"), dict(source, name="two")]}
    with scan_batches(path, mask) as batches:
        records = [r for batch in batches for r in batch]
    assert [(r.table, r.values) for r in records] == [
        ("one", {"value": "1"}),
        ("two", {"value": "1"}),
    ]


def test_header_bound_source_reconstructs_physical_rows(tmp_path: Path) -> None:
    path = tmp_path / "multi.csv"
    path.write_text("Title,,\nAccount,Revenue,Revenue\nID,EUR,USD\na,1,2\n")
    mask = {
        "sheet": None,
        "sources": [
            {
                "name": "sales",
                "header_start_row": 2,
                "data_start_row": 4,
                "rules": {"header": {"rows": 2}},
            }
        ],
    }
    assert dict(next(iter_matching_rows(path, mask))) == {
        "Account ID": "a",
        "Revenue EUR": "1",
        "Revenue USD": "2",
    }


@pytest.mark.parametrize("batch_size", [1, 2, 1024])
def test_missing_select_preserves_other_sources_and_fails_only_at_end(
    tmp_path: Path, batch_size: int
) -> None:
    path = tmp_path / "sources.csv"
    path.write_text("a,1,b,2\nc,3,d,4\n")
    mask = {
        "sheet": None,
        "sources": [
            {
                "name": "bad",
                "columns": [{"name": "A", "column": "A"}, {"name": "B", "column": "B"}],
                "data_start_row": 1,
                "rules": {"select": ["missing"]},
            },
            {
                "name": "good",
                "columns": [{"name": "A", "column": "C"}, {"name": "B", "column": "D"}],
                "data_start_row": 1,
            },
        ],
    }
    records, statistics = partial_scan(path, mask, batch_size)
    assert [(r.table, r.row) for r in records if r.kind == RecordKind.MATCHED] == [
        ("good", 1),
        ("good", 2),
    ]
    assert [r.values for r in records if r.kind == RecordKind.REJECTED] == [
        {"A": "a", "B": "1"},
        {"A": "c", "B": "3"},
    ]
    assert (statistics.matched, statistics.rejected) == (2, 2)
    with iter_matching_batches(path, mask, batch_size=batch_size) as batches:
        matches = []
        with pytest.raises(RuntimeError, match="SCHEMA_MISMATCH"):
            matches.extend(dict(row) for batch in batches for row in batch)
        assert matches == [{"A": "b", "B": "2"}, {"A": "d", "B": "4"}]
        assert batches.statistics is not None
        assert not batches.statistics.complete


def test_invalid_header_bound_source_does_not_abort_valid_source(tmp_path: Path) -> None:
    path = tmp_path / "header.csv"
    path.write_text(" CODE ,code,,A,B\nx,y,,ok,2\n")
    mask = {
        "sheet": None,
        "sources": [
            {
                "header_start_row": 1,
                "first_column": "A",
                "last_column": "B",
                "data_start_row": 2,
                "rules": {"header": {"trim": True, "lowercase": True}},
            },
            {
                "name": "good",
                "columns": [{"name": "A", "column": "D"}, {"name": "B", "column": "E"}],
                "data_start_row": 2,
            },
        ],
    }
    records, _ = partial_scan(path, mask, 1)
    assert [r.values for r in records if r.kind == RecordKind.MATCHED] == [{"A": "ok", "B": "2"}]


def test_invalid_header_bound_source_preserves_bounds_and_skip_rows(tmp_path: Path) -> None:
    path = tmp_path / "bounds.csv"
    path.write_text(" CODE ,code\na,b\nc,d\ne,f\n")
    mask = {
        "sheet": None,
        "source": {
            "header_start_row": 1,
            "data_start_row": 2,
            "data_end_row": 3,
            "skip_rows": [2],
            "rules": {"header": {"trim": True, "lowercase": True}},
        },
    }
    records, _ = partial_scan(path, mask, 1)
    assert [(r.row, r.values) for r in records] == [(3, {"A": "c", "B": "d"})]


@pytest.mark.parametrize("batch_size", [1, 2, 1024])
def test_offset_multiline_duplicate_headers_comments_and_neighbor_table(
    tmp_path: Path,
    batch_size: int,
) -> None:
    path = tmp_path / "layout.xlsx"
    layout_workbook(path)
    original = path.read_bytes()
    expected = [
        {"Kunde": "ABC One", "Umsatz": 120},
        {"Kunde": "ABC Two", "Umsatz": 200},
    ]
    assert [
        dict(row) for row in iter_matching_rows(path, source_mask(), batch_size=batch_size)
    ] == expected
    with iter_matching_batches(path, source_mask(), batch_size=batch_size) as batches:
        assert [dict(row) for batch in batches for row in batch] == expected
    assert path.read_bytes() == original


def test_neighbor_table_is_selected_independently(tmp_path: Path) -> None:
    path = tmp_path / "neighbor.xlsx"
    layout_workbook(path)
    mask = FilterMask(
        sheet="Daten",
        source=TableSource(
            columns=(
                ColumnBinding(name="Kunde", column="G"),
                ColumnBinding(name="Umsatz", column="H"),
            ),
            data_start_row=7,
            data_end_row=10,
            skip_rows=(8,),
        ),
        where=source_mask().where,
    )
    assert [dict(row) for row in iter_matching_rows(path, mask)] == [
        {"Kunde": "ABC Right One", "Umsatz": 150},
        {"Kunde": "ABC Right Two", "Umsatz": 250},
    ]


def test_end_of_sheet_and_multiple_aliases_for_same_column(tmp_path: Path) -> None:
    path = tmp_path / "aliases.xlsx"
    layout_workbook(path)
    mask = FilterMask(
        sheet="Daten",
        source=TableSource(
            columns=(
                ColumnBinding(name="Kunde", column="C"),
                ColumnBinding(name="Copy", column="C"),
            ),
            data_start_row=10,
        ),
        where=AllOf(
            conditions=(
                TextCondition(column="Kunde", op=Operator.STARTS_WITH, value="ABC"),
                EmptyCondition(column="Copy", op=Operator.NOT_EMPTY),
            )
        ),
    )
    assert [dict(row) for row in iter_matching_rows(path, mask)] == [
        {"Kunde": "ABC Two", "Copy": "ABC Two"},
        {"Kunde": "ABC Footer", "Copy": "ABC Footer"},
    ]


@pytest.mark.parametrize(
    "updates",
    [
        {"data_start_row": True},
        {"data_start_row": 0},
        {"data_end_row": 6},
        {"data_end_row": 1048577},
        {"skip_rows": [6]},
        {"skip_rows": [11]},
        {"columns": []},
        {"columns": [{"name": "x", "column": "XFE"}]},
        {"columns": [{"name": "x", "column": "a"}]},
        {"columns": [{"name": "x", "column": "A1"}]},
        {"columns": [{"name": " ", "column": "A"}]},
        {"columns": [{"name": "x", "column": "A"}, {"name": "x", "column": "B"}]},
        {"unexpected": "field"},
    ],
)
def test_invalid_scopes_fail_before_io(updates: dict[str, object]) -> None:
    payload = source_mask().model_dump(by_alias=True)
    source = source_mask().source
    assert source is not None
    source_payload = source.model_dump()
    source_payload.update(updates)
    payload["source"] = source_payload
    with pytest.raises(ValidationError):
        iter_matching_batches("missing.xlsx", payload)


def test_source_rejects_conflicting_header_and_unknown_alias(tmp_path: Path) -> None:
    payload = source_mask().model_dump(by_alias=True)
    payload["header_row"] = 3
    with pytest.raises(ValidationError, match="header_row"):
        iter_matching_batches("missing.xlsx", payload)
    path = tmp_path / "unknown.xlsx"
    layout_workbook(path)
    mask = FilterMask(
        sheet="Daten",
        source=source_mask().source,
        where=ScalarCondition(column="Unknown", op=Operator.EQ, value="x"),
    )
    with (
        pytest.raises(RuntimeError, match="SCHEMA_MISMATCH"),
        iter_matching_batches(path, mask) as batches,
    ):
        list(batches)
