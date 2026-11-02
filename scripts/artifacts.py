"""Build evidence and fail-closed release gates; never upload to a package index."""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from email.parser import BytesParser
from enum import StrEnum
from fnmatch import fnmatchcase
from pathlib import Path, PurePosixPath
from typing import Annotated, Literal
from zipfile import ZipFile

from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.tags import Tag, parse_tag
from packaging.utils import canonicalize_name, parse_sdist_filename, parse_wheel_filename
from packaging.version import Version
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.licenses import graph_file, require_artifact

SHA256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Commit = Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
FileName = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.+-]*$")]
Identifier = Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9_-]*$")]
REPO = Path(__file__).resolve().parents[1]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class System(StrEnum):
    LINUX = "Linux"
    MACOS = "Darwin"
    WINDOWS = "Windows"


class Machine(StrEnum):
    X86 = "x86_64"
    ARM = "arm64"


class Kind(StrEnum):
    WHEEL = "wheel"
    SDIST = "sdist"


class Command(StrEnum):
    PLAN = "plan"
    TEST = "test"
    GATE = "gate"


class WheelTarget(Model):
    id: Identifier
    runner: Literal[
        "ubuntu-24.04", "ubuntu-24.04-arm", "windows-2022", "macos-15-intel", "macos-15"
    ]
    system: System
    machine: Machine
    rust_target: Annotated[str, Field(pattern=r"^[a-z0-9_-]+$")]
    platform_tag: Annotated[str, Field(pattern=r"^[a-z0-9_]+$")]
    manylinux: Annotated[str, Field(pattern=r"^\d+_\d+$")] | None


class Targets(Model):
    format_version: Literal[1]
    wheels: Annotated[tuple[WheelTarget, ...], Field(min_length=5, max_length=5)]

    @model_validator(mode="after")
    def unique_targets(self) -> Targets:
        if len({target.id for target in self.wheels}) != len(self.wheels):
            raise ValueError("Duplicate target IDs")
        if len({(target.system, target.machine) for target in self.wheels}) != len(self.wheels):
            raise ValueError("Duplicate native platforms")
        return self


class StandardModel(BaseModel):
    """Read only relevant fields of standardized TOML, which has other valid sections."""

    model_config = ConfigDict(extra="ignore", frozen=True, populate_by_name=True)


class Project(StandardModel):
    name: str
    version: str
    requires_python: str = Field(alias="requires-python")
    classifiers: tuple[str, ...]
    license: str

    @property
    def pythons(self) -> tuple[str, ...]:
        prefix = "Programming Language :: Python :: "
        versions = tuple(
            sorted(
                (
                    value.removeprefix(prefix)
                    for value in self.classifiers
                    if value.startswith(prefix) and value.removeprefix(prefix).count(".") == 1
                ),
                key=Version,
            )
        )
        spec = SpecifierSet(self.requires_python)
        if not versions or any(Version(value) not in spec for value in versions):
            raise ValueError("Python classifiers disagree with Requires-Python")
        return versions


class BuildSystem(StandardModel):
    requires: tuple[str, ...]

    @property
    def maturin(self) -> str:
        requirements = [Requirement(value) for value in self.requires]
        maturin = [value for value in requirements if value.name == "maturin"]
        if len(maturin) != 1:
            raise ValueError("One pinned maturin build backend is required")
        specifiers = list(maturin[0].specifier)
        if len(specifiers) != 1 or specifiers[0].operator != "==":
            raise ValueError("Pin the maturin build backend")
        return specifiers[0].version


class IncludePath(StandardModel):
    path: str
    format: str


class MaturinConfig(StandardModel):
    include: tuple[IncludePath, ...]
    exclude: tuple[str, ...]


class Tools(StandardModel):
    maturin: MaturinConfig


class ProjectFile(StandardModel):
    project: Project
    build_system: BuildSystem = Field(alias="build-system")
    tool: Tools


