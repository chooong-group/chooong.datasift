"""Isolated Git checkouts and synthetic release evidence."""

import io
import json
import shutil
import subprocess
import tarfile
import tomllib
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from packaging.utils import canonicalize_name

from release.shared import git
from scripts.artifacts import ProjectFile, source_files
from scripts.licenses import expected_files, read_inventory
from tooling.tests.fixtures import REPO, SyntheticBundle, _sha, _write_json
from tooling.tests.license_fixtures import synthetic_graph, synthetic_licenses, synthetic_native


@pytest.fixture
def release_checkout(tmp_path: Path) -> Path:
    """An isolated, clean commit permits tests during pre-commit and source edits."""
    repo = tmp_path / "checkout"
    repo.mkdir()
    for name in (
        *source_files(REPO),
        ".github/release-targets.json",
        ".gitattributes",
        "LICENSE",
        "CHANGELOG.md",
    ):
        if name.startswith("compliance/") or name == "THIRD_PARTY_NOTICES.txt":
            continue
        target = repo / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO / name, target)
    synthetic_licenses(repo, REPO)
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
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=repo, check=True)
    subprocess.run(
        ["git", "config", "core.hooksPath", str(repo / "empty-hooks")], cwd=repo, check=True
    )
    return repo


@pytest.fixture
def synthetic_bundle(tmp_path: Path, release_checkout: Path) -> SyntheticBundle:
    """Fake binary/JUnit evidence exercises verification logic only; never native support."""
    root = tmp_path / "bundle"
    (root / "dist").mkdir(parents=True)
    (root / "evidence").mkdir()
    project = ProjectFile.model_validate(
        tomllib.loads((REPO / "pyproject.toml").read_text())
    ).project
    version = project.version
    name = canonicalize_name(project.name).replace("-", "_")
    license_inventory = read_inventory(release_checkout)
    license_paths = expected_files(release_checkout, license_inventory)
    metadata_text = (
        f"Metadata-Version: 2.4\nName: {project.name}\nVersion: {version}\n"
        f"Requires-Python: {project.requires_python}\nLicense-Expression: {project.license}\n"
    )
    metadata_text += "".join(f"License-File: {name}\n" for name in license_paths)
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
                for filename in (*source_files(release_checkout), "LICENSE", "PKG-INFO"):
                    content = (
                        metadata_text.encode()
                        if filename == "PKG-INFO"
                        else (release_checkout / filename).read_bytes()
                    )
                    info = tarfile.TarInfo(prefix + "/" + filename)
                    info.size = len(content)
                    archive.addfile(info, io.BytesIO(content))
        else:
            tag = "cp312-abi3-" + target["platform_tag"]
            artifact = root / "dist" / f"{name}-{version}-{tag}.whl"
            distinfo = f"{name}-{version}.dist-info/"
            with ZipFile(artifact, "w", compression=ZIP_DEFLATED) as archive:
                archive.writestr(distinfo + "METADATA", metadata_text)
                archive.writestr(
                    distinfo + "WHEEL", f"Wheel-Version: 1.0\nRoot-Is-Purelib: false\nTag: {tag}\n"
                )
                for license_path in license_paths:
                    archive.writestr(
                        distinfo + "licenses/" + license_path,
                        (release_checkout / license_path).read_bytes(),
                    )
                archive.writestr(
                    "chooong/datasift/rust."
                    + ("pyd" if target["system"] == "Windows" else "abi3.so"),
                    synthetic_native(target["system"]),
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
        for python in ("3.12", "3.13", "3.14"):
            report = root / "evidence" / f"{identifier}-{python}.xml"
            report.write_text(
                '<testsuites><testsuite tests="2" failures="0" errors="0">'
                '<testcase classname="tests.formats.test_excel" name="synthetic_xlsx"/>'
                '<testcase classname="tests.api.test_models" name="synthetic_xlsm"/>'
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
        graph_sha256 = (
            None if is_sdist else _sha(synthetic_graph(artifact, identifier, license_inventory))
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
                "graph_sha256": graph_sha256,
            },
        )
        receipts.append(receipt)
    return SyntheticBundle(
        root=root,
        output=tmp_path / "verified",
        receipt_paths=tuple(receipts),
        repo=release_checkout,
    )


@pytest.fixture
def release_repo(release_checkout: Path) -> Path:
    """Preparation always starts with unreleased notes, regardless of release-branch state."""
    (release_checkout / "CHANGELOG.md").write_text(
        "# Changelog\n\n## Unreleased\n\n### Added\n\n"
        "- Streaming XLSX/XLSM synthetic release fixture.\n",
        encoding="utf-8",
    )
    git(release_checkout, "add", "CHANGELOG.md")
    git(
        release_checkout,
        "-c",
        "user.name=Synthetic fixture",
        "-c",
        "user.email=synthetic@example.invalid",
        "commit",
        "--quiet",
        "-m",
        "Unprepared synthetic release",
    )
    subprocess.run(
        ["git", "switch", "-C", "main"], cwd=release_checkout, check=True, capture_output=True
    )
    return release_checkout
