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
        "sheet": "Daten",
        "where": {
            "all": [
                {"column": "Kunde", "op": "starts_with", "value": "ABC"},
                {"column": "Land", "op": "eq", "value": "DE"},
                {"column": "Umsatz", "op": "gte", "value": 1000},
                {
                    "any": [
                        {"column": "Status", "op": "eq", "value": "Aktiv"},
                        {"column": "Status", "op": "eq", "value": "Offen"},
                    ]
                },
            ]
        },
    }


@pytest.fixture
def csv_file(tmp_path: Path) -> Path:
    return csv_sample(tmp_path)
