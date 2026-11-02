"""Public contract checks using real synthetic files."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from chooong.datasift import (
    FilterMask,
    iter_matching_batches,
)
from tests.fixtures.excel import make_workbook
from tests.fixtures.masks import contract_mask, pipeline_mask


def test_typed_models_roundtrip_and_immutable_rows(tmp_path: Path) -> None:
    path = tmp_path / "sample.xlsm"
    make_workbook(path)
    mask = FilterMask.model_validate_json(contract_mask().model_dump_json(by_alias=True))
    with iter_matching_batches(path, mask, batch_size=2) as batches:
        rows = [row for batch in batches for row in batch]
    assert len(rows) == 6
    assert rows[0]["Country"] == "DE"
    assert tuple(rows[0]) == ("Customer", "Country", "Status")
    assert len(rows[0]) == 3
    assert not list(batches)
    with pytest.raises(TypeError):
        rows[0].cells["Customer"] = "changed"


@pytest.mark.parametrize("batch_size", [0, -1, 65537, True, 1.5])
def test_invalid_batches_fail_before_io(batch_size: object) -> None:
    with pytest.raises(ValueError, match="batch_size"):
        iter_matching_batches("missing.xlsx", contract_mask(), batch_size=batch_size)


@pytest.mark.parametrize(
    "updates",
    [
        {"sheet": " "},
        {"header_row": True},
        {"unknown": 1},
        {"where": {"column": "Country", "op": "unknown", "value": "DE"}},
        {"where": {"column": "Country", "op": "is_empty", "value": None}},
        {"where": {"column": "Revenue", "op": "gte", "value": True}},
        {"where": {"column": "Revenue", "op": "eq", "value": float("nan")}},
    ],
)
def test_untrusted_masks_fail_closed(updates: dict[str, object]) -> None:
    payload = contract_mask().model_dump(by_alias=True)
    payload.update(updates)
    with pytest.raises(ValidationError):
        iter_matching_batches("missing.xlsx", payload)


@pytest.mark.parametrize("group", ["conditions", "condition"])
def test_python_field_names_are_not_wire_aliases(group: str) -> None:
    predicate = {"column": "Country", "op": "eq", "value": "DE"}
    payload = {"sheet": "Data", "where": {group: [predicate]}}
    with pytest.raises(ValidationError):
        iter_matching_batches("missing.xlsx", payload)
    with pytest.raises(ValidationError):
        iter_matching_batches("missing.xlsx", json.dumps(payload))


@pytest.mark.parametrize(
    "condition",
    [
        {"column": "UNKNOWN", "op": "eq", "value": "hello"},
        {"column": "Revenue", "op": "gte", "value": "1000"},
        {"column": "Customer", "op": "regex", "value": "("},
        {"any": []},
        {"column": "Customer", "op": "contains", "value": "ABC", "evil": "bad"},
    ],
)
def test_mask_errors_are_eager(xlsx: Path, condition: dict) -> None:
    with pytest.raises(ValueError, match=".+"):
        iter_matching_batches(xlsx, {"sheet": "Data", "where": condition})


def test_full_model_contract_roundtrip() -> None:
    spec = FilterMask.model_validate(pipeline_mask())
    assert FilterMask.model_validate_json(spec.model_dump_json()) == spec