class CargoPackage(StandardModel):
    version: str
    license: str


class PyO3(StandardModel):
    features: tuple[str, ...]


class Dependencies(StandardModel):
    pyo3: PyO3


class CargoFile(StandardModel):
    package: CargoPackage
    dependencies: Dependencies

    @property
    def interpreter(self) -> str:
        features = [
            value.removeprefix("abi3-py")
            for value in self.dependencies.pyo3.features
            if value.startswith("abi3-py")
        ]
        if len(features) != 1 or not features[0].isdigit():
            raise ValueError("One PyO3 ABI3 baseline is required")
        return "cp" + features[0]


class Toolchain(StandardModel):
    channel: Annotated[str, Field(pattern=r"^\d+\.\d+\.\d+$")]


class RustFile(StandardModel):
    toolchain: Toolchain


class Matrix(Model):
    include: tuple[WheelTarget, ...]


class Probe(Model):
    python: str
    system: System
    machine: Machine
    native_origin: str

    @field_validator("machine", mode="before")
    @classmethod
    def machine_alias(cls, value: object) -> object:
        if isinstance(value, str):
            if value.lower() in {"amd64", "x86_64"}:
                return Machine.X86
            if value.lower() in {"aarch64", "arm64"}:
                return Machine.ARM
        return value


class TestRun(Model):
    requested_python: str
    probe: Probe
    junit: FileName
    junit_sha256: SHA256
    tests: Annotated[int, Field(gt=0)]


class Receipt(Model):
    format_version: Literal[1] = 1
    kind: Kind
    target: Identifier
    filename: FileName
    sha256: SHA256
    commit: Commit
    version: str
    runs: tuple[TestRun, ...]
    graph_sha256: SHA256 | None = None


class Manifest(Model):
    format_version: Literal[1] = 1
    commit: Commit
    version: str
    artifacts: tuple[Receipt, ...]


class Arguments(Model):
    command: Command
    repo: Path
    bundle: Path
    target: str | None
    kind: Kind | None
    commit: Commit | None
    version: str | None
    output: Path
    github_output: Path | None


@dataclass(frozen=True, slots=True)
class Context:
    repo: Path
    project: Project
    targets: Targets
    commit: str
    interpreter: str
    maturin: str
    rust: str


