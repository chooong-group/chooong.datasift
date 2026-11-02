"""Benchmarks are explicit opt-in and run outside the pytest process."""

import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from tests.benchmarks.models import BuildProfile
from tests.benchmarks.runner import Session


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption("--benchmark-output", type=Path, default=Path("benchmark-results"))
    parser.addoption("--benchmark-python", type=Path, default=Path(sys.executable))
    parser.addoption("--benchmark-baseline-python", type=Path)
    parser.addoption("--benchmark-baseline-ref")
    parser.addoption(
        "--benchmark-build-profile", choices=list(BuildProfile), default=BuildProfile.UNKNOWN
    )


@pytest.fixture(scope="session")
def benchmark_session(request: pytest.FixtureRequest) -> Iterator[Session]:
    session = Session(
        directory=request.config.getoption("--benchmark-output").resolve(),
        candidate=request.config.getoption("--benchmark-python").absolute(),
        baseline=request.config.getoption("--benchmark-baseline-python"),
        baseline_ref=request.config.getoption("--benchmark-baseline-ref"),
        profile=BuildProfile(request.config.getoption("--benchmark-build-profile")),
    )
    yield session
    session.write(complete=request.session.testsfailed == 0)
