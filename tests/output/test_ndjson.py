"""Public contract checks using real synthetic files."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from chooong.datasift import (
    export,
)
from tests.fixtures.masks import (
    pipeline_mask,
)


def test_native_exports_one_scan_and_replay_preserves_failed_outputs(
    csv_file: Path, tmp_path: Path
) -> None:
    path = csv_file
    matched = tmp_path / "matched.ndjson"
    rejected = tmp_path / "rejected.ndjson"
    stats = export(path, pipeline_mask(), matched, rejected_output=rejected, batch_size=1)
    assert (stats.matched, stats.rejected) == (2, 1)
    assert len(matched.read_text().splitlines()) == 2
    assert json.loads(rejected.read_text())["values"]["Amount"] == "bad"
    previous = (matched.read_bytes(), rejected.read_bytes())
    bad = tmp_path / "broken.xlsx"
    bad.write_bytes(b"broken")
    with pytest.raises(RuntimeError):
        export([path, bad], pipeline_mask(), matched, rejected_output=rejected)
    assert (matched.read_bytes(), rejected.read_bytes()) == previous
    export(path, pipeline_mask(), matched, rejected_output=rejected)
    assert (matched.read_bytes(), rejected.read_bytes()) == previous
    assert not list(tmp_path.glob("*.tmp"))


def test_export_preserves_mask_path_and_hardlink_alias(csv_file: Path, tmp_path) -> None:
    path = csv_file
    mask = tmp_path / "mask.json"
    mask.write_text(json.dumps(pipeline_mask()))
    alias = tmp_path / "alias.json"
    alias.hardlink_to(mask)
    original = mask.read_bytes()
    for destination in (mask, alias):
        with pytest.raises(ValueError, match="Filterdatei"):
            export(path, mask, destination)
    assert mask.read_bytes() == original


def test_schema_errors_never_commit_either_export(tmp_path: Path) -> None:
    path = tmp_path / "bad.csv"
    path.write_text("A,B\na,1\n")
    output = tmp_path / "matches.parquet"
    rejected = tmp_path / "rejects.ndjson"
    output.write_bytes(b"previous matches")
    rejected.write_bytes(b"previous rejects")
    with pytest.raises(RuntimeError, match="SCHEMA_MISMATCH"):
        export(path, {"sheet": None, "select": ["missing"]}, output, rejected_output=rejected)
    assert output.read_bytes() == b"previous matches"
    assert rejected.read_bytes() == b"previous rejects"
