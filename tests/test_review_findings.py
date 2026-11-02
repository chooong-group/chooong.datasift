"""Real-file regression coverage for the schema, discovery and recovery review findings."""

import json
from collections.abc import Mapping
from hashlib import sha256
from pathlib import Path

import pytest
from test_all_sheets import _book, _Sheet, _worksheet
from test_engine import _cell

from chooong.datasift import (
    RecordKind,
    ScanRecord,
    Statistics,
    export,
    iter_matching_batches,
    recover_export,
    scan_batches,
)


def _partial(
    path: Path, mask: Mapping[str, object], batch_size: int
) -> tuple[list[ScanRecord], Statistics]:
    records: list[ScanRecord] = []
    with scan_batches(path, mask, batch_size=batch_size) as batches:
        with pytest.raises(RuntimeError, match="SCHEMA_MISMATCH"):
            records.extend(record for batch in batches for record in batch)
        statistics = batches.statistics
    assert statistics is not None
    assert not statistics.complete
    return records, statistics


def _rows(values: list[tuple[object, ...]]) -> str:
    result = []
    for number, row in enumerate(values, start=1):
        cells = "".join(_cell(chr(65 + index), number, value) for index, value in enumerate(row))
        result.append(f'<row r="{number}">{cells}</row>')
    return _worksheet(*result)


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
    records, statistics = _partial(path, mask, batch_size)
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


@pytest.mark.parametrize("selection", [["C"], [{"pattern": "^C$"}]])
def test_missing_projection_in_first_sheet_does_not_hide_second_sheet(
    tmp_path: Path, selection: list[object]
) -> None:
    path = tmp_path / "schemas.xlsx"
    _book(
        path,
        _Sheet("Bad", _rows([("A", "B"), ("bad", 1)])),
        _Sheet("Good", _rows([("A", "C"), ("good", 2)])),
    )
    records, statistics = _partial(path, {"sheet": None, "select": selection}, 1)
    assert [r.values for r in records if r.kind == RecordKind.MATCHED] == [{"C": 2}]
    assert statistics.diagnostics[0].code == "SCHEMA_MISMATCH"


def test_normalization_collision_quarantines_only_its_table(tmp_path: Path) -> None:
    path = tmp_path / "collision.xlsx"
    _book(
        path,
        _Sheet(
            "Data",
            _rows(
                [
                    (" CODE ", "code", "Value", None, "code", "Value"),
                    ("x", "y", 1, None, "ok", 2),
                    (),
                    (None, None, None, None, "code", "Value"),
                    (None, None, None, None, "later", 3),
                ]
            ),
        ),
    )
    mask = {
        "sheet": None,
        "header": {"anchors": ["code", "value"], "trim": True, "lowercase": True},
        "select": ["*"],
    }
    records, statistics = _partial(path, mask, 1)
    assert [r.values for r in records if r.kind == RecordKind.MATCHED] == [
        {"code": "ok", "value": 2},
        {"code": "later", "value": 3},
    ]
    rejected = [r for r in records if r.kind == RecordKind.REJECTED]
    assert rejected[0].values == {"A": "x", "B": "y", "C": 1}
    assert any(d.code == "SCHEMA_MISMATCH" for d in statistics.diagnostics)


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
    records, _ = _partial(path, mask, 1)
    assert [r.values for r in records if r.kind == RecordKind.MATCHED] == [{"A": "ok", "B": "2"}]


@pytest.mark.parametrize("batch_size", [1, 2, 1024])
def test_free_discovery_handles_different_side_by_side_and_stacked_schemas(
    tmp_path: Path, batch_size: int
) -> None:
    path = tmp_path / "free.xlsx"
    _book(
        path,
        _Sheet(
            "Data",
            _rows(
                [
                    ("A title",),
                    ("Name", "Amount", None, "Code", "Count", "Flag"),
                    ("left", 1, None, "right", 2, True),
                    (),
                    ("Another title",),
                    (None, "City", "Population"),
                    (None, "Berlin", 3),
                ]
            ),
        ),
    )
    with scan_batches(path, {"sheet": None}, batch_size=batch_size) as batches:
        records = [r for batch in batches for r in batch]
        assert batches.statistics is not None
        assert batches.statistics.complete
    assert [r.values for r in records] == [
        {"Name": "left", "Amount": 1},
        {"Code": "right", "Count": 2, "Flag": True},
        {"City": "Berlin", "Population": 3},
    ]