def digest(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def context(arguments: Arguments) -> Context:
    repo = arguments.repo.resolve()
    project_file = ProjectFile.model_validate(tomllib.loads((repo / "pyproject.toml").read_text()))
    cargo = CargoFile.model_validate(tomllib.loads((repo / "datasift-core/Cargo.toml").read_text()))
    rust = RustFile.model_validate(tomllib.loads((repo / "rust-toolchain.toml").read_text()))
    project = project_file.project
    if cargo.package.version != project.version or cargo.package.license != project.license:
        raise ValueError("Python/Rust version or license mismatch")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    if arguments.commit is not None and arguments.commit != commit:
        raise ValueError("Checkout does not match the requested commit")
    if arguments.version is not None and arguments.version != project.version:
        raise ValueError("Requested release version differs from pyproject.toml")
    project.pythons  # Validate declared test versions even for a plan-only invocation.
    if arguments.command != Command.PLAN:
        ensure_reviewed_inputs(repo, project_file.tool.maturin)
    return Context(
        repo,
        project,
        Targets.model_validate_json((repo / ".github/release-targets.json").read_text()),
        commit,
        cargo.interpreter,
        project_file.build_system.maturin,
        rust.toolchain.channel,
    )


def ensure_reviewed_inputs(repo: Path, config: MaturinConfig) -> None:
    changed = subprocess.check_output(
        ["git", "diff", "--name-only", "HEAD"], cwd=repo, text=True
    ).splitlines()
    untracked = subprocess.check_output(
        ["git", "ls-files", "--others", "--exclude-standard"], cwd=repo, text=True
    ).splitlines()
    included = tuple(item.path for item in config.include)
    included_roots = tuple(pattern.split("*", 1)[0] for pattern in included if "*" in pattern)
    for name in changed:
        if not any(fnmatchcase(name, pattern) for pattern in config.exclude):
            raise ValueError("Uncommitted inputs cannot be bound to a release commit")
    for name in untracked:
        if any(fnmatchcase(name, pattern) for pattern in config.exclude):
            continue
        if name.startswith(("src/", "datasift-core/", *included_roots)) or any(
            fnmatchcase(name, pattern) for pattern in included
        ):
            raise ValueError("Uncommitted inputs cannot be bound to a release commit")
    subprocess.run(
        [
            "git",
            "ls-files",
            "--error-unmatch",
            "scripts/artifacts.py",
            "scripts/verify_publish.py",
            ".github/release-targets.json",
        ],
        cwd=repo,
        stdout=subprocess.DEVNULL,
        check=True,
    )


def emit_output(path: Path | None, name: str, value: str) -> None:
    if path is not None:
        if "\n" in value or "\r" in value:
            raise ValueError("Workflow outputs must be single-line")
        with path.open("a", encoding="utf-8") as handle:
            handle.write(f"{name}={value}\n")


def plan(ctx: Context, output: Path | None) -> None:
    matrix = Matrix(include=ctx.targets.wheels).model_dump_json()
    emit_output(output, "matrix", matrix)
    emit_output(output, "python", ctx.project.pythons[0])
    emit_output(output, "maturin", ctx.maturin)
    emit_output(output, "rust", ctx.rust)
    sys.stdout.write(matrix + "\n")


def target_for(ctx: Context, identifier: str) -> WheelTarget:
    target = next((target for target in ctx.targets.wheels if target.id == identifier), None)
    if target is None:
        raise ValueError("Unknown native target")
    return target


def safe_file(directory: Path, name: str) -> Path:
    path = directory / name
    if Path(name).name != name or path.is_symlink() or not path.is_file():
        raise ValueError(f"Unsafe or missing artifact: {name}")
    return path


def inventory(names: list[str]) -> None:
    for name in names:
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts or "\\" in name:
            raise ValueError("Unsafe archive path")
        if any(
            part in {".data", ".git", ".venv", "__pycache__", ".env", "site", "target"}
            for part in path.parts
        ):
            raise ValueError("Local data or build directory in artifact")
        if path.suffix.lower() in {".xlsx", ".xlsm", ".xls", ".ndjson", ".pyc", ".pyo"}:
            raise ValueError("Local data or cache in artifact")


def validate_metadata(content: bytes, ctx: Context) -> None:
    metadata = BytesParser().parsebytes(content)
    if canonicalize_name(str(metadata["Name"])) != canonicalize_name(ctx.project.name):
        raise ValueError("Distribution name mismatch")
    if str(metadata["Version"]) != ctx.project.version:
        raise ValueError("Artifact version mismatch")
    if SpecifierSet(str(metadata["Requires-Python"])) != SpecifierSet(ctx.project.requires_python):
        raise ValueError("Requires-Python mismatch")
    if str(metadata["License-Expression"]) != ctx.project.license:
        raise ValueError("License metadata mismatch")


def validate_artifact(path: Path, ctx: Context, receipt_kind: Kind, identifier: str) -> None:
    if receipt_kind == Kind.WHEEL:
        validate_wheel(path, ctx, identifier)
    else:
        validate_sdist(path, ctx)
    require_artifact(path, ctx.repo, identifier)


def validate_wheel(path: Path, ctx: Context, identifier: str) -> None:
    target = target_for(ctx, identifier)
    name, version, build, tags = parse_wheel_filename(path.name)
    if (
        name != canonicalize_name(ctx.project.name)
        or version != Version(ctx.project.version)
        or build
    ):
        raise ValueError("Wheel filename/version mismatch")
    if any(
        tag.interpreter != ctx.interpreter
        or tag.abi != "abi3"
        or tag.platform != target.platform_tag
        for tag in tags
    ):
        raise ValueError("Wheel ABI/platform tags do not match the target")
    with ZipFile(path) as archive:
        names = archive.namelist()
        inventory(names)
        metadata_files = [name for name in names if name.endswith(".dist-info/METADATA")]
        wheel_files = [name for name in names if name.endswith(".dist-info/WHEEL")]
        if len(metadata_files) != 1 or len(wheel_files) != 1:
            raise ValueError("Missing or duplicate wheel metadata")
        validate_metadata(archive.read(metadata_files[0]), ctx)
        wheel = BytesParser().parsebytes(archive.read(wheel_files[0]))
        declared_tags: set[Tag] = set()
        for value in wheel.get_all("Tag", []):
            declared_tags.update(parse_tag(str(value)))
        if declared_tags != tags or str(wheel["Root-Is-Purelib"]).lower() != "false":
            raise ValueError("Wheel content tags or native-library marker mismatch")
        native = [
            name
            for name in names
            if name.startswith("chooong/datasift/rust.") and name.endswith((".so", ".pyd"))
        ]
        if len(native) != 1:
            raise ValueError("Missing native extension")
        for filename in (
            "__init__.py",
            "__main__.py",
            "models.py",
            "reader.py",
            "rust.pyi",
            "py.typed",
        ):
            if "chooong/datasift/" + filename not in names:
                raise ValueError("Missing Python/typing input")
        license_path = metadata_files[0].removesuffix("METADATA") + "licenses/LICENSE"
        if archive.read(license_path) != (ctx.repo / "LICENSE").read_bytes():
            raise ValueError("Wheel license file mismatch")


def source_files(repo: Path) -> tuple[str, ...]:
    return tuple(
        subprocess.check_output(
            [
                "git",
                "ls-files",
                "src",
                "datasift-core",
                "tests",
                "tooling",
                "scripts",
                "release",
                "licenses",
                "THIRD_PARTY_NOTICES.txt",
                "pyproject.toml",
                "uv.lock",
                "rust-toolchain.toml",
            ],
            cwd=repo,
            text=True,
        ).splitlines()
    )


def validate_source_inputs(archive: tarfile.TarFile, repo: Path, prefix: str) -> None:
    for name in source_files(repo):
        try:
            member = archive.extractfile(prefix + "/" + name)
        except KeyError as error:
            raise ValueError(f"Missing source-build input: {name}") from error
        if member is None:
            raise ValueError(f"Missing source-build input: {name}")
        with member:
            if member.read() != (repo / name).read_bytes():
                raise ValueError(f"Source-build input differs from reviewed commit: {name}")


def validate_sdist(path: Path, ctx: Context) -> None:
    name, version = parse_sdist_filename(path.name)
    if name != canonicalize_name(ctx.project.name) or version != Version(ctx.project.version):
        raise ValueError("sdist filename/version mismatch")
    with tarfile.open(path) as archive:
        names = archive.getnames()
        inventory(names)
        if any(member.issym() or member.islnk() for member in archive.getmembers()):
            raise ValueError("Symlinks are not allowed in the sdist")
        metadata = [
            name
            for name in names
            if PurePosixPath(name).parent.parent == PurePosixPath(".")
            and name.endswith("/PKG-INFO")
        ]
        if len(metadata) != 1:
            raise ValueError("sdist must have one root PKG-INFO")
        handle = archive.extractfile(metadata[0])
        if handle is None:
            raise ValueError("Missing sdist metadata")
        with handle:
            validate_metadata(handle.read(), ctx)
        prefix = PurePosixPath(metadata[0]).parts[0]
        license_file = archive.extractfile(prefix + "/LICENSE")
        if license_file is None:
            raise ValueError("Missing sdist license")
        with license_file:
            if license_file.read() != (ctx.repo / "LICENSE").read_bytes():
                raise ValueError("sdist license file mismatch")
        for suffix in (
            "/pyproject.toml",
            "/datasift-core/Cargo.toml",
            "/datasift-core/src/lib.rs",
            "/datasift-core/Cargo.lock",
            "/rust-toolchain.toml",
            "/uv.lock",
            "/src/chooong/datasift/models.py",
            "/src/chooong/datasift/reader.py",
            "/src/chooong/datasift/rust.pyi",
            "/src/chooong/datasift/py.typed",
            "/tests/formats/test_excel.py",
        ):
            if not any(name.endswith(suffix) for name in names):
                raise ValueError(f"Missing source-build input: {suffix}")

        validate_source_inputs(archive, ctx.repo, prefix)


def junit_count(path: Path) -> int:
    root = ET.parse(path).getroot()
    if any(node.tag in {"failure", "error", "skipped"} for node in root.iter()):
        raise ValueError("Failed, errored, or skipped artifact tests")
    cases = list(root.iter("testcase"))
    classes = {node.attrib.get("classname", "") for node in cases}
    if (
        not cases
        or not any("formats.test_excel" in name or "formats/test_excel" in name for name in classes)
        or not any("api.test_models" in name or "api/test_models" in name for name in classes)
    ):
        raise ValueError("No actual XLSX/XLSM fixture tests in report")
    return len(cases)


PROBE = """
import json, pathlib, platform, sys
import chooong.datasift
from chooong.datasift import rust
origin = pathlib.Path(rust.__file__).resolve()
prefix = pathlib.Path(sys.prefix).resolve()
package = pathlib.Path(chooong.datasift.__file__).resolve()
if not origin.is_relative_to(prefix) or not package.is_relative_to(prefix):
    raise SystemExit('imports came from outside the isolated environment')
if rust.BatchIterator.__module__ != 'chooong.datasift.rust':
    raise SystemExit('incorrect native module')
print(json.dumps(dict(python=platform.python_version(), system=platform.system(),
                     machine=platform.machine(), native_origin=str(origin.relative_to(prefix)))))
"""


def validate_probe(probe: Probe, ctx: Context, kind: Kind, identifier: str, python: str) -> None:
    if ".".join(probe.python.split(".")[:2]) != python:
        raise ValueError("Wrong test interpreter")
    if (
        not probe.native_origin.endswith((".so", ".pyd"))
        or PurePosixPath(probe.native_origin.replace("\\", "/")).is_absolute()
    ):
        raise ValueError("Invalid native import origin")
    targets = (target_for(ctx, identifier),) if kind == Kind.WHEEL else ctx.targets.wheels
    if not any(
        probe.system == target.system and probe.machine == target.machine for target in targets
    ):
        raise ValueError("Cross-compilation is not a native runtime test")


def source_snapshot(repo: Path, commit: str, destination: Path) -> None:
    destination.mkdir(parents=True)
    with tempfile.TemporaryFile() as content:
        subprocess.run(
            ["git", "archive", "--format=tar", commit],
            cwd=repo,
            stdout=content,
            check=True,
        )
        content.seek(0)
        with tarfile.open(fileobj=content) as archive:
            archive.extractall(destination, filter="data")


def test_artifact(ctx: Context, args: Arguments) -> None:
    if args.kind is None or args.target is None:
        raise ValueError("test requires --kind and --target")
    if args.kind == Kind.SDIST and args.target != Kind.SDIST.value:
        raise ValueError("Source receipts must use target sdist")
    bundle = args.bundle.resolve()
    suffix = "*.whl" if args.kind == Kind.WHEEL else "*.tar.gz"
    files = list((bundle / "dist").glob(suffix))
    if len(files) != 1:
        raise ValueError("Test each artifact separately")
    artifact = files[0]
    validate_artifact(artifact, ctx, args.kind, args.target)
    before = digest(artifact)
    uv = shutil.which("uv")
    if uv is None:
        raise ValueError("uv is required")
    evidence = bundle / "evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    runs: list[TestRun] = []
    with tempfile.TemporaryDirectory(prefix="datasift-artifact-test-") as temporary:
        temporary_path = Path(temporary)
        source = temporary_path / "source"
        source_snapshot(ctx.repo, ctx.commit, source)
        requirements = temporary_path / "requirements.txt"
        subprocess.run(
            [uv, "export", "--frozen", "--no-emit-project", "--output-file", str(requirements)],
            cwd=source,
            stdout=subprocess.DEVNULL,
            check=True,
        )
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)
        for python in ctx.project.pythons:
            venv = temporary_path / ("python-" + python)
            subprocess.run([uv, "venv", "--python", python, str(venv)], check=True)
            executable = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            subprocess.run(
                [
                    uv,
                    "pip",
                    "install",
                    "--python",
                    str(executable),
                    "--require-hashes",
                    "-r",
                    str(requirements),
                ],
                check=True,
            )
            subprocess.run(
                [
                    uv,
                    "pip",
                    "install",
                    "--python",
                    str(executable),
                    "--no-deps",
                    "--no-cache",
                    "--config-settings=maturin.build-args=--locked",
                    str(artifact),
                ],
                check=True,
            )
            probe = Probe.model_validate_json(
                subprocess.check_output(
                    [str(executable), "-I", "-c", PROBE], cwd=temporary_path, env=env, text=True
                )
            )
            validate_probe(probe, ctx, args.kind, args.target, python)
            junit = evidence / f"{args.target}-{python}.xml"
            subprocess.run(
                [
                    str(executable),
                    "-I",
                    "-m",
                    "pytest",
                    "-c",
                    str(source / "pyproject.toml"),
                    "-m",
                    "not benchmark",
                    "-p",
                    "no:cacheprovider",
                    "--cov=chooong.datasift",
                    "--cov-config",
                    str(source / "pyproject.toml"),
                    "--cov-report=term-missing",
                    "--junitxml",
                    str(junit),
                    str(source / "tests"),
                ],
                cwd=temporary_path,
                env=env,
                check=True,
            )
            runs.append(
                TestRun(
                    requested_python=python,
                    probe=probe,
                    junit=junit.name,
                    junit_sha256=digest(junit),
                    tests=junit_count(junit),
                )
            )
    if digest(artifact) != before:
        raise ValueError("Artifact changed during its test")
    receipt = Receipt(
        kind=args.kind,
        target=args.target,
        filename=artifact.name,
        sha256=before,
        commit=ctx.commit,
        version=ctx.project.version,
        runs=tuple(runs),
        graph_sha256=digest(graph_file(artifact, args.target)) if args.kind == Kind.WHEEL else None,
    )
    (evidence / f"{args.target}.json").write_text(
        receipt.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )


