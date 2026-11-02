"""Synthetic gate contracts, not claims of real platform execution."""

import hashlib
import io
import json
import shutil
import subprocess
import sys
import tarfile
from dataclasses import dataclass
from importlib.metadata import distribution
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
import yaml
from packaging.utils import canonicalize_name

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts/artifacts.py"


@dataclass(frozen=True, slots=True)
class SyntheticBundle:
    root: Path
    output: Path
    receipt_paths: tuple[Path, ...]
    repo: Path


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _gate(bundle: SyntheticBundle) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "gate",
            "--repo",
            str(bundle.repo),
            "--bundle",
            str(bundle.root),
            "--output",
            str(bundle.output),
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def _rewrite_zip(path: Path, member: str, content: bytes | None) -> None:
    with ZipFile(path) as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}
    if content is None:
        del parts[member]
    else:
        parts[member] = content
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
        for name, data in parts.items():
            archive.writestr(name, data)


@pytest.fixture
def release_checkout(tmp_path: Path) -> Path:
    """An isolated, clean commit permits tests during pre-commit and source edits."""
    repo = tmp_path / "checkout"
    repo.mkdir()
    for name in (
        "pyproject.toml",
        "datasift-core/Cargo.toml",
        "rust-toolchain.toml",
        ".github/release-targets.json",
        "scripts/artifacts.py",
        "scripts/verify_publish.py",
        "LICENSE",
    ):
        target = repo / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO / name, target)
    for args in (
        ["init", "--quiet"],
        ["add", "."],
        [
            "-c",
            "commit.gpgsign=false",
            "-c",
            "core.hooksPath=" + str(repo / "empty-hooks"),
            "-c",
            "user.name=Synthetic fixture",
            "-c",
            "user.email=synthetic@example.invalid",
            "commit",
            "--quiet",
            "-m",
            "Synthetic release input",
        ],
    ):
        subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)
    return repo


