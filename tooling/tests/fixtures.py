"""Synthetic archive and receipt mutations for negative tests."""

import hashlib
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

REPO = Path(__file__).resolve().parents[2]


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
        text = text.replace("tests.formats.test_excel", "unrelated").replace(
            "tests.api.test_models", "unrelated"
        )
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
    elif failure in {"wrong_license_bytes", "license_crlf"}:
        license_name = metadata_name.removesuffix("METADATA") + "licenses/LICENSE"
        with ZipFile(artifact) as archive:
            license_bytes = archive.read(license_name)
        content = (
            license_bytes.replace(b"\n", b"\r\n")
            if failure == "license_crlf"
            else b"Incorrect synthetic license"
        )
        _rewrite_zip(artifact, license_name, content)
    elif failure == "wrong_content_tag":
        _rewrite_zip(artifact, wheel_name, wheel.replace(b"cp312", b"cp311"))
    else:
        replacement = (
            artifact.name.replace("cp312", "cp311")
            if failure == "wrong_abi"
            else artifact.name.replace("manylinux_2_28", "manylinux_2_99")
        )
        new_artifact = artifact.with_name(replacement)
        artifact.rename(new_artifact)
        artifact = new_artifact
        receipt["filename"] = artifact.name
    receipt["sha256"] = _sha(artifact)
