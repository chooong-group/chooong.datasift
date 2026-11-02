"""Reusable deterministic test fixtures."""

from __future__ import annotations

import json
from collections.abc import Mapping
from hashlib import sha256
from pathlib import Path

import pytest

from chooong.datasift import (
    ScanRecord,
    Statistics,
    scan_batches,
)


def partial_scan(
    path: Path, mask: Mapping[str, object], batch_size: int
) -> tuple[list[ScanRecord], Statistics]:
    records: list[ScanRecord] = []
    with scan_batches(path, mask, batch_size=batch_size) as batches:
        with pytest.raises(RuntimeError, match="SCHEMA_MISMATCH"):
            records.extend(record for batch in batches for record in batch)
        statistics = batches.statistics
    assert statistics is not None
    assert not statistics.complete
    return records, statistics


def recovery_journal(tmp_path: Path) -> tuple[Path, Path, Path, str]:
    output = tmp_path / "matched.ndjson"
    stage = tmp_path / ".matched.ndjson.datasift-1-0.tmp"
    journal = tmp_path / ".matched.ndjson.datasift-commit.json"
    output.write_bytes(b"old")
    stage.write_bytes(b"new")
    journal.write_text(
        json.dumps(
            {
                "version": 1,
                "entries": [
                    {
                        "destination": str(output),
                        "stage": str(stage),
                        "sha256": sha256(b"new").hexdigest(),
                    }
                ],
            }
        )
    )
    return output, stage, journal, sha256(journal.read_bytes()).hexdigest()