def verify_receipt(ctx: Context, bundle: Path, receipt: Receipt) -> None:
    expected_kind = Kind.SDIST if receipt.target == Kind.SDIST.value else Kind.WHEEL
    if (
        receipt.kind != expected_kind
        or receipt.commit != ctx.commit
        or receipt.version != ctx.project.version
    ):
        raise ValueError("Artifact kind/commit/version mismatch")
    artifact = safe_file(bundle / "dist", receipt.filename)
    if digest(artifact) != receipt.sha256:
        raise ValueError("Artifact SHA-256 mismatch")
    if receipt.kind == Kind.WHEEL:
        graph = safe_file(bundle / "licenses", receipt.target + ".cargo.json")
        if receipt.graph_sha256 is None or digest(graph) != receipt.graph_sha256:
            raise ValueError("Resolved Cargo graph checksum mismatch")
    elif receipt.graph_sha256 is not None:
        raise ValueError("Source receipt must not claim an embedded Cargo graph")
    validate_artifact(artifact, ctx, receipt.kind, receipt.target)
    if sorted(run.requested_python for run in receipt.runs) != list(ctx.project.pythons):
        raise ValueError("Missing or duplicate Python runtime evidence")
    for run in receipt.runs:
        validate_probe(run.probe, ctx, receipt.kind, receipt.target, run.requested_python)
        junit = safe_file(bundle / "evidence", run.junit)
        if digest(junit) != run.junit_sha256 or junit_count(junit) != run.tests:
            raise ValueError("Test evidence checksum/count mismatch")


