"""Reusable deterministic test fixtures."""

from __future__ import annotations

from pathlib import Path


def csv_sample(tmp_path: Path) -> Path:
    path = tmp_path / "input.csv"
    path.write_text('ID,Amount,Country\n1,"1.234,56",DE\n,"bad",AT\n3,,\n', encoding="utf-8")
    return path
