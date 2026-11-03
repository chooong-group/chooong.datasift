"""Expose native-bridge overhead and comparable baseline/candidate samples."""

import pytest

from tests.benchmarks.models import Case, Format, Mode
from tests.benchmarks.runner import Session

pytestmark = pytest.mark.benchmark


@pytest.mark.parametrize("format", list(Format))
def test_native_boundary(benchmark_session: Session, format: Format) -> None:
    native = benchmark_session.measure(Case(format=format, mode=Mode.NATIVE))
    public = benchmark_session.measure(Case(format=format))
    assert native.candidate.samples[0].matched == public.candidate.samples[0].matched
    if native.baseline is not None:
        assert all(
            sample.matched == native.case.expected_matches for sample in native.baseline.samples
        )
