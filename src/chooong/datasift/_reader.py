"""File/native adapter; predicates and rejected rows stay in Rust."""

from collections.abc import Generator, Iterator, Mapping
from pathlib import Path
from types import TracebackType
from typing import Self

from . import _rust
from ._models import FilterMask, Row

MaskInput = FilterMask | Mapping[str, object] | str | Path
MAX_BATCH_SIZE = 65536
DEFAULT_BATCH_SIZE = 1024


def _load_mask(mask: MaskInput) -> FilterMask:
    if isinstance(mask, FilterMask):
        # Validate again: model_construct/model_copy can bypass model validation.
        return FilterMask.model_validate_json(mask.model_dump_json(by_alias=True))
    if isinstance(mask, Mapping):
        return FilterMask.model_validate(mask, by_name=False)
    if isinstance(mask, Path):
        return FilterMask.model_validate_json(mask.read_text(encoding="utf-8"), by_name=False)
    if mask.lstrip().startswith("{"):
        return FilterMask.model_validate_json(mask, by_name=False)
    return FilterMask.model_validate_json(Path(mask).read_text(encoding="utf-8"), by_name=False)


class BatchIterator(Iterator[list[Row]]):
    """Closeable native scan; use as context manager when stopping early."""

    def __init__(self, native: _rust.BatchIterator) -> None:
        self._native = native

    def __iter__(self) -> Self:
        return self

    def __next__(self) -> list[Row]:
        return [Row(cells) for cells in next(self._native)]

    def close(self) -> None:
        self._native.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()


def iter_matching_batches(
    xlsx_path: str | Path,
    mask: MaskInput,
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> BatchIterator:
    """Validate the mask/header eagerly, then stream matching batches."""
    if isinstance(batch_size, bool) or not isinstance(batch_size, int):
        raise ValueError("batch_size muss eine Ganzzahl sein")
    if not 1 <= batch_size <= MAX_BATCH_SIZE:
        raise ValueError("batch_size muss zwischen 1 und 65536 liegen")
    spec = _load_mask(mask)
    return BatchIterator(
        _rust.iter_batches(str(xlsx_path), spec.model_dump_json(by_alias=True), batch_size)
    )


def iter_matching_rows(
    xlsx_path: str | Path,
    mask: MaskInput,
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> Generator[Row]:
    """Yield matches; closing the generator cancels its underlying scan."""
    with iter_matching_batches(xlsx_path, mask, batch_size=batch_size) as batches:
        for batch in batches:
            yield from batch
