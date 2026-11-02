"""Public contract checks using real synthetic files."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from chooong.datasift import (
    RecordKind,
    iter_matching_batches,
    iter_matching_rows,
    scan_batches,
)
from tests.fixtures.excel import make_workbook
from tests.fixtures.masks import contract_mask, pipeline_mask


def test_generator_close_and_replay_are_independent(tmp_path: Path) -> None:
    path = tmp_path / "sample.xlsx"
    make_workbook(path)
    rows = iter_matching_rows(path, contract_mask(), batch_size=1)
    first = next(rows)
    rows.close()
    assert list(rows) == []
    replay = list(iter_matching_rows(path, contract_mask()))
    assert first == replay[0]
    assert len(replay) == 6


def test_concurrent_scans_do_not_share_state(tmp_path: Path) -> None:
    path = tmp_path / "sample.xlsx"
    make_workbook(path)

    def scan(_: int) -> list[str | bool | int | float | None]:
        return [row["Kunde"] for row in iter_matching_rows(path, contract_mask(), batch_size=1)]

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(scan, range(8)))
    assert all(result == results[0] for result in results)
    assert len(results[0]) == 6


def test_iterator_can_move_between_threads(tmp_path: Path) -> None:
    path = tmp_path / "sample.xlsx"
    make_workbook(path)
    with iter_matching_batches(path, contract_mask(), batch_size=1) as batches:
        with ThreadPoolExecutor(max_workers=1) as pool:
            first = pool.submit(next, batches).result(timeout=10)
        assert first[0]["Kunde"] == "ABC GmbH"
        assert len([row for batch in batches for row in batch]) == 5


def test_close_stops_worker(xlsx: Path) -> None:
    mask = {"sheet": "Daten", "where": {"column": "Land", "op": "eq", "value": "DE"}}
    batches = iter_matching_batches(xlsx, mask)
    batches.close()
    assert list(batches) == []


def test_iterator_close_and_reject_opt_out(csv_file: Path, tmp_path: Path) -> None:
    path = csv_file
    with scan_batches(path, pipeline_mask(), rejected=False, batch_size=1) as batches:
        assert next(batches)[0].kind == RecordKind.MATCHED
        batches.close()
        assert list(batches) == []
    with iter_matching_batches(path, {"sheet": None}) as batches:
        list(batches)
        assert batches.statistics is not None
        assert batches.statistics.complete
