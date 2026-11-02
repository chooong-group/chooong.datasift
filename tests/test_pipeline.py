"""Public end-to-end feature interactions using real CSV and OOXML inputs."""

import json
from decimal import Decimal
from hashlib import sha256
from pathlib import Path

import pytest
from test_all_sheets import _book, _Sheet, _worksheet
from test_engine import _cell

from chooong.datasift import (
    FilterMask,
    Money,
    RecordKind,
    RejectCode,
    export,
    iter_matching_batches,
    iter_matching_rows,
    recover_export,
    scan_batches,
)


def _csv(tmp_path: Path) -> Path:
    path = tmp_path / "input.csv"
    path.write_text('ID,Amount,Country\n1,"1.234,56",DE\n,"bad",AT\n3,,\n', encoding="utf-8")
    return path


def _mask() -> dict[str, object]:
    return {
        "sheet": None,
        "header": {"anchors": ["ID", "Amount", "Country"]},
        "required": ["ID", "Amount"],
        "defaults": {"Country": "UNKNOWN", "Amount": "0,00"},
        "types": {
            "Amount": {"type": "money", "currency": "EUR", "locale": "de-DE", "convert": True}
        },
        "select": ["Country", "Amount"],
    }


@pytest.mark.parametrize("batch_size", [1, 2, 1024])
def test_defaults_conversion_rejects_projection_and_statistics(
    tmp_path: Path, batch_size: int
) -> None:
    path = _csv(tmp_path)
    with scan_batches(path, _mask(), batch_size=batch_size) as batches:
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
    rows = list(iter_matching_rows(path, _mask(), batch_size=batch_size))
    assert list(rows[0]) == ["Country", "Amount"]
    assert rows[0]["Amount"] == Money(Decimal("1234.56"), "EUR")
    assert rows[1]["Amount"] == Money(Decimal("0.00"), "EUR")


@pytest.mark.parametrize("selection", [["*"], [{"pattern": "^(ID|Amount)$"}], ["Country", "ID"]])
def test_optional_where_and_regex_projection(tmp_path: Path, selection: list[object]) -> None:
    path = _csv(tmp_path)
    rows = list(iter_matching_rows(path, {"sheet": None, "select": selection}))
    assert len(rows) == 3
    assert list(rows[0]) == (
        ["ID", "Amount", "Country"]
        if selection == ["*"]
        else ["ID", "Amount"]
        if isinstance(selection[0], dict)
        else ["Country", "ID"]
    )


def test_exact_money_comparison_after_conversion_and_currency_mismatch(tmp_path: Path) -> None:
    path = _csv(tmp_path)
    mask = _mask()
    mask["where"] = {
        "all": [
            {"column": "Amount", "op": "is_type", "value": "money"},
            {
                "column": "Amount",
                "op": "gte",
                "value": {
                    "type": "money",
                    "amount": "1234.560000000000000000000001",
                    "currency": "EUR",
                },
            },
        ]
    }
    assert list(iter_matching_rows(path, mask)) == []
    mask["where"] = {
        "column": "Amount",
        "op": "gte",
        "value": {"type": "money", "amount": "0", "currency": "USD"},
    }
    assert list(iter_matching_rows(path, mask)) == []


