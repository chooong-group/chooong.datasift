"""Repeated Excel headers are indexed once and used by filters and output."""

import json
import subprocess
import sys
from pathlib import Path

import pytest
from test_contract import _rewrite
from test_engine import _cell, make_workbook

from chooong.datasift import (
    AllOf,
    FilterMask,
    NumericCondition,
    Operator,
    ScalarCondition,
    iter_matching_batches,
    iter_matching_rows,
)


def _workbook(
    path: Path,
    headers: tuple[str | int | None, ...] = ("Kunde", "Land", "Umsatz", "Umsatz"),
    header_row: int = 1,
) -> None:
    make_workbook(path, header_row=header_row)
    before = (
        f'<row r="{header_row}">'
        + "".join(_cell(chr(65 + i), header_row, i, "shared") for i in range(4))
        + "</row>"
    )
    after = (
        f'<row r="{header_row}">'
        + "".join(_cell(chr(65 + i), header_row, label) for i, label in enumerate(headers))
        + "</row>"
    )
    _rewrite(path, "xl/worksheets/data42.xml", before, after)


def _mask() -> FilterMask:
    return FilterMask(
        sheet="Daten",
        where=AllOf(
            conditions=(
                NumericCondition(column="Umsatz_1", op=Operator.GTE, value=1000),
                ScalarCondition(column="Umsatz_2", op=Operator.EQ, value="Aktiv"),
            )
        ),
    )


@pytest.mark.parametrize("header_row", [1, 3])
@pytest.mark.parametrize("batch_size", [1, 2, 1024])
def test_duplicate_headers_are_indexed_for_filters_and_output(
    tmp_path: Path,
    header_row: int,
    batch_size: int,
) -> None:
    path = tmp_path / "duplicates.xlsx"
    _workbook(path, header_row=header_row)
    original = path.read_bytes()
    expected = [
        {"Umsatz_1": 5000, "Umsatz_2": "Aktiv"},
        {"Umsatz_1": 8000, "Umsatz_2": "Aktiv"},
        {"Umsatz_1": 3200, "Umsatz_2": "Aktiv"},
    ]
    assert [
        dict(row) for row in iter_matching_rows(path, _mask(), batch_size=batch_size)
    ] == expected
    with iter_matching_batches(path, _mask(), batch_size=batch_size) as batches:
        assert [dict(row) for batch in batches for row in batch] == expected
    assert path.read_bytes() == original


def test_three_occurrences_retain_physical_order_and_values(tmp_path: Path) -> None:
    path = tmp_path / "three.xlsx"
    _workbook(path, headers=("Kunde", "Umsatz", "Umsatz", "Umsatz"))
    mask = FilterMask(
        sheet="Daten",
        where=AllOf(
            conditions=(
                ScalarCondition(column="Umsatz_1", op=Operator.EQ, value="DE"),
                NumericCondition(column="Umsatz_2", op=Operator.GTE, value=1000),
                ScalarCondition(column="Umsatz_3", op=Operator.EQ, value="Aktiv"),
            )
        ),
    )
    assert [dict(row) for row in iter_matching_rows(path, mask)] == [
        {"Umsatz_1": "DE", "Umsatz_2": 5000, "Umsatz_3": "Aktiv"},
        {"Umsatz_1": "DE", "Umsatz_2": 3200, "Umsatz_3": "Aktiv"},
    ]


@pytest.mark.parametrize(
    "headers",
    [
        ("Umsatz_1", "Land", "Umsatz", "Umsatz"),
        ("Kunde", "Umsatz", "Umsatz", "Umsatz_1"),
    ],
)
def test_index_collision_fails_at_scan_end(
    tmp_path: Path,
    headers: tuple[str, ...],
) -> None:
    path = tmp_path / "collision.xlsx"
    _workbook(path, headers=headers)
    with (
        pytest.raises(RuntimeError, match="SCHEMA_MISMATCH"),
        iter_matching_batches(path, _mask()) as batches,
    ):
        list(batches)


def test_missing_text_header_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "numeric-header.xlsx"
    _workbook(path, headers=("Kunde", "Land", 123, "Status"))
    with pytest.raises(ValueError, match="Keine Kopfzeile"):
        iter_matching_batches(path, _mask())


def test_cli_emits_indexed_keys(tmp_path: Path) -> None:
    path = tmp_path / "cli.xlsx"
    _workbook(path)
    mask = tmp_path / "mask.json"
    mask.write_text(_mask().model_dump_json(by_alias=True))
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
