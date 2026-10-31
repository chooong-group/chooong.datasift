"""Stream XLSX matches; all row-level predicate evaluations run in native Rust."""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

from . import _rust

__all__ = ["iter_matching_batches", "iter_matching_rows"]


def _mask_json(mask: Mapping[str, Any] | str | Path) -> str:
    if isinstance(mask, Path):
        return mask.read_text(encoding="utf-8")
    if isinstance(mask, str):
        if mask.lstrip().startswith("{"):
            return mask
        return Path(mask).read_text(encoding="utf-8")
    if isinstance(mask, Mapping):
        return json.dumps(dict(mask), ensure_ascii=False, allow_nan=False)
    raise TypeError("mask muss dict, JSON-Text oder Pfad zu einer JSON-Datei sein")


def iter_matching_batches(
    xlsx_path: str | Path,
    mask: Mapping[str, Any] | str | Path,
    *,
    batch_size: int = 1024,
) -> Iterator[list[dict[str, Any]]]:
    """Return a native Rust iterator of matching-row batches, without loading a sheet.

    Caller may call `.close()` on the returned iterator to stop a long scan early.
    Date cells containing Excel serials are returned as numeric serials, not dates.
    Formula cells use cached values stored by the XLSX producer.
    """
    return _rust.iter_batches(str(xlsx_path), _mask_json(mask), batch_size)


def iter_matching_rows(
    xlsx_path: str | Path,
    mask: Mapping[str, Any] | str | Path,
    *,
    batch_size: int = 1024,
) -> Iterator[dict[str, Any]]:
    """Yield matching row dicts, flattening native batches lazily."""
    batches = iter_matching_batches(xlsx_path, mask, batch_size=batch_size)
    try:
        for batch in batches:
            yield from batch
    finally:
        batches.close()
