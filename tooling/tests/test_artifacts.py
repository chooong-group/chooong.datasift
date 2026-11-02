"""Release safety contracts using synthetic evidence, never platform claims."""

import io
import json
import tarfile
from pathlib import Path

import pytest

from tooling.tests.fixtures import (
    SyntheticBundle,
    _change_archive,
    _change_receipt,
    _change_report,
    _gate,
    _sha,
    _write_json,
)


def test_gate_accepts_complete_consistent_synthetic_evidence_without_rebuilding(
    synthetic_bundle: SyntheticBundle,
) -> None:
    bundle = synthetic_bundle
    original = {path.name: _sha(path) for path in (bundle.root / "dist").iterdir()}
    result = _gate(bundle)
    assert result.returncode == 0, result.stderr
    assert {path.name: _sha(path) for path in (bundle.output / "dist").iterdir()} == original
    before = (bundle.output / "manifest.json").read_bytes()
    assert _gate(bundle).returncode != 0
    assert (bundle.output / "manifest.json").read_bytes() == before


@pytest.mark.parametrize("untracked", [False, True])
def test_gate_rejects_inputs_outside_the_bound_commit(
    synthetic_bundle: SyntheticBundle, untracked: bool
) -> None:
    bundle = synthetic_bundle
    target = bundle.repo / ("src/injected.py" if untracked else "datasift-core/Cargo.toml")
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a") as handle:
        handle.write("\n# Unreviewed input\n")
    result = _gate(bundle)
    assert result.returncode != 0
    assert "Uncommitted inputs cannot be bound to a release commit" in result.stderr
    assert not bundle.output.exists()


@pytest.mark.parametrize(
    "failure", ["missing_sdist", "source_input", "fixture_input", "source_bytes", "license"]
)
def test_gate_rejects_incomplete_or_inconsistent_source_distributions(
    synthetic_bundle: SyntheticBundle, failure: str
) -> None:
    bundle = synthetic_bundle
    receipt_path = bundle.receipt_paths[-1]
    receipt = json.loads(receipt_path.read_text())
    if failure == "missing_sdist":
        receipt_path.unlink()
        expected = "Incomplete or duplicate platform evidence"
    else:
        artifact = bundle.root / "dist" / receipt["filename"]
        with tarfile.open(artifact) as archive:
            parts = []
            for member in archive.getmembers():
                stream = archive.extractfile(member)
                assert stream is not None
                parts.append((member, stream.read()))
        with tarfile.open(artifact, "w:gz") as archive:
            for member, content in parts:
                if failure == "source_input" and member.name.endswith("/datasift-core/src/lib.rs"):
                    continue
                if failure == "fixture_input" and member.name.endswith("/tests/fixtures/excel.py"):
                    continue
                if failure == "source_bytes" and member.name.endswith(
                    "/src/chooong/datasift/models.py"
                ):
                    content += b"\n# Synthetic unreviewed edit\n"
                    member.size = len(content)
                if failure == "license" and member.name.endswith("/LICENSE"):
                    content = b"Incorrect synthetic license"
                    member.size = len(content)
                archive.addfile(member, io.BytesIO(content))
        receipt["sha256"] = _sha(artifact)
        _write_json(receipt_path, receipt)
        expected = (
            "Missing source-build input"
            if failure in {"source_input", "fixture_input"}
            else "Source-build input differs"
            if failure == "source_bytes"
            else "sdist license file mismatch"
        )
    result = _gate(bundle)
    assert result.returncode != 0
    assert expected in result.stderr
    assert not bundle.output.exists()


@pytest.mark.parametrize(
    "failure",
    [
        "missing_platform",
        "missing_python",
        "duplicate_python",
        "wrong_commit",
        "wrong_version",
        "wrong_machine",
        "wrong_system",
        "tampered_bytes",
        "tampered_junit",
        "failed_tests",
        "skipped_tests",
        "no_fixtures",
        "unexpected_file",
        "unsafe_filename",
        "wrong_abi",
        "wrong_platform_tag",
        "wrong_content_tag",
        "missing_native",
        "wrong_metadata",
        "wrong_license",
    ],
)
def test_gate_rejects_invalid_evidence_without_creating_publishable_output(
    synthetic_bundle: SyntheticBundle,
    failure: str,
) -> None:
    bundle = synthetic_bundle
    receipt_path = bundle.receipt_paths[0]
    receipt = json.loads(receipt_path.read_text())
    artifact = bundle.root / "dist" / receipt["filename"]
    if failure == "missing_platform":
        receipt_path.unlink()
    elif failure in {
        "missing_python",
        "duplicate_python",
        "wrong_commit",
        "wrong_version",
        "wrong_machine",
        "wrong_system",
        "unsafe_filename",
    }:
        _change_receipt(receipt, failure)
    elif failure == "tampered_bytes":
        with artifact.open("ab") as handle:
            handle.write(b"tampered")
    elif failure in {"tampered_junit", "failed_tests", "skipped_tests", "no_fixtures"}:
        _change_report(bundle, receipt, failure)
    elif failure == "unexpected_file":
        (bundle.root / "dist" / "extra.whl").write_bytes(b"unexpected")
    else:
        _change_archive(artifact, receipt, failure)
    if receipt_path.exists():
        _write_json(receipt_path, receipt)
    result = _gate(bundle)
    assert result.returncode != 0, result.stdout
    assert not bundle.output.exists()


def test_artifact_test_sources_remain_bound_to_the_recorded_commit(
    release_checkout: Path,
    tmp_path: Path,
) -> None:
    from release.shared import git
    from scripts.artifacts import source_snapshot

    original = (release_checkout / "tests/fixtures/excel.py").read_bytes()
    commit = git(release_checkout, "rev-parse", "HEAD")
    (release_checkout / "tests/fixtures/excel.py").write_bytes(b"synthetic concurrent edit")
    snapshot = tmp_path / "snapshot"
    source_snapshot(release_checkout, commit, snapshot)
    assert (snapshot / "tests/fixtures/excel.py").read_bytes() == original
    assert (
        release_checkout / "tests/fixtures/excel.py"
    ).read_bytes() == b"synthetic concurrent edit"
    assert not (snapshot / ".git").exists()
