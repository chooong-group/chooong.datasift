"""Reusable deterministic test fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.fixtures.csv import csv_sample
from tests.fixtures.excel import make_workbook


@pytest.fixture
def xlsx(tmp_path: Path) -> Path:
    file = tmp_path / "sample.xlsx"
    make_workbook(file)
    return file


@pytest.fixture
def mask() -> dict[str, object]:
    return {
        "sheet": "Data",
        "where": {
            "all": [
                {"column": "Customer", "op": "starts_with", "value": "ABC"},
                {"column": "Country", "op": "eq", "value": "DE"},
                {"column": "Revenue", "op": "gte", "value": 1000},
                {
                    "any": [
                        {"column": "Status", "op": "eq", "value": "Active"},
                        {"column": "Status", "op": "eq", "value": "Open"},
                    ]
                },
            ]
        },
    }


@pytest.fixture
def csv_file(tmp_path: Path) -> Path:
    return csv_sample(tmp_path)