def copy_graph(bundle: Path, copied: Path, receipt: Receipt) -> None:
    if receipt.kind == Kind.WHEEL:
        copied_graph = graph_file(copied, receipt.target)
        copied_graph.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(
            graph_file(bundle / "dist" / receipt.filename, receipt.target), copied_graph
        )
        if digest(copied_graph) != receipt.graph_sha256:
            raise ValueError("Resolved Cargo graph changed while staging")


def gate(ctx: Context, args: Arguments) -> None:
    bundle = args.bundle.resolve()
    receipts = tuple(
        Receipt.model_validate_json(path.read_text())
        for path in sorted((bundle / "evidence").glob("*.json"))
    )
    expected = {target.id for target in ctx.targets.wheels} | {Kind.SDIST.value}
    if {receipt.target for receipt in receipts} != expected or len(receipts) != len(expected):
        raise ValueError("Incomplete or duplicate platform evidence")
    if len({receipt.filename for receipt in receipts}) != len(receipts):
        raise ValueError("Duplicate artifact filenames")
    for receipt in receipts:
        verify_receipt(ctx, bundle, receipt)
    if {path.name for path in (bundle / "dist").iterdir()} != {
        receipt.filename for receipt in receipts
    }:
        raise ValueError("Unexpected distribution files")
    output = args.output.resolve()
    if output.exists():
        raise ValueError("Refusing to overwrite an existing verified bundle")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent, prefix=".verified-") as temporary:
        stage = Path(temporary) / "candidate"
        (stage / "dist").mkdir(parents=True)
        for receipt in receipts:
            copied = stage / "dist" / receipt.filename
            shutil.copyfile(bundle / "dist" / receipt.filename, copied)
            if digest(copied) != receipt.sha256:
                raise ValueError("Artifact changed while staging the verified bundle")
            copy_graph(bundle, copied, receipt)
        (stage / "SHA256SUMS").write_text(
            "".join(f"{receipt.sha256}  {receipt.filename}\n" for receipt in receipts),
            encoding="utf-8",
        )
        (stage / "manifest.json").write_text(
            Manifest(
                commit=ctx.commit, version=ctx.project.version, artifacts=receipts
            ).model_dump_json(indent=2)
            + "\n",
            encoding="utf-8",
        )
        stage.replace(output)
    emit_output(args.github_output, "checksums-sha256", digest(output / "SHA256SUMS"))
    sys.stdout.write(
        f"Verified {len(receipts)} unchanged distributions "
        f"for {ctx.commit} / {ctx.project.version}\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=list(Command))
    parser.add_argument("--repo", type=Path, default=REPO)
    parser.add_argument("--bundle", type=Path, default=Path("bundle"))
    parser.add_argument("--target")
    parser.add_argument("--kind", choices=list(Kind))
    parser.add_argument("--commit")
    parser.add_argument("--version")
    parser.add_argument("--output", type=Path, default=Path("verified"))
    parser.add_argument("--github-output", type=Path)
    arguments = Arguments.model_validate(vars(parser.parse_args()))
    ctx = context(arguments)
    if arguments.command == Command.PLAN:
        plan(ctx, arguments.github_output)
    elif arguments.command == Command.TEST:
        test_artifact(ctx, arguments)
    else:
        gate(ctx, arguments)


if __name__ == "__main__":
    main()
