"""Public contract checks using real synthetic files."""

from __future__ import annotations

from pathlib import Path

from chooong.datasift import (
    iter_matching_rows,
)
from tests.fixtures.masks import (
    pipeline_mask,
)


def test_exact_money_comparison_after_conversion_and_currency_mismatch(
    csv_file: Path, tmp_path: Path
) -> None:
    path = csv_file
    mask = pipeline_mask()
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


def test_money_currency_mismatch_cannot_pass_through_not(csv_file: Path, tmp_path) -> None:
    path = csv_file
    mask = pipeline_mask()
    mask["where"] = {
        "not": {
            "column": "Amount",
            "op": "eq",
            "value": {"type": "money", "amount": "1", "currency": "USD"},
        }
    }
    assert list(iter_matching_rows(path, mask)) == []
