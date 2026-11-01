"""Run the dirty-workbook quickstart through the public API."""

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


def test_dirty_quickstart_extracts_matching_columns_from_both_tables(tmp_path: Path) -> None:
    workbook = tmp_path / "sample.xlsx"
    script = Path(__file__).resolve().parents[1] / "examples/create_sample.py"
    subprocess.run([sys.executable, str(script), str(workbook), "--dirty"], check=True)
    mask = FilterMask(
        sheet=None,
        where=AllOf(
            conditions=(
                ScalarCondition(column="Country", op=Operator.EQ, value="DE"),
                NumericCondition(column="Amount", op=Operator.GTE, value=1000),
            )
        ),
    )
    assert [dict(row) for row in iter_matching_rows(workbook, mask)] == [
        {"Country": "DE", "Amount": 1500},
        {"Country": "DE", "Amount": 2400},
    ]
