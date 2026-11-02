"""Public contract checks using real synthetic files."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from chooong.datasift import (
    iter_matching_batches,
)
from chooong.datasift.__main__ import main
from tests.fixtures.excel import (
    _FIRST,
    _LABELS,
    _SECOND,
    Sheet,
    cell,
    cli_inputs,
    indexed_workbook,
    layout_workbook,
    make_workbook,
    rewrite,
    table_layout,
    write_book,
)
from tests.fixtures.masks import (
    contract_mask,
    indexed_mask,
    pipeline_mask,
    sheet_mask,
    source_mask,
    table_mask,
)


def test_late_sheet_failure_propagates_and_cli_keeps_existing_output(tmp_path: Path) -> None:
    path = tmp_path / "late.xlsx"
    broken = _SECOND.replace(cell("A", 2, 202), '<c r="A2" t="s"><v>999999</v></c>')
    write_book(path, Sheet("First", _FIRST), Sheet("Broken", broken))
    with iter_matching_batches(path, sheet_mask(), batch_size=1) as batches:
        assert dict(next(batches)[0]) == {"Land": "DE", "Value": 101}
        with pytest.raises(RuntimeError, match="Shared-String-Index"):
            list(batches)
    mask = tmp_path / "mask.json"
    mask.write_text(sheet_mask().model_dump_json(by_alias=True))
    target = tmp_path / "result.ndjson"
    target.write_text("previous")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "chooong.datasift",
            str(path),
            str(mask),
            "--output",
            str(target),
            "--batch-size",
            "1",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert target.read_text() == "previous"
    assert not list(tmp_path.glob(".result.ndjson.*.tmp"))


def test_cli_merges_all_sheet_hits(tmp_path: Path) -> None:
    path = tmp_path / "cli.xlsx"
    write_book(path, Sheet("First", _FIRST), Sheet("Second", _SECOND))
    mask = tmp_path / "mask.json"
    mask.write_text(sheet_mask().model_dump_json(by_alias=True))
    target = tmp_path / "result.ndjson"
    result = subprocess.run(
        [sys.executable, "-m", "chooong.datasift", str(path), str(mask), "--output", str(target)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert [row["Value"] for row in map(json.loads, target.read_text().splitlines())] == [
        101,
        202,
        203,
    ]


@pytest.mark.parametrize("file_output", [True, False])
def test_cli_writes_real_rows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    file_output: bool,
) -> None:
    workbook, mask = cli_inputs(tmp_path)
    destination = tmp_path / "output.ndjson"
    argv = ["chooong-datasift", str(workbook), str(mask), "--batch-size", "1"]
    if file_output:
        argv.extend(["--output", str(destination)])
    monkeypatch.setattr(sys, "argv", argv)
    original = workbook.read_bytes()
    main()
    output = destination.read_text() if file_output else capsys.readouterr().out
    rows = [json.loads(line) for line in output.splitlines()]
    assert len(rows) == 7
    assert all(row == {"Land": "DE"} for row in rows)
    assert workbook.read_bytes() == original


def test_late_error_preserves_target_and_cleans_temp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workbook, mask = cli_inputs(tmp_path)
    make_workbook(workbook, malformed=True)
    destination = tmp_path / "output.ndjson"
    destination.write_text("previous result")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "chooong-datasift",
            str(workbook),
            str(mask),
            "--output",
            str(destination),
            "--batch-size",
            "1",
        ],
    )
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 1
    assert destination.read_text() == "previous result"
    assert not list(tmp_path.glob(".output.ndjson.*.tmp"))
    assert "Filterfehler (RuntimeError)" in capsys.readouterr().err


def test_cli_rejects_input_alias(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    workbook, mask = cli_inputs(tmp_path)
    alias = tmp_path / "alias.xlsx"
    alias.symlink_to(workbook)
    original = workbook.read_bytes()
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "chooong-datasift",
            str(workbook),
            str(mask),
            "--output",
            str(alias),
        ],
    )
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2
    assert workbook.read_bytes() == original


def test_cli_protects_mask_and_redacts_invalid_values(tmp_path: Path) -> None:
    path = tmp_path / "sample.xlsx"
    make_workbook(path)
    mask = tmp_path / "mask.json"
    mask.write_text(contract_mask().model_dump_json(by_alias=True))
    original = mask.read_bytes()
    result = subprocess.run(
        [sys.executable, "-m", "chooong.datasift", str(path), str(mask), "--output", str(mask)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert mask.read_bytes() == original
    mask.write_text(json.dumps({"sheet": "private-data", "where": {"op": "private-value"}}))
    result = subprocess.run(
        [sys.executable, "-m", "chooong.datasift", str(path), str(mask)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "private" not in result.stderr
    assert not result.stdout


def test_cli_extracts_only_bound_fields_in_ndjson(tmp_path: Path) -> None:
    path = tmp_path / "cli-extras.xlsx"
    make_workbook(path)
    before = '<c r="D5" t="s"><v>6</v></c></row>'
    after = '<c r="D5" t="s"><v>6</v></c><c r="M5"><v>123</v></c></row>'
    rewrite(path, "xl/worksheets/data42.xml", before, after)
    original = path.read_bytes()
    mask = tmp_path / "mask.json"
    mask.write_text(contract_mask().model_dump_json(by_alias=True))
    destination = tmp_path / "result.ndjson"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "chooong.datasift",
            str(path),
            str(mask),
            "--output",
            str(destination),
            "--batch-size",
            "1",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert not result.stderr
    rows = [json.loads(line) for line in destination.read_text().splitlines()]
    assert len(rows) == 6
    assert all(set(row) == {"Kunde", "Land", "Status"} for row in rows)
    assert path.read_bytes() == original
    assert not list(tmp_path.glob(".result.ndjson.*.tmp"))


def test_cli_output_is_atomic_on_success_and_error(
    xlsx: Path,
    mask: dict,
    tmp_path: Path,
) -> None:
    import subprocess
    import sys

    mask_file = tmp_path / "mask.json"
    mask_file.write_text(json.dumps(mask), encoding="utf-8")
    destination = tmp_path / "result.ndjson"
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "chooong.datasift",
            str(xlsx),
            str(mask_file),
            "--output",
            str(destination),
            "--batch-size",
            "1",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    actual = [json.loads(line) for line in destination.read_text(encoding="utf-8").splitlines()]
    assert len(actual) == 3

    original_content = destination.read_bytes()
    broken = tmp_path / "corrupt.xlsx"
    make_workbook(broken, malformed=True)
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "chooong.datasift",
            str(broken),
            str(mask_file),
            "--output",
            str(destination),
            "--batch-size",
            "1",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode != 0
    assert destination.read_bytes() == original_content
    assert not list(tmp_path.glob(".result.ndjson.*.tmp"))


def test_cli_cannot_overwrite_input(xlsx: Path, mask: dict, tmp_path: Path) -> None:
    import subprocess
    import sys

    mask_file = tmp_path / "mask.json"
    mask_file.write_text(json.dumps(mask), encoding="utf-8")
    original_bytes = xlsx.read_bytes()
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "chooong.datasift",
            str(xlsx),
            str(mask_file),
            "--output",
            str(xlsx),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert xlsx.read_bytes() == original_bytes


def test_cli_emits_indexed_keys(tmp_path: Path) -> None:
    path = tmp_path / "cli.xlsx"
    indexed_workbook(path)
    mask = tmp_path / "mask.json"
    mask.write_text(indexed_mask().model_dump_json(by_alias=True))
    output = tmp_path / "output.ndjson"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "chooong.datasift",
            str(path),
            str(mask),
            "--output",
            str(output),
            "--batch-size",
            "1",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    rows = [json.loads(line) for line in output.read_text().splitlines()]
    assert len(rows) == 3
    assert rows[0]["Umsatz_1"] == 5000
    assert rows[0]["Umsatz_2"] == "Aktiv"
    assert all("Umsatz" not in row for row in rows)


def test_later_discovered_table_failure_keeps_cli_output_atomic(tmp_path: Path) -> None:
    path = tmp_path / "corrupt.xlsx"
    table_layout(path)
    mask = tmp_path / "mask.json"
    mask.write_text(table_mask().model_dump_json(by_alias=True))
    target = tmp_path / "out.ndjson"
    target.write_text("previous")
    rewrite(
        path,
        "xl/worksheets/part-18.xml",
        cell("O", 16, "approved"),
        '<c r="O16" t="s"><v>999999</v></c>',
    )
    with iter_matching_batches(path, table_mask(), batch_size=1) as batches:
        assert next(batches)[0][_LABELS[1]] == 902
        with pytest.raises(RuntimeError, match="Shared-String-Index"):
            list(batches)
    result = subprocess.run(
        [sys.executable, "-m", "chooong.datasift", str(path), str(mask), "--output", str(target)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert target.read_text() == "previous"
    assert not list(tmp_path.glob(".out.ndjson.*.tmp"))


def test_cli_extracts_all_ten_entries(tmp_path: Path) -> None:
    path = tmp_path / "cli.xlsx"
    table_layout(path)
    mask = tmp_path / "mask.json"
    mask.write_text(table_mask().model_dump_json(by_alias=True))
    target = tmp_path / "out.ndjson"
    result = subprocess.run(
        [sys.executable, "-m", "chooong.datasift", str(path), str(mask), "--output", str(target)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    rows = [json.loads(line) for line in target.read_text().splitlines()]
    assert len(rows) == 10
    assert all(set(row) == set(_LABELS) for row in rows)


def test_cli_dual_output_explain_and_parquet(csv_file: Path, tmp_path, monkeypatch) -> None:
    import sys

    from chooong.datasift.__main__ import main

    path = csv_file
    mask = tmp_path / "mask.json"
    mask.write_text(json.dumps(pipeline_mask()))
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


def test_cli_explain_cannot_overwrite_glob_input(csv_file: Path, tmp_path, monkeypatch) -> None:
    import sys

    from chooong.datasift.__main__ import main

    path = csv_file
    mask = tmp_path / "mask.json"
    mask.write_text(json.dumps(pipeline_mask()))
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


def test_selected_corruption_is_an_error_and_cli_preserves_existing_output(tmp_path: Path) -> None:
    path = tmp_path / "corrupt-selected.xlsx"
    layout_workbook(path)
    rewrite(
        path,
        "xl/worksheets/data42.xml",
        '<c r="D10"><v>200</v></c>',
        '<c r="D10" t="s"><v>999999</v></c>',
    )
    mask_file = tmp_path / "mask.json"
    mask_file.write_text(source_mask().model_dump_json(by_alias=True))
    target = tmp_path / "target.ndjson"
    target.write_text("previous")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "chooong.datasift",
            str(path),
            str(mask_file),
            "--output",
            str(target),
            "--batch-size",
            "1",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "RuntimeError" in result.stderr
    assert target.read_text() == "previous"
    assert not list(tmp_path.glob(".target.ndjson.*.tmp"))


def test_layout_example_cli_output(tmp_path: Path) -> None:
    path = tmp_path / "layout-cli.xlsx"
    layout_workbook(path)
    mask = tmp_path / "mask.json"
    mask.write_text(source_mask().model_dump_json(by_alias=True))
    output = tmp_path / "output.ndjson"
    result = subprocess.run(
        [sys.executable, "-m", "chooong.datasift", str(path), str(mask), "--output", str(output)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert [json.loads(line) for line in output.read_text().splitlines()] == [
        {"Kunde": "ABC One", "Umsatz": 120},
        {"Kunde": "ABC Two", "Umsatz": 200},
    ]
