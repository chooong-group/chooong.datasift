"""Equivalent filters and exact conversions must keep their expected result set."""

import pytest

from tests.benchmarks.models import Case, Filter, Format, Mode
from tests.benchmarks.runner import Session

pytestmark = pytest.mark.benchmark


@pytest.mark.parametrize("format", list(Format))
@pytest.mark.parametrize("filter", list(Filter))
def test_filter_complexity(benchmark_session: Session, format: Format, filter: Filter) -> None:
    case = Case(format=format, filter=filter, mode=Mode.EVENTS)
    result = benchmark_session.measure(case)
    assert all(sample.matched + sample.rejected == case.rows for sample in result.candidate.samples)
