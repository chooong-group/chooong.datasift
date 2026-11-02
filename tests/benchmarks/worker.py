"""One isolated, measured scan. Never generate input inside this process."""

import argparse
import ctypes
import hashlib
import platform
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from chooong.datasift import (
    FilterMask,
    RecordKind,
    Statistics,
    export,
    iter_matching_batches,
    rust,
    scan_batches,
)
from tests.benchmarks.models import Case, Filter, Measurement, Mode

PROCESS_STARTED = time.perf_counter()


if sys.platform == "win32":

    class _MemoryCounters(ctypes.Structure):
        _fields_ = [
            ("cb", ctypes.c_ulong),
            ("page_faults", ctypes.c_ulong),
            ("peak_working_set", ctypes.c_size_t),
            ("working_set", ctypes.c_size_t),
            ("quota_peak_paged", ctypes.c_size_t),
            ("quota_paged", ctypes.c_size_t),
            ("quota_peak_nonpaged", ctypes.c_size_t),
            ("quota_nonpaged", ctypes.c_size_t),
            ("pagefile", ctypes.c_size_t),
            ("peak_pagefile", ctypes.c_size_t),
        ]

    def peak_rss() -> int:
        counters = _MemoryCounters()
        counters.cb = ctypes.sizeof(counters)
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        process = kernel.GetCurrentProcess
        process.restype = ctypes.c_void_p
        memory = ctypes.WinDLL("psapi", use_last_error=True).GetProcessMemoryInfo
        memory.argtypes = [ctypes.c_void_p, ctypes.POINTER(_MemoryCounters), ctypes.c_ulong]
        memory.restype = ctypes.c_int
        if not memory(process(), ctypes.byref(counters), counters.cb):
            raise ctypes.WinError(ctypes.get_last_error())
        return int(counters.peak_working_set)
else:
    import resource

    def peak_rss() -> int:
        value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return int(value if platform.system() == "Darwin" else value * 1024)


def mask(case: Case) -> FilterMask:
    predicate: dict[str, object] = {"column": "Country", "op": "eq", "value": "DE"}
    if case.filter == Filter.LOGIC:
        predicate = {
            "all": [
                {"any": [{"column": "Country", "op": "eq", "value": "XX"}, predicate]},
                {"not": {"column": "ID", "op": "starts_with", "value": "never-"}},
            ]
        }
    elif case.filter == Filter.REGEX:
        predicate = {"column": "Country", "op": "regex", "value": "^DE$"}
    config: dict[str, object] = {
        "sheet": None,
        "header": {"anchors": ["ID", "Amount", "Country"]},
        "select": ["ID", "Amount", "Country"],
        "where": predicate,
    }
    if case.filter in {Filter.DECIMAL, Filter.MONEY, Filter.VALIDATION}:
        kind = "money" if case.filter == Filter.MONEY else "decimal"
        config["types"] = {
            "Amount": {
                "type": kind,
                "convert": True,
                **({"currency": "EUR"} if kind == "money" else {}),
            }
        }
    if case.filter == Filter.VALIDATION:
        config["required"] = ["ID", "Amount"]
        config["defaults"] = {"Amount": "0.00"}
    return FilterMask.model_validate(config)


@dataclass(frozen=True, slots=True)
class ScanCounts:
    matched: int
    rejected: int
    statistics: Statistics | None


def _events(case: Case, input_path: Path, spec: FilterMask) -> ScanCounts:
    matched = rejected = 0
    with scan_batches(input_path, spec, batch_size=case.batch_size) as batches:
        for batch in batches:
            for record in batch:
                if record.kind == RecordKind.MATCHED:
                    matched += 1
                else:
                    rejected += 1
        return ScanCounts(matched, rejected, batches.statistics)


def _native(case: Case, input_path: Path, spec: FilterMask) -> ScanCounts:
    batches = rust.iter_json(
        [str(input_path)], spec.model_dump_json(by_alias=True), case.batch_size
    )
    try:
        count = sum(len(batch) for batch in batches)
        raw = batches.statistics_json()
        stats = Statistics.model_validate_json(raw) if raw is not None else None
        return ScanCounts(count, 0, stats)
    finally:
        batches.close()


def _rows(case: Case, input_path: Path, spec: FilterMask) -> ScanCounts:
    with iter_matching_batches(input_path, spec, batch_size=case.batch_size) as batches:
        count = sum(len(batch) for batch in batches)
        return ScanCounts(count, 0, batches.statistics)


def measure(case: Case, input_path: Path, output: Path) -> Measurement:
    spec = mask(case)
    started = time.perf_counter()
    if case.mode in {Mode.NDJSON, Mode.PARQUET}:
        exported = export(
            input_path,
            spec,
            output,
            rejected_output=output.with_name("rejected" + output.suffix),
            batch_size=case.batch_size,
        )
        counts = ScanCounts(exported.matched, exported.rejected, exported)
    elif case.mode == Mode.EVENTS:
        counts = _events(case, input_path, spec)
    elif case.mode == Mode.NATIVE:
        counts = _native(case, input_path, spec)
    else:
        counts = _rows(case, input_path, spec)
    seconds = time.perf_counter() - started
    count, rejected, stats = counts.matched, counts.rejected, counts.statistics
    rss = peak_rss()
    if stats is None or not stats.complete or count != case.expected_matches:
        raise ValueError(f"Incorrect benchmark result: {count}, expected {case.expected_matches}")
    if case.mode in {Mode.EVENTS, Mode.NDJSON, Mode.PARQUET} and rejected != case.rows - count:
        raise ValueError("Incorrect rejected count")
    if case.mode == Mode.NDJSON:
        with output.open() as stream:
            if sum(1 for _ in stream) != count:
                raise ValueError("Incorrect NDJSON output count")
    if case.mode == Mode.PARQUET:
        with output.open("rb") as stream:
            if stream.read(4) != b"PAR1":
                raise ValueError("Invalid Parquet output")
    with input_path.open("rb") as stream:
        sha256 = hashlib.file_digest(stream, "sha256").hexdigest()
    return Measurement(
        scan_seconds=seconds,
        pre_scan_seconds=started - PROCESS_STARTED,
        process_seconds=seconds,
        peak_rss_bytes=rss,
        matched=count,
        rejected=stats.rejected,
        rust_scan_seconds=stats.seconds,
        input_sha256=sha256,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case")
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = measure(Case.model_validate_json(args.case), args.input, args.output)
    sys.stdout.write(result.model_dump_json() + "\n")


if __name__ == "__main__":
    main()
