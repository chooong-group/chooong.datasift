"""Exercise the CLI composition root with real files in the current process."""

import json
import sys
from pathlib import Path

import pytest
from test_engine import make_workbook

from chooong.datasift.__main__ import main


def _inputs(tmp_path: Path) -> tuple[Path, Path]:
    workbook = tmp_path / "sample.xlsx"
    make_workbook(workbook)
    mask = tmp_path / "mask.json"
    mask.write_text(
        json.dumps(
            {
                "sheet": "Daten",
                "where": {"column": "Land", "op": "eq", "value": "DE"},
            }
        )
    )
    return workbook, mask


@pytest.mark.parametrize("file_output", [True, False])
def test_cli_writes_real_rows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    file_output: bool,
) -> None:
    workbook, mask = _inputs(tmp_path)
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
    assert rows[0]["Kunde"] == "ABC GmbH"
    assert rows[-1]["Umsatz"] is True
    assert workbook.read_bytes() == original


def test_late_error_preserves_target_and_cleans_temp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workbook, mask = _inputs(tmp_path)
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
    workbook, mask = _inputs(tmp_path)
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
