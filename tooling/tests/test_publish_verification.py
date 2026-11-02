"""Release safety contracts using synthetic evidence, never platform claims."""

import subprocess
import sys

import pytest

from tooling.tests.fixtures import REPO, SyntheticBundle, _gate, _sha


@pytest.mark.parametrize("tamper", ["dist", "checksums", "extra", "missing"])
def test_publish_verifier_blocks_changes_after_the_final_gate(
    synthetic_bundle: SyntheticBundle,
    tamper: str,
) -> None:
    bundle = synthetic_bundle
    assert _gate(bundle).returncode == 0
    expected = _sha(bundle.output / "SHA256SUMS")
    command = [
        sys.executable,
        str(REPO / "scripts/verify_publish.py"),
        str(bundle.output),
        expected,
    ]
    assert subprocess.run(command, check=False).returncode == 0
    artifact = next((bundle.output / "dist").iterdir())
    if tamper == "dist":
        artifact.write_bytes(b"changed")
    elif tamper == "checksums":
        (bundle.output / "SHA256SUMS").write_text("changed")
    elif tamper == "extra":
        (bundle.output / "dist" / "extra.whl").write_bytes(b"extra")
    else:
        artifact.unlink()
    assert subprocess.run(command, capture_output=True, check=False).returncode != 0