def test_zero_false_defaults_and_schema_rejections(tmp_path: Path) -> None:
    path = tmp_path / "data.xlsx"
    _book(
        path,
        _Sheet(
            "Data",
            _worksheet(
                '<row r="1">' + _cell("A", 1, "A") + _cell("B", 1, "B") + "</row>",
                '<row r="2">' + _cell("A", 2, 0) + _cell("B", 2, False) + "</row>",
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


def test_multi_source_overlaps_and_sheet_selection(tmp_path: Path) -> None:
    path = _csv(tmp_path)
    source = {"columns": [{"name": "value", "column": "A"}], "data_start_row": 2, "data_end_row": 2}
    mask = {"sheet": None, "sources": [dict(source, name="one"), dict(source, name="two")]}
    with scan_batches(path, mask) as batches:
        records = [r for batch in batches for r in batch]
    assert [(r.table, r.values) for r in records] == [
        ("one", {"value": "1"}),
        ("two", {"value": "1"}),
    ]


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


def test_native_exports_one_scan_and_replay_preserves_failed_outputs(tmp_path: Path) -> None:
    path = _csv(tmp_path)
    matched = tmp_path / "matched.ndjson"
    rejected = tmp_path / "rejected.ndjson"
    stats = export(path, _mask(), matched, rejected_output=rejected, batch_size=1)
    assert (stats.matched, stats.rejected) == (2, 1)
    assert len(matched.read_text().splitlines()) == 2
    assert json.loads(rejected.read_text())["values"]["Amount"] == "bad"
    previous = (matched.read_bytes(), rejected.read_bytes())
    bad = tmp_path / "broken.xlsx"
    bad.write_bytes(b"broken")
    with pytest.raises(RuntimeError):
        export([path, bad], _mask(), matched, rejected_output=rejected)
    assert (matched.read_bytes(), rejected.read_bytes()) == previous
    export(path, _mask(), matched, rejected_output=rejected)
    assert (matched.read_bytes(), rejected.read_bytes()) == previous
    assert not list(tmp_path.glob("*.tmp"))


def test_journal_recovery_rolls_forward_and_refuses_replay(tmp_path: Path) -> None:
    matched = tmp_path / "matched.ndjson"
    rejected = tmp_path / "rejected.ndjson"
    stage = tmp_path / ".rejected.ndjson.datasift-123-0.tmp"
    matched.write_text("new match")
    rejected.write_text("old reject")
    stage.write_text("new reject")
    journal = tmp_path / ".matched.ndjson.datasift-commit.json"
    journal.write_text(
        json.dumps(
            {
                "version": 1,
                "entries": [
                    {
                        "destination": str(matched),
                        "stage": str(tmp_path / ".matched.ndjson.datasift-123-0.tmp"),
                        "sha256": sha256(b"new match").hexdigest(),
                    },
                    {
                        "destination": str(rejected),
                        "stage": str(stage),
                        "sha256": sha256(b"new reject").hexdigest(),
                    },
                ],
            }
        )
    )
    trusted = sha256(journal.read_bytes()).hexdigest()
    recover_export(matched, journal_sha256=trusted, rejected_output=rejected)
    assert matched.read_text() == "new match"
    assert rejected.read_text() == "new reject"
    assert not journal.exists()
    with pytest.raises(ValueError, match="fehlt"):
        recover_export(matched, journal_sha256=trusted, rejected_output=rejected)


def test_encoding_bom_quotes_newlines_and_invalid_encoding(tmp_path: Path) -> None:
    path = tmp_path / "utf16.csv"
    path.write_bytes('A;B\n"München\nNord";"a; b"\n'.encode("utf-16"))
    mask = {
        "sheet": None,
        "header": {"anchors": ["A", "B"]},
        "csv": {"encoding": "utf-16le", "delimiter": ";"},
    }
    rows = list(iter_matching_rows(path, mask))
    assert dict(rows[0]) == {"A": "München\nNord", "B": "a; b"}
    path.write_bytes(b"A,B\n\xff,1\n")
    with pytest.raises((ValueError, RuntimeError)):
        list(iter_matching_rows(path, {"sheet": None}))


def test_iterator_close_and_reject_opt_out(tmp_path: Path) -> None:
    path = _csv(tmp_path)
    with scan_batches(path, _mask(), rejected=False, batch_size=1) as batches:
        assert next(batches)[0].kind == RecordKind.MATCHED
        batches.close()
        assert list(batches) == []
    with iter_matching_batches(path, {"sheet": None}) as batches:
        list(batches)
        assert batches.statistics is not None
        assert batches.statistics.complete


def test_header_normalization_and_collision_fail_closed(tmp_path: Path) -> None:
    path = tmp_path / "normalized.csv"
    path.write_text(" CODE ,Amount\na,1\n")
    mask = {
        "sheet": None,
        "header": {"trim": True, "lowercase": True, "anchors": ["code", "amount"]},
    }
    assert dict(next(iter_matching_rows(path, mask))) == {"code": "a", "amount": "1"}
    path.write_text(" CODE ,code\na,b\n")
    with pytest.raises((ValueError, RuntimeError), match="SCHEMA_MISMATCH"):
        list(iter_matching_rows(path, mask))


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


def test_full_model_contract_roundtrip() -> None:
    spec = FilterMask.model_validate(_mask())
    assert FilterMask.model_validate_json(spec.model_dump_json()) == spec


@pytest.mark.parametrize(
    ("target", "value", "expected"),
    [
        ("integer", "123", 123),
        ("float", "0.5", 0.5),
        ("number", "0.5", 0.5),
        ("boolean", "false", False),
        ("decimal", "0.1234567890123456789012345678", Decimal("0.1234567890123456789012345678")),
        ("currency_code", "EUR", "EUR"),
        ("string", "literal", "literal"),
    ],
)
def test_type_conversion_then_nested_type_filters(tmp_path, target, value, expected) -> None:
    path = tmp_path / "types.csv"
    path.write_text(f"Value,Other\n{value},x\ninvalid,x\n")
    mask = {
        "sheet": None,
        "types": {"Value": {"type": target, "convert": True}},
        "where": {
            "all": [
                {"column": "Value", "op": "is_type", "value": target},
                {"not": {"column": "Value", "op": "not_type", "value": target}},
            ]
        },
    }
    rows = list(iter_matching_rows(path, mask))
    assert rows[0]["Value"] == expected
    assert len(rows) == (2 if target == "string" else 1)


@pytest.mark.parametrize(
    ("date1904", "serial", "expected"),
    [
        (False, 59, "1900-02-28"),
        (False, 60, None),
        (False, 61, "1900-03-01"),
        (True, 0, "1904-01-01"),
    ],
)
def test_real_excel_date_systems_and_styles(tmp_path, date1904, serial, expected) -> None:
    from datetime import date
    from zipfile import ZIP_DEFLATED, ZipFile

    from test_contract import _rewrite

    path = tmp_path / "dates.xlsx"
    document = _worksheet(
        '<row r="1">' + _cell("A", 1, "Date") + _cell("B", 1, "ID") + "</row>",
        f'<row r="2"><c r="A2" s="0"><v>{serial}</v></c>' + _cell("B", 2, "x") + "</row>",
    )
    _book(path, _Sheet("Data", document))
    if date1904:
        _rewrite(path, "xl/workbook.xml", "<sheets>", '<workbookPr date1904="1"/><sheets>')
    with ZipFile(path) as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}
    parts["xl/styles.xml"] = b'<styleSheet><cellXfs><xf numFmtId="14"/></cellXfs></styleSheet>'
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
        for name, content in parts.items():
            archive.writestr(name, content)
    mask = {"sheet": None, "types": {"Date": {"type": "date"}}}
    with scan_batches(path, mask) as batches:
        records = [r for batch in batches for r in batch]
    if expected is None:
        assert records[0].kind == RecordKind.REJECTED
    else:
        assert records[0].kind == RecordKind.MATCHED
        assert next(iter_matching_rows(path, mask))["Date"] == date.fromisoformat(expected)
    # Explicitly unconfigured scalar output is compatible.
    assert next(iter_matching_rows(path, {"sheet": None}))["Date"] == serial


def test_temporal_text_formats_and_nanoseconds(tmp_path) -> None:
    from datetime import date

    from chooong.datasift import PreciseDateTime

    path = tmp_path / "time.csv"
    path.write_text("Date,Time\n01.11.2026,2026-11-01T12:00:00.123456789\n")
    mask = {
        "sheet": None,
        "types": {
            "Date": {"type": "date", "convert": True, "format": "%d.%m.%Y"},
            "Time": {"type": "datetime", "convert": True},
        },
    }
    row = next(iter_matching_rows(path, mask))
    assert row["Date"] == date(2026, 11, 1)
    assert row["Time"] == PreciseDateTime("2026-11-01T12:00:00.123456789")


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


def test_merged_header_expansion_is_native(tmp_path) -> None:
    path = tmp_path / "merged.xlsx"
    document = _worksheet(
        '<row r="1">' + _cell("A", 1, "Revenue") + "</row>",
        '<row r="2">' + _cell("A", 2, "EUR") + _cell("B", 2, "USD") + "</row>",
        '<row r="3">' + _cell("A", 3, 1) + _cell("B", 3, 2) + "</row>",
    ).replace("</worksheet>", '<mergeCells><mergeCell ref="A1:B1"/></mergeCells></worksheet>')
    _book(path, _Sheet("Data", document))
    mask = {
        "sheet": None,
        "sources": [
            {
                "header_start_row": 1,
                "data_start_row": 3,
                "rules": {"header": {"rows": 2, "merged_fill": True}},
            }
        ],
    }
    assert dict(next(iter_matching_rows(path, mask))) == {"Revenue EUR": 1, "Revenue USD": 2}


def test_cli_dual_output_explain_and_parquet(tmp_path, monkeypatch) -> None:
    import sys

    from chooong.datasift.__main__ import main

    path = _csv(tmp_path)
    mask = tmp_path / "mask.json"
    mask.write_text(json.dumps(_mask()))
    matched = tmp_path / "matched.parquet"
    rejected = tmp_path / "rejected.parquet"
    stats = tmp_path / "statistics.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "chooong-datasift",
            str(path),
            str(mask),
            "--output",
            str(matched),
            "--rejected-output",
            str(rejected),
            "--explain",
            str(stats),
        ],
    )
    main()
    assert json.loads(stats.read_text())["matched"] == 2
    assert matched.read_bytes()[:4] == b"PAR1"
    assert rejected.read_bytes()[-4:] == b"PAR1"


