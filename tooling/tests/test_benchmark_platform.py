"""Compare the measured interpreters' architecture, including translated binaries."""

import json
import subprocess
from pathlib import Path

import pytest

from release.shared import git
from tests.benchmarks import runner


def test_baseline_from_another_interpreter_architecture_is_rejected(
    release_checkout: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = tmp_path / "candidate-python"
    baseline = tmp_path / "baseline-python"
    original = subprocess.check_output

    def probe(
        command: list[str],
        *,
        cwd: Path | None = None,
        text: bool = False,
    ) -> bytes | str:
        if command[0] in {str(candidate), str(baseline)}:
            assert command[1] == "-I"
            result = json.dumps(
                {
                    "python": "3.13.15",
                    "system": "Darwin",
                    "machine": "arm64" if command[0] == str(candidate) else "x86_64",
                    "native_origin": "lib/python3.13/site-packages/chooong/datasift/rust.abi3.so",
                }
            )
            return result if text else result.encode()
        return original(command, cwd=cwd, text=text)

    commit = git(release_checkout, "rev-parse", "HEAD")
    monkeypatch.setattr(runner, "ROOT", release_checkout)
    monkeypatch.setattr(subprocess, "check_output", probe)
    with pytest.raises(ValueError, match="same OS, architecture and Python"):
        runner.Session(tmp_path / "measurements", candidate, baseline, commit)
    assert not (tmp_path / "measurements").exists()
