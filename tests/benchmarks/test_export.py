"""Measure native exports while checking matched/rejected conservation."""

import pytest

from tests.benchmarks.models import Case, Filter, Format, Mode
from tests.benchmarks.runner import Session

pytestmark = pytest.mark.benchmark


@pytest.mark.parametrize("format", list(Format))
@pytest.mark.parametrize("mode", [Mode.NDJSON, Mode.PARQUET])
def test_export(benchmark_session: Session, format: Format, mode: Mode) -> None:
    case = Case(format=format, mode=mode, filter=Filter.MONEY)
    result = benchmark_session.measure(case)
    assert all(sample.matched + sample.rejected == case.rows for sample in result.candidate.samples)
