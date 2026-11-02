"""Compare the measured interpreters' architecture, including translated binaries."""

from pathlib import Path

import pytest

from release.shared import git
from scripts.artifacts import Machine, Probe, System
from tests.benchmarks import runner


def test_baseline_from_another_interpreter_architecture_is_rejected(
    release_checkout: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = tmp_path / "candidate-python"
    baseline = tmp_path / "baseline-python"

    def probe(executable: Path) -> Probe:
        assert executable in {candidate, baseline}
        return Probe(
            python="3.13.15",
            system=System.MACOS,
            machine=Machine.ARM if executable == candidate else Machine.X86,
            native_origin="lib/python3.13/site-packages/chooong/datasift/rust.abi3.so",
        )

    commit = git(release_checkout, "rev-parse", "HEAD")
    monkeypatch.setattr(runner, "ROOT", release_checkout)
    monkeypatch.setattr(runner, "probe_interpreter", probe)
    with pytest.raises(ValueError, match="same OS, architecture and Python"):
        runner.Session(tmp_path / "measurements", candidate, baseline, commit)
    assert not (tmp_path / "measurements").exists()