def test_projection_can_select_columns_before_filter_and_validation_is_independent(
    tmp_path,
) -> None:
    path = tmp_path / "projection.csv"
    path.write_text("ID,Amount,Country\nfirst,12,DE\nsecond,bad,DE\n")
    mask = {
        "sheet": None,
        "where": {"column": "Country", "op": "eq", "value": "DE"},
        "select": ["ID"],
        "types": {"Amount": {"type": "integer", "convert": True}},
    }
    assert [dict(r) for r in iter_matching_rows(path, mask)] == [{"ID": "first"}]


def test_timezone_offsets_are_preserved_and_comparisons_use_instants(tmp_path) -> None:
    from datetime import datetime

    path = tmp_path / "timezone.csv"
    path.write_text("Date,Other\n2026-11-01T13:00:00+01:00,x\n")
    mask = {
        "sheet": None,
        "types": {"Date": {"type": "datetime", "convert": True}},
        "where": {
            "column": "Date",
            "op": "eq",
            "value": {"type": "datetime", "value": "2026-11-01T12:00:00Z"},
        },
    }
    row = next(iter_matching_rows(path, mask))
    assert row["Date"] == datetime.fromisoformat("2026-11-01T13:00:00+01:00")
    assert row["Date"].isoformat() == "2026-11-01T13:00:00+01:00"


