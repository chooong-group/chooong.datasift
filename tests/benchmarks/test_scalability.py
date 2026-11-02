"""Excel-scale inputs must produce exact counts across worksheet boundaries."""

import pytest

from tests.benchmarks.models import Case, Format
from tests.benchmarks.runner import Session

pytestmark = pytest.mark.benchmark


@pytest.mark.parametrize("format", list(Format))
@pytest.mark.parametrize("rows", [10_000, 100_000, 1_000_000, 2_000_000])
def test_scalability(benchmark_session: Session, format: Format, rows: int) -> None:
    case = Case(format=format, rows=rows)
    result = benchmark_session.measure(case)
    assert all(sample.matched == case.expected_matches for sample in result.candidate.samples)
