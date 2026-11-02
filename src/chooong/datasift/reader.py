"""File/native adapter; predicates and rejected rows stay in Rust."""

from collections.abc import Generator, Iterator, Mapping, Sequence
from pathlib import Path
from types import TracebackType
from typing import Self

from chooong.datasift import rust
from chooong.datasift.models import FilterMask, Row, ScanRecord, Statistics

MaskInput = FilterMask | Mapping[str, object] | str | Path
MAX_BATCH_SIZE = 65536
DEFAULT_BATCH_SIZE = 1024
PathInput = str | Path | Sequence[str | Path]


def _paths(paths: PathInput) -> list[str]:
    return [str(paths)] if isinstance(paths, (str, Path)) else [str(path) for path in paths]


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

    def __init__(self, native: rust.BatchIterator) -> None:
        self._native = native

    def __iter__(self) -> Self:
        return self

    def __next__(self) -> list[Row]:
        return [Row(cells) for cells in next(self._native)]

    @property
    def statistics(self) -> Statistics | None:
        value = self._native.statistics_json()
        return Statistics.model_validate_json(value) if value is not None else None

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
    xlsx_path: PathInput,
    mask: MaskInput,
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> BatchIterator:
    """Validate the mask eagerly; all-sheet schemas resolve during iteration."""
    _validate_batch_size(batch_size)
    spec = _load_mask(mask)
    return BatchIterator(
        rust.iter_many(_paths(xlsx_path), spec.model_dump_json(by_alias=True), batch_size)
    )


def iter_matching_rows(
    xlsx_path: PathInput,
    mask: MaskInput,
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> Generator[Row, None, None]:
    """Yield matches; closing the generator cancels its underlying scan."""
    with iter_matching_batches(xlsx_path, mask, batch_size=batch_size) as batches:
        for batch in batches:
            yield from batch


class ScanIterator(Iterator[list[ScanRecord]]):
    """A single backpressured stream; consume matched and rejected records together."""

    def __init__(self, native: rust.EventIterator) -> None:
        self._native = native

    def __iter__(self) -> Self:
        return self

    def __next__(self) -> list[ScanRecord]:
        return [ScanRecord.model_validate_json(value) for value in next(self._native)]

    @property
    def statistics(self) -> Statistics | None:
        value = self._native.statistics_json()
        return Statistics.model_validate_json(value) if value is not None else None

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


def scan_batches(
    paths: PathInput,
    mask: MaskInput,
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
    rejected: bool = True,
) -> ScanIterator:
    spec = _load_mask(mask)
    _validate_batch_size(batch_size)
    return ScanIterator(
        rust.iter_events(_paths(paths), spec.model_dump_json(by_alias=True), batch_size, rejected)
    )


def _validate_batch_size(batch_size: int) -> None:
    if isinstance(batch_size, bool) or not isinstance(batch_size, int):
        raise ValueError("batch_size muss eine Ganzzahl sein")
    if not 1 <= batch_size <= MAX_BATCH_SIZE:
        raise ValueError("batch_size muss zwischen 1 und 65536 liegen")


def export(
    paths: PathInput,
    mask: MaskInput,
    output: str | Path,
    *,
    rejected_output: str | Path | None = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> Statistics:
    """Write native NDJSON/Parquet streams; suffix .parquet selects Parquet."""
    _validate_mask_outputs(mask, (output, rejected_output))
    spec = _load_mask(mask)
    _validate_batch_size(batch_size)
    value = rust.export(
        _paths(paths),
        spec.model_dump_json(by_alias=True),
        str(output),
        str(rejected_output) if rejected_output is not None else None,
        batch_size,
    )
    return Statistics.model_validate_json(value)


def recover_export(
    output: str | Path, *, journal_sha256: str, rejected_output: str | Path | None = None
) -> None:
    """Recover only caller-authorized destinations and an independently trusted journal digest."""
    rust.recover_export(
        str(output),
        journal_sha256,
        str(rejected_output) if rejected_output is not None else None,
    )


def _validate_mask_outputs(mask: MaskInput, destinations: tuple[str | Path | None, ...]) -> None:
    if isinstance(mask, (FilterMask, Mapping)):
        return
    if isinstance(mask, str) and mask.lstrip().startswith("{"):
        return
    source = Path(mask)
    for destination in destinations:
        if destination is None:
            continue
        path = Path(destination)
        if path.resolve() == source.resolve() or (
            path.exists() and source.exists() and path.samefile(source)
        ):
            raise ValueError("Ausgabe darf die Filterdatei nicht überschreiben")