def test_money_currency_mismatch_cannot_pass_through_not(tmp_path) -> None:
    path = _csv(tmp_path)
    mask = _mask()
    mask["where"] = {
        "not": {
            "column": "Amount",
            "op": "eq",
            "value": {"type": "money", "amount": "1", "currency": "USD"},
        }
    }
    assert list(iter_matching_rows(path, mask)) == []


@pytest.mark.parametrize("selection", [["missing"], [{"pattern": "^missing$"}]])
def test_missing_projection_fails_without_silent_loss(tmp_path, selection) -> None:
    path = _csv(tmp_path)
    with pytest.raises((ValueError, RuntimeError), match="SCHEMA_MISMATCH"):
        list(iter_matching_rows(path, {"sheet": None, "select": selection}))


def test_explicit_type_mismatch_is_row_local(tmp_path) -> None:
    path = _csv(tmp_path)
    mask = {"sheet": None, "types": {"Amount": {"type": "integer"}}}
    with scan_batches(path, mask) as batches:
        records = [r for batch in batches for r in batch]
    assert records[0].reasons[0].code == RejectCode.TYPE_MISMATCH
    assert len(records) == 3


def test_null_and_unicode_normalization(tmp_path) -> None:
    path = tmp_path / "unicode.csv"
    path.write_text("Cafe\u0301,Value\na,\n")
    mask = {
        "sheet": None,
        "header": {"unicode": "NFC"},
        "where": {"column": "Value", "op": "is_type", "value": "null"},
        "select": ["*"],
    }
    assert dict(next(iter_matching_rows(path, mask))) == {"Café": "a", "Value": None}


