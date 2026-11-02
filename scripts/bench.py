"""Run the single benchmark implementation in tests/benchmarks."""

import subprocess
import sys

if __name__ == "__main__":
    raise SystemExit(
        subprocess.call(
            [sys.executable, "-m", "pytest", "tests/benchmarks/", "-m", "benchmark", *sys.argv[1:]]
        )
    )
