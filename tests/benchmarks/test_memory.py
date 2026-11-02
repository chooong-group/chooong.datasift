"""Reuse the scaling samples to report RSS growth without timing thresholds."""

import struct

import pytest

from tests.benchmarks.models import Case, Format
from tests.benchmarks.runner import Session

pytestmark = pytest.mark.benchmark


@pytest.mark.parametrize("format", list(Format))
def test_streaming_memory(benchmark_session: Session, format: Format) -> None:
    small = benchmark_session.measure(Case(format=format, rows=10_000))
    large = benchmark_session.measure(Case(format=format, rows=2_000_000))
    # Every input row would require at least one pointer if the complete input
    # table were retained. These generated files contain no shared-string table.
    # Compare observed ranges, allowing the measured small-run RSS variation.
    large_rss = min(sample.peak_rss_bytes for sample in large.candidate.samples)
    small_rss = max(sample.peak_rss_bytes for sample in small.candidate.samples)
    pointer_bytes = struct.calcsize("P")
    assert large_rss - small_rss < large.case.rows * pointer_bytes, (
        "RSS growth exceeds the minimum storage for materialized input-row pointers; "
        "inspect the raw samples for a streaming regression"
    )