def test_commit_metadata_paths_cannot_be_result_paths(tmp_path) -> None:
    path = _csv(tmp_path)
    output = tmp_path / "matched.ndjson"
    for rejected in (
        tmp_path / ".matched.ndjson.datasift-commit.json",
        tmp_path / ".matched.ndjson.datasift.lock",
    ):
        with pytest.raises(RuntimeError, match="Metadaten"):
            export(path, _mask(), output, rejected_output=rejected)
    assert not output.exists()


def test_recovery_detects_missing_uncommitted_stage_and_tampering(tmp_path) -> None:
    output = tmp_path / "matched.ndjson"
    output.write_text("old result")
    stage = tmp_path / ".matched.ndjson.datasift-1-0.tmp"
    journal = tmp_path / ".matched.ndjson.datasift-commit.json"
    journal.write_text(
        json.dumps(
            {
                "version": 1,
                "entries": [
                    {
                        "destination": str(output),
                        "stage": str(stage),
                        "sha256": sha256(b"new result").hexdigest(),
                    }
                ],
            }
        )
    )
    trusted = sha256(journal.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="überein"):
        recover_export(output, journal_sha256=trusted)
    assert output.read_text() == "old result"
    assert journal.exists()
    stage.write_text("changed result")
    with pytest.raises(ValueError, match="überein"):
        recover_export(output, journal_sha256=trusted)
    assert output.read_text() == "old result"
    stage.write_text("new result")
    recover_export(output, journal_sha256=trusted)
    assert output.read_text() == "new result"


def test_cli_explain_cannot_overwrite_glob_input(tmp_path, monkeypatch) -> None:
    import sys

    from chooong.datasift.__main__ import main

    path = _csv(tmp_path)
    mask = tmp_path / "mask.json"
    mask.write_text(json.dumps(_mask()))
    original = path.read_bytes()
    monkeypatch.setattr(
        sys,
        "argv",
        ["chooong-datasift", str(tmp_path / "*.csv"), str(mask), "--explain", str(path)],
    )
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2
    assert path.read_bytes() == original


def test_export_preserves_mask_path_and_hardlink_alias(tmp_path) -> None:
    path = _csv(tmp_path)
    mask = tmp_path / "mask.json"
    mask.write_text(json.dumps(_mask()))
    alias = tmp_path / "alias.json"
    alias.hardlink_to(mask)
    original = mask.read_bytes()
    for destination in (mask, alias):
        with pytest.raises(ValueError, match="Filterdatei"):
            export(path, mask, destination)
    assert mask.read_bytes() == original
