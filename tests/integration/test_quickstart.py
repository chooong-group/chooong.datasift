"""Run the documented offset-table example through both public entry points."""

import json
import subprocess
import sys
from pathlib import Path

from chooong.datasift import (
    AllOf,
    FilterMask,
    NumericCondition,
    Operator,
    ScalarCondition,
    iter_matching_rows,
)
from tests.fixtures.excel import Sheet, worksheet_rows, write_book


def test_quickstart(tmp_path: Path) -> None:
    path = tmp_path / "sample.xlsx"
    write_book(
        path,
        Sheet(
            "Data",
            worksheet_rows(
                [
                    ("Synthetic report",),
                    (),
                    (),
                    (
                        None,
                        None,
                        "Country",
                        "Amount",
                        "Note",
                        None,
                        None,
                        "Country",
                        "Amount",
                        "Note",
                    ),
                    (
                        None,
                        None,
                        "Amounts pending review",
                        None,
                        None,
                        None,
                        None,
                        "Includes estimates",
                    ),
                    (None, None, "DE", 1500, "Provisional", None, None, "DE", 2400, "Approved"),
                    (None, None, "AT", 2000, None, None, None, "DE", 900),
                ]
            ),
        ),
    )
    before = path.read_bytes()
    mask = FilterMask(
        sheet=None,
        where=AllOf(
            conditions=(
                ScalarCondition(column="Country", op=Operator.EQ, value="DE"),
                NumericCondition(column="Amount", op=Operator.GTE, value=1000),
            )
        ),
    )
    expected = [{"Country": "DE", "Amount": 1500}, {"Country": "DE", "Amount": 2400}]
    assert [dict(row) for row in iter_matching_rows(path, mask)] == expected
    mask_path = tmp_path / "filter.json"
    mask_path.write_text(mask.model_dump_json(by_alias=True), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "-m", "chooong.datasift", str(path), str(mask_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    assert [json.loads(line) for line in result.stdout.splitlines()] == expected
    assert path.read_bytes() == before
