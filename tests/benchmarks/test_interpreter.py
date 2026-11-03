"""Benchmark environment measurements use the selected interpreter."""

import platform
import sys
from pathlib import Path

import pytest

from tests.benchmarks.models import Interpreter
from tests.benchmarks.runner import probe_interpreter


@pytest.mark.parametrize(
    ("machine", "expected"),
    [("AMD64", "x86_64"), ("x86_64", "x86_64"), ("aarch64", "arm64"), ("arm64", "arm64")],
)
def test_machine_aliases(machine: str, expected: str) -> None:
    measured = Interpreter(
        python="3.13.0", system="Linux", machine=machine, native_origin="rust.abi3.so"
    )
    assert measured.machine == expected


def test_probe_installed_native_interpreter() -> None:
    measured = probe_interpreter(Path(sys.executable))
    assert measured.python == platform.python_version()
    assert measured.system == platform.system()
    assert Path(measured.native_origin).is_file()
    assert measured.native_origin.endswith((".so", ".pyd"))