def test_free_multiline_headers_use_same_rule_after_first_table(tmp_path: Path) -> None:
    path = tmp_path / "multi.xlsx"
    _book(
        path,
        _Sheet(
            "Data",
            _rows(
                [
                    ("Account", "Revenue"),
                    ("ID", "EUR"),
                    ("one", 1),
                    ("Account", "Revenue"),
                    ("ID", "EUR"),
                    ("two", 3),
                    (),
                    ("City", "Population"),
                    ("Name", "Count"),
                    ("Berlin", 2),
                ]
            ),
        ),
    )
    with scan_batches(path, {"sheet": None, "header": {"rows": 2}}) as batches:
        records = [r for batch in batches for r in batch]
    assert [r.values for r in records] == [
        {"Account ID": "one", "Revenue EUR": 1},
        {"Account ID": "two", "Revenue EUR": 3},
        {"City Name": "Berlin", "Population Count": 2},
    ]


def test_free_text_title_and_ambiguous_text_table_are_not_silent_success(tmp_path: Path) -> None:
    path = tmp_path / "ambiguous.xlsx"
    _book(
        path,
        _Sheet(
            "Data",
            _rows(
                [
                    ("Quarter", "Report"),
                    ("Name", "State"),
                    ("Alice", "Open"),
                    (),
                    ("Code", "Count"),
                    ("ok", 2),
                ]
            ),
        ),
    )
    records, statistics = _partial(path, {"sheet": None}, 1)
    assert [r.values for r in records if r.kind == RecordKind.MATCHED] == [
        {"Code": "ok", "Count": 2}
    ]
    assert any(d.code == "AMBIGUOUS_HEADER" for d in statistics.diagnostics)
    assert any(r.values == {"A": "Name", "B": "State"} for r in records)


def test_schema_errors_never_commit_either_export(tmp_path: Path) -> None:
    path = tmp_path / "bad.csv"
    path.write_text("A,B\na,1\n")
    output = tmp_path / "matches.parquet"
    rejected = tmp_path / "rejects.ndjson"
    output.write_bytes(b"previous matches")
    rejected.write_bytes(b"previous rejects")
    with pytest.raises(RuntimeError, match="SCHEMA_MISMATCH"):
        export(path, {"sheet": None, "select": ["missing"]}, output, rejected_output=rejected)
    assert output.read_bytes() == b"previous matches"
    assert rejected.read_bytes() == b"previous rejects"


def _journal(tmp_path: Path) -> tuple[Path, Path, Path, str]:
    output = tmp_path / "matched.ndjson"
    stage = tmp_path / ".matched.ndjson.datasift-1-0.tmp"
    journal = tmp_path / ".matched.ndjson.datasift-commit.json"
    output.write_bytes(b"old")
    stage.write_bytes(b"new")
    journal.write_text(
        json.dumps(
            {
                "version": 1,
                "entries": [
                    {
                        "destination": str(output),
                        "stage": str(stage),
                        "sha256": sha256(b"new").hexdigest(),
                    }
                ],
            }
        )
    )
    return output, stage, journal, sha256(journal.read_bytes()).hexdigest()


def test_recovery_requires_trusted_digest_and_explicit_destinations(tmp_path: Path) -> None:
    output, stage, journal, trusted = _journal(tmp_path)
    victim = tmp_path / "victim.ndjson"
    victim.write_bytes(b"do not overwrite")
    payload = json.loads(journal.read_text())
    payload["entries"][0]["destination"] = str(victim)
    journal.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="Prüfsumme"):
        recover_export(output, journal_sha256=trusted)
    with pytest.raises(ValueError, match="Zielpfad"):
        recover_export(output, journal_sha256=sha256(journal.read_bytes()).hexdigest())
    assert victim.read_bytes() == b"do not overwrite"
    assert output.read_bytes() == b"old"
    assert stage.read_bytes() == b"new"


