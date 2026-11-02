"""Throughput sweeps keep data size fixed while varying selectivity and batches."""

import pytest

from tests.benchmarks.models import Case, Format
from tests.benchmarks.runner import Session

pytestmark = pytest.mark.benchmark


@pytest.mark.parametrize("format", list(Format))
@pytest.mark.parametrize("hit_percent", [0, 5, 50, 100])
@pytest.mark.parametrize("batch_size", [64, 1024, 65536])
def test_throughput(
    benchmark_session: Session, format: Format, hit_percent: int, batch_size: int
) -> None:
    case = Case(format=format, hit_percent=hit_percent, batch_size=batch_size)
    result = benchmark_session.measure(case)
    assert all(sample.matched == case.expected_matches for sample in result.candidate.samples)
    assert len({sample.input_sha256 for sample in result.candidate.samples}) == 1
