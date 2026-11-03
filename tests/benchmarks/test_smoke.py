"""Small functional checks for the benchmark generator and measurement path."""

import json
from pathlib import Path

import pytest

from tests.benchmarks.generate import generate
from tests.benchmarks.models import Case, Filter, Format, Mode
from tests.benchmarks.worker import measure


@pytest.mark.parametrize("format", list(Format))
@pytest.mark.parametrize("filter", [Filter.MONEY, Filter.VALIDATION])
def test_generated_data_is_reproducible_and_measured_results_are_exact(
    tmp_path: Path,
    format: Format,
    filter: Filter,
) -> None:
    case = Case(format=format, filter=filter, rows=20, hit_percent=50, mode=Mode.NDJSON)
    first = tmp_path / f"first.{format}"
    second = tmp_path / f"second.{format}"
    generate(first, case)
    generate(second, case)
    assert first.read_bytes() == second.read_bytes()
    result = measure(case, first, tmp_path / "matched.ndjson")
    assert result.matched == case.expected_matches
    assert result.matched + result.rejected == case.rows
    rows = [json.loads(line) for line in (tmp_path / "matched.ndjson").read_text().splitlines()]
    expected_count = 18 if filter == Filter.VALIDATION else 20
    assert [row["ID"] for row in rows] == [f"row-{index}" for index in range(expected_count)]
    assert all(row["Country"] == "DE" for row in rows)
    if filter == Filter.MONEY:
        assert rows[0]["Amount"] == {"type": "money", "amount": "1825.50", "currency": "EUR"}
    else:
        assert rows[0]["Amount"] == {"type": "decimal", "value": "0.00"}
        rejected = [
            json.loads(line) for line in (tmp_path / "rejected.ndjson").read_text().splitlines()
        ]
        assert [entry["reasons"][0]["code"] for entry in rejected] == [
            "CONVERSION_FAILED",
            "REQUIRED_MISSING",
        ]
    with pytest.raises(FileExistsError):
        generate(first, case)