@pytest.mark.parametrize("path_kind", ["journal", "stage", "target", "lock"])
def test_recovery_rejects_hardlink_aliases(tmp_path: Path, path_kind: str) -> None:
    output, stage, journal, trusted = _journal(tmp_path)
    lock = tmp_path / ".matched.ndjson.datasift.lock"
    lock.write_bytes(b"")
    selected = {"journal": journal, "stage": stage, "target": output, "lock": lock}[path_kind]
    alias = tmp_path / "alias"
    alias.hardlink_to(selected)
    previous = output.read_bytes()
    with pytest.raises(ValueError, match="Hardlink"):
        recover_export(output, journal_sha256=trusted)
    assert output.read_bytes() == previous
    assert alias.read_bytes() == selected.read_bytes()


@pytest.mark.parametrize("path_kind", ["journal", "stage", "target", "lock"])
def test_recovery_rejects_symlink_aliases(tmp_path: Path, path_kind: str) -> None:
    output, stage, journal, trusted = _journal(tmp_path)
    lock = tmp_path / ".matched.ndjson.datasift.lock"
    lock.write_bytes(b"")
    selected = {"journal": journal, "stage": stage, "target": output, "lock": lock}[path_kind]
    victim = tmp_path / "victim"
    selected.replace(victim)
    selected.symlink_to(victim)
    previous = victim.read_bytes()
    with pytest.raises(ValueError, match="sicherer regulärer Pfad|Symlink"):
        recover_export(output, journal_sha256=trusted)
    assert victim.read_bytes() == previous


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


def test_indexed_collision_does_not_hide_independent_neighbor(tmp_path: Path) -> None:
    path = tmp_path / "indexed.csv"
    path.write_text("Value_1,Value,Value,,Value_1,Value_2\nx,1,2,,3,4\n")
    records, _ = _partial(
        path,
        {
            "sheet": None,
            "where": {
                "all": [
                    {"column": "Value_1", "op": "ne", "value": "x"},
                    {"column": "Value_2", "op": "ne", "value": "x"},
                ]
            },
        },
        1,
    )
    assert [r.values for r in records if r.kind == RecordKind.MATCHED] == [
        {"Value_1": "3", "Value_2": "4"}
    ]


def test_missing_header_bound_schema_has_incomplete_statistics(tmp_path: Path) -> None:
    path = tmp_path / "missing.csv"
    path.write_text("title\n")
    mask = {"sheet": None, "source": {"header_start_row": 3, "data_start_row": 4}}
    records, statistics = _partial(path, mask, 1)
    assert records == []
    assert statistics.diagnostics[0].code == "SCHEMA_MISMATCH"
    with (
        iter_matching_batches(path, mask) as batches,
        pytest.raises(RuntimeError, match="SCHEMA_MISMATCH"),
    ):
        list(batches)
    assert batches.statistics is not None
    assert not batches.statistics.complete


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
    records, _ = _partial(path, mask, 1)
    assert [(r.row, r.values) for r in records] == [(3, {"A": "c", "B": "d"})]


def test_recovery_requires_confirmation_of_second_destination(tmp_path: Path) -> None:
    output, _, journal, _ = _journal(tmp_path)
    rejected = tmp_path / "rejects.ndjson"
    rejected.write_bytes(b"old rejects")
    stage = tmp_path / ".rejects.ndjson.datasift-1-1.tmp"
    stage.write_bytes(b"new rejects")
    payload = json.loads(journal.read_text())
    payload["entries"].append(
        {
            "destination": str(rejected),
            "stage": str(stage),
            "sha256": sha256(b"new rejects").hexdigest(),
        }
    )
    journal.write_text(json.dumps(payload))
    trusted = sha256(journal.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="vollständig bestätigt"):
        recover_export(output, journal_sha256=trusted)
    assert output.read_bytes() == b"old"
    assert rejected.read_bytes() == b"old rejects"
    recover_export(output, journal_sha256=trusted, rejected_output=rejected)
    assert output.read_bytes() == b"new"
    assert rejected.read_bytes() == b"new rejects"


def test_empty_normalized_free_schema_does_not_abort_neighbor(tmp_path: Path) -> None:
    path = tmp_path / "empty-headers.csv"
    path.write_text("  ,  ,,Name,Count\n1,2,,ok,3\n")
    records, _ = _partial(path, {"sheet": None, "header": {"trim": True}}, 1)
    assert [r.values for r in records if r.kind == RecordKind.MATCHED] == [
        {"Name": "ok", "Count": "3"}
    ]