@pytest.fixture
def synthetic_bundle(tmp_path: Path, release_checkout: Path) -> SyntheticBundle:
    """Fake binary/JUnit evidence exercises verification logic only; never native support."""
    root = tmp_path / "bundle"
    (root / "dist").mkdir(parents=True)
    (root / "evidence").mkdir()
    metadata = distribution("chooong.datasift")
    version = metadata.version
    name = canonicalize_name(metadata.metadata["Name"]).replace("-", "_")
    metadata_text = metadata.read_text("METADATA")
    assert metadata_text is not None
    commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=release_checkout, text=True
    ).strip()
    targets = json.loads((REPO / ".github/release-targets.json").read_text())["wheels"]
    receipts: list[Path] = []
    for target in [*targets, {"id": "sdist", "system": "Darwin", "machine": "arm64"}]:
        identifier = target["id"]
        is_sdist = identifier == "sdist"
        if is_sdist:
            artifact = root / "dist" / f"{name}-{version}.tar.gz"
            prefix = f"{name}-{version}"
            with tarfile.open(artifact, "w:gz") as archive:
                for filename in (
                    "pyproject.toml",
                    "datasift-core/Cargo.toml",
                    "datasift-core/src/lib.rs",
                    "datasift-core/Cargo.lock",
                    "rust-toolchain.toml",
                    "uv.lock",
                    "src/chooong/datasift/models.py",
                    "src/chooong/datasift/reader.py",
                    "src/chooong/datasift/rust.pyi",
                    "src/chooong/datasift/py.typed",
                    "tests/test_engine.py",
                    "LICENSE",
                    "PKG-INFO",
                ):
                    content = (
                        metadata_text.encode()
                        if filename == "PKG-INFO"
                        else (REPO / filename).read_bytes()
                    )
                    info = tarfile.TarInfo(prefix + "/" + filename)
                    info.size = len(content)
                    archive.addfile(info, io.BytesIO(content))
        else:
            tag = "cp313-abi3-" + target["platform_tag"]
            artifact = root / "dist" / f"{name}-{version}-{tag}.whl"
            distinfo = f"{name}-{version}.dist-info/"
            with ZipFile(artifact, "w", compression=ZIP_DEFLATED) as archive:
                archive.writestr(distinfo + "METADATA", metadata_text)
                archive.writestr(
                    distinfo + "WHEEL", f"Wheel-Version: 1.0\nRoot-Is-Purelib: false\nTag: {tag}\n"
                )
                archive.writestr(distinfo + "licenses/LICENSE", (REPO / "LICENSE").read_bytes())
                archive.writestr(
                    "chooong/datasift/rust."
                    + ("pyd" if target["system"] == "Windows" else "abi3.so"),
                    b"SYNTHETIC, NOT AN EXECUTABLE LIBRARY",
                )
                for filename in (
                    "__init__.py",
                    "__main__.py",
                    "models.py",
                    "reader.py",
                    "rust.pyi",
                    "py.typed",
                ):
                    archive.writestr("chooong/datasift/" + filename, b"")
        runs = []
        for python in ("3.13", "3.14"):
            report = root / "evidence" / f"{identifier}-{python}.xml"
            report.write_text(
                '<testsuites><testsuite tests="2" failures="0" errors="0">'
                '<testcase classname="test_engine" name="synthetic_xlsx"/>'
                '<testcase classname="test_contract" name="synthetic_xlsm"/>'
                "</testsuite></testsuites>"
            )
            runs.append(
                {
                    "requested_python": python,
                    "probe": {
                        "python": python + ".0",
                        "system": target["system"],
                        "machine": target["machine"],
                        "native_origin": "site-packages/chooong/datasift/rust.abi3.so",
                    },
                    "junit": report.name,
                    "junit_sha256": _sha(report),
                    "tests": 2,
                }
            )
        receipt = root / "evidence" / f"{identifier}.json"
        _write_json(
            receipt,
            {
                "format_version": 1,
                "kind": "sdist" if is_sdist else "wheel",
                "target": identifier,
                "filename": artifact.name,
                "sha256": _sha(artifact),
                "commit": commit,
                "version": version,
                "runs": runs,
            },
        )
        receipts.append(receipt)
    return SyntheticBundle(
        root=root,
        output=tmp_path / "verified",
        receipt_paths=tuple(receipts),
        repo=release_checkout,
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


@pytest.mark.parametrize("failure", ["missing_sdist", "source_input", "license"])
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
                if failure == "license" and member.name.endswith("/LICENSE"):
                    content = b"Incorrect synthetic license"
                    member.size = len(content)
                archive.addfile(member, io.BytesIO(content))
        receipt["sha256"] = _sha(artifact)
        _write_json(receipt_path, receipt)
        expected = (
            "Missing source-build input"
            if failure == "source_input"
            else "sdist license file mismatch"
        )
    result = _gate(bundle)
    assert result.returncode != 0
    assert expected in result.stderr
    assert not bundle.output.exists()


def _change_receipt(receipt: dict, failure: str) -> None:
    if failure == "missing_python":
        receipt["runs"].pop()
    elif failure == "duplicate_python":
        receipt["runs"].append(receipt["runs"][0])
    elif failure == "wrong_commit":
        receipt["commit"] = "0" * 40
    elif failure == "wrong_version":
        receipt["version"] = "999.0"
    elif failure == "wrong_machine":
        probe = receipt["runs"][0]["probe"]
        probe["machine"] = "arm64" if probe["machine"] == "x86_64" else "x86_64"
    elif failure == "wrong_system":
        probe = receipt["runs"][0]["probe"]
        probe["system"] = "Windows" if probe["system"] == "Linux" else "Linux"
    else:
        receipt["filename"] = "../outside.whl"


def _change_report(bundle: SyntheticBundle, receipt: dict, failure: str) -> None:
    run = receipt["runs"][0]
    report = bundle.root / "evidence" / run["junit"]
    text = report.read_text()
    if failure == "no_fixtures":
        text = text.replace("test_engine", "unrelated").replace("test_contract", "unrelated")
    else:
        marker = "<skipped/>" if failure == "skipped_tests" else "<failure/>"
        text = text.replace("</testsuite>", marker + "</testsuite>")
    report.write_text(text)
    if failure != "tampered_junit":
        run["junit_sha256"] = _sha(report)


def _change_archive(artifact: Path, receipt: dict, failure: str) -> None:
    with ZipFile(artifact) as archive:
        wheel_name = next(name for name in archive.namelist() if name.endswith("/WHEEL"))
        metadata_name = next(name for name in archive.namelist() if name.endswith("/METADATA"))
        native_name = next(name for name in archive.namelist() if name.endswith((".so", ".pyd")))
        wheel = archive.read(wheel_name)
        metadata = archive.read(metadata_name)
    if failure == "missing_native":
        _rewrite_zip(artifact, native_name, None)
    elif failure == "wrong_metadata":
        _rewrite_zip(
            artifact,
            metadata_name,
            metadata.replace(b"Version: " + receipt["version"].encode(), b"Version: 999.0"),
        )
    elif failure == "wrong_license":
        _rewrite_zip(artifact, metadata_name, metadata.replace(b"Apache-2.0", b"MIT"))
    elif failure == "wrong_content_tag":
        _rewrite_zip(artifact, wheel_name, wheel.replace(b"cp313", b"cp312"))
    else:
        replacement = (
            artifact.name.replace("cp313", "cp312")
            if failure == "wrong_abi"
            else artifact.name.replace("manylinux_2_28", "manylinux_2_99")
        )
        new_artifact = artifact.with_name(replacement)
        artifact.rename(new_artifact)
        artifact = new_artifact
        receipt["filename"] = artifact.name
    receipt["sha256"] = _sha(artifact)


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


def test_workflows_are_read_only_for_forks_and_publication_is_hard_disabled() -> None:
    workflows = REPO / ".github/workflows"
    for path in workflows.glob("*.yml"):
        text = path.read_text()
        assert "pull_request_target" not in text
        assert "self-hosted" not in text
        assert "secrets." not in text
        workflow = yaml.load(text, Loader=yaml.BaseLoader)
        assert workflow["permissions"] == {"contents": "read"}
    release = yaml.load((workflows / "release.yml").read_text(), Loader=yaml.BaseLoader)
    assert set(release["on"]) == {"workflow_dispatch"}
    publish = release["jobs"]["publish"]
    assert publish["if"].startswith("${{ false &&")
    assert publish["environment"]["name"] == "pypi"
    assert publish["permissions"]["id-token"] == "write"
    assert not (workflows / "release-gitlab-pypi.yml").exists()
    pages = yaml.load((workflows / "docs-pages.yml").read_text(), Loader=yaml.BaseLoader)
    assert pages["jobs"]["build"]["if"].startswith("${{ false &&")
    ci = yaml.load((workflows / "ci.yml").read_text(), Loader=yaml.BaseLoader)
    assert all(
        "github.event.repository.private == false" in job["if"] for job in ci["jobs"].values()
    )


def test_quickstart_runs_against_real_workbook_and_never_overwrites(tmp_path: Path) -> None:
    from chooong.datasift import iter_matching_rows

    workbook = tmp_path / "sample.xlsx"
    command = [sys.executable, str(REPO / "examples/create_sample.py"), str(workbook)]
    assert subprocess.run(command, check=False).returncode == 0
    before = workbook.read_bytes()
    assert [
        dict(row) for row in iter_matching_rows(workbook, REPO / "examples/quickstart-filter.json")
    ] == [
        {"Country": "DE"},
        {"Country": "DE"},
    ]
    assert subprocess.run(command, capture_output=True, check=False).returncode != 0
    assert workbook.read_bytes() == before
