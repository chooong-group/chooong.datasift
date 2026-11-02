"""Offline, fail-closed dependency and distribution license verification."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
import subprocess
import sys
import tarfile
import tomllib
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from email.parser import BytesParser
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import ClassVar
from urllib.parse import urlsplit
from urllib.request import urlopen
from zipfile import ZipFile, is_zipfile

from packaging.licenses import InvalidLicenseExpression, canonicalize_license_expression
from pydantic import ConfigDict, TypeAdapter

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.license_binary import NativeImports, inspect_native

REPO = Path(__file__).resolve().parents[1]
INVENTORY = "compliance/inventory.json"
NOTICE = "THIRD_PARTY_NOTICES.txt"
PERMISSIVE = frozenset(
    {
        "MIT",
        "MIT-0",
        "Apache-2.0",
        "Apache-2.0 WITH LLVM-exception",
        "BSD-2-Clause",
        "BSD-3-Clause",
        "Zlib",
        "Unicode-3.0",
        "CC0-1.0",
        "Unlicense",
        "PSF-2.0",
        "Python-2.0",
        "ISC",
        "0BSD",
        "Unicode-DFS-2016",
    }
)


class Status(StrEnum):
    PASS = "PASS"  # noqa: S105 - audit outcome, not a credential.
    FAIL = "FAIL"
    NOT_DISTRIBUTED = "NOT_DISTRIBUTED"


class Ecosystem(StrEnum):
    CARGO = "cargo"
    PYTHON = "python"
    BUILD = "build-tool"
    TOOLCHAIN = "toolchain"
    SYSTEM = "system"
    EMBEDDED = "embedded-cargo"


class Use(StrEnum):
    RUNTIME = "runtime"
    BUILD = "build"
    DEV = "dev"
    LOCKED = "locked-only"
    EXTERNAL = "external-runtime"
    GENERATED = "generated-code"


class Scope(StrEnum):
    DISTRIBUTED = "distributed"
    EXTERNAL_RUNTIME = "external-runtime"
    BUILD = "build-tool"
    DEV = "dev-tool"
    SYSTEM = "external-system"
    UNUSED = "not-used"


class ProofRole(StrEnum):
    LICENSE = "license"
    NOTICE = "notice"
    COPYRIGHT = "copyright"
    CANONICAL = "canonical-license"
    LOCK = "dependency-lock"


class StrictRecord:
    __slots__ = ()
    __pydantic_config__: ClassVar[ConfigDict] = ConfigDict(extra="forbid")


@dataclass(frozen=True, slots=True)
class Proof(StrictRecord):
    path: str
    sha256: str
    url: str
    source_sha256: str
    member: str | None
    role: ProofRole


@dataclass(frozen=True, slots=True)
class Usage(StrictRecord):
    target: str
    categories: tuple[Use, ...]


@dataclass(frozen=True, slots=True)
class Dependency(StrictRecord):
    ecosystem: Ecosystem
    name: str
    version: str
    source: str
    source_sha256: str
    declared_license: str
    selected_license: str
    copyright: tuple[str, ...]
    proofs: tuple[Proof, ...]
    usage: tuple[Usage, ...]
    redistributed: bool
    status: Status
    rationale: str
    blockers: tuple[str, ...]
    parents: tuple[str, ...] = ()

    @property
    def identifier(self) -> str:
        return f"{self.ecosystem.value}:{self.name}@{self.version}"


@dataclass(frozen=True, slots=True)
class LockBinding(StrictRecord):
    path: str
    sha256: str


@dataclass(frozen=True, slots=True)
class Origin:
    url: str
    sha256: str


@dataclass(frozen=True, slots=True)
class Inventory(StrictRecord):
    format_version: int
    project_version: str
    locks: tuple[LockBinding, ...]
    targets: tuple[str, ...]
    dependencies: tuple[Dependency, ...]


@dataclass(frozen=True, slots=True)
class ComponentResult:
    identifier: str
    target: str
    status: Status
    reasons: tuple[str, ...]
    scope: Scope = Scope.DISTRIBUTED


@dataclass(frozen=True, slots=True)
class ArtifactResult:
    filename: str
    sha256: str
    target: str
    status: Status
    errors: tuple[str, ...]
    imports: NativeImports | None
    dependencies: tuple[ComponentResult, ...]
    graph_sha256: str | None = None
    external_python: tuple[str, ...] = ()
    build_dependencies: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Audit:
    format_version: int
    inventory_sha256: str
    status: Status
    artifacts: tuple[ArtifactResult, ...]


INVENTORY_ADAPTER = TypeAdapter(Inventory)
AUDIT_ADAPTER = TypeAdapter(Audit)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_inventory(repo: Path) -> Inventory:
    result = INVENTORY_ADAPTER.validate_json((repo / INVENTORY).read_bytes(), strict=False)
    if result.format_version != 1:
        raise ValueError("Unsupported license inventory format")
    identifiers = [entry.identifier for entry in result.dependencies]
    if not identifiers or len(set(identifiers)) != len(identifiers):
        raise ValueError("Empty or duplicate dependency inventory")
    return result


def safe_path(repo: Path, name: str) -> Path:
    relative = PurePosixPath(name)
    if relative.is_absolute() or ".." in relative.parts or "\\" in name:
        raise ValueError("Unsafe license proof path")
    path = repo / name
    if path.is_symlink() or not path.resolve().is_relative_to(repo.resolve()):
        raise ValueError("Unsafe license proof path")
    return path


def atoms(expression: str) -> frozenset[str]:
    normalized = canonicalize_license_expression(expression)
    tokens = re.findall(r"[^\s()]+|[()]", normalized)
    result: set[str] = set()
    offset = 0
    while offset < len(tokens):
        term = tokens[offset]
        if term not in {"(", ")", "AND", "OR"}:
            if offset + 2 < len(tokens) and tokens[offset + 1] == "WITH":
                term += " WITH " + tokens[offset + 2]
                offset += 2
            result.add(term)
        offset += 1
    return frozenset(result)


def operand(tokens: tuple[str, ...], selected: frozenset[str], start: int) -> tuple[bool, int]:
    term = tokens[start]
    if term == "(":
        value, end = disjunction(tokens, selected, start + 1)
        if tokens[end] != ")":
            raise ValueError("Invalid SPDX parentheses")
        return value, end + 1
    if start + 2 < len(tokens) and tokens[start + 1] == "WITH":
        return term + " WITH " + tokens[start + 2] in selected, start + 3
    return term in selected, start + 1


def conjunction(tokens: tuple[str, ...], selected: frozenset[str], start: int) -> tuple[bool, int]:
    value, end = operand(tokens, selected, start)
    while end < len(tokens) and tokens[end] == "AND":
        next_value, end = operand(tokens, selected, end + 1)
        value = value and next_value
    return value, end


def disjunction(tokens: tuple[str, ...], selected: frozenset[str], start: int) -> tuple[bool, int]:
    value, end = conjunction(tokens, selected, start)
    while end < len(tokens) and tokens[end] == "OR":
        next_value, end = conjunction(tokens, selected, end + 1)
        value = value or next_value
    return value, end


def selection_valid(declared: str, selected: str) -> bool:
    canonical = canonicalize_license_expression(declared)
    chosen = canonicalize_license_expression(selected)
    # A selection is one concrete obligation set, not another unresolved alternative.
    if " OR " in chosen:
        return False
    selected_atoms = atoms(chosen)
    if not selected_atoms <= atoms(canonical):
        return False
    tokens = tuple(re.findall(r"[^\s()]+|[()]", canonical))
    value, end = disjunction(tokens, selected_atoms, 0)
    return value and end == len(tokens)


def expression_errors(entry: Dependency) -> tuple[str, ...]:
    errors: list[str] = []
    try:
        if not selection_valid(entry.declared_license, entry.selected_license):
            errors.append("Selected SPDX obligations do not satisfy the declared license")
        permitted = PERMISSIVE
        if not atoms(entry.selected_license) <= permitted:
            errors.append("Custom, unknown or unapproved license/exception requires review")
    except (InvalidLicenseExpression, ValueError, IndexError):
        errors.append("Unknown or invalid SPDX license expression")
    return tuple(errors)


def component_errors(entry: Dependency, repo: Path) -> tuple[str, ...]:
    errors = list(entry.blockers)
    if entry.status != Status.PASS:
        errors.append("Dependency has no completed license assessment")
    if not entry.rationale.strip() or not entry.proofs or not entry.copyright:
        errors.append("Missing rationale, original evidence or copyright evidence")
    if not any(
        proof.url == entry.source
        and proof.source_sha256 == entry.source_sha256
        and proof.role in {ProofRole.LICENSE, ProofRole.COPYRIGHT, ProofRole.NOTICE}
        for proof in entry.proofs
    ):
        errors.append("No original license/copyright evidence bound to this dependency source")
    errors.extend(expression_errors(entry))
    for proof in entry.proofs:
        path = safe_path(repo, proof.path)
        if not path.is_file() or sha256(path.read_bytes()) != proof.sha256:
            errors.append(f"Missing or changed original evidence: {proof.path}")
        if not re.fullmatch(r"[0-9a-f]{64}", proof.source_sha256):
            errors.append("Missing exact upstream source hash")
        if urlsplit(proof.url).scheme != "https":
            errors.append("License evidence needs a verifiable HTTPS source")
    return tuple(dict.fromkeys(errors))


def locked_packages(repo: Path) -> set[tuple[str, str, str]]:
    records = tomllib.loads((repo / "datasift-core/Cargo.lock").read_text(encoding="utf-8"))[
        "package"
    ]
    return {
        (record["name"], record["version"], record["checksum"])
        for record in records
        if "source" in record
    }


def inventory_errors(repo: Path, inventory: Inventory) -> tuple[str, ...]:
    errors: list[str] = []
    required = {
        "datasift-core/Cargo.lock",
        "datasift-core/Cargo.toml",
        "rust-toolchain.toml",
        ".github/release-targets.json",
    }
    if {binding.path for binding in inventory.locks} != required or len(inventory.locks) != len(
        required
    ):
        errors.append("Missing/duplicate lock or release-target bindings")
    errors.extend(
        f"License inventory is stale: {binding.path}"
        for binding in inventory.locks
        if sha256(safe_path(repo, binding.path).read_bytes()) != binding.sha256
    )
    reviewed = {
        (entry.name, entry.version, entry.source_sha256)
        for entry in inventory.dependencies
        if entry.ecosystem == Ecosystem.CARGO
    }
    if not reviewed <= locked_packages(repo):
        errors.append("Inconsistent Rust inventory: datasift-core/Cargo.lock")
    project = tomllib.loads((repo / "pyproject.toml").read_text(encoding="utf-8"))
    if project["project"]["version"] != inventory.project_version:
        errors.append("Inventory project version mismatch")
    expected = tuple(
        t["id"] for t in json.loads((repo / ".github/release-targets.json").read_text())["wheels"]
    )
    if set(inventory.targets) != set(expected) or len(inventory.targets) != len(expected):
        errors.append("Incomplete license target matrix")
    errors.extend(
        f"Missing platform classification: {entry.identifier}"
        for entry in inventory.dependencies
        if {u.target for u in entry.usage} != set(expected) or len(entry.usage) != len(expected)
    )
    rust = tomllib.loads((repo / "rust-toolchain.toml").read_text())["toolchain"]["channel"]
    if [
        (e.name, e.version)
        for e in inventory.dependencies
        if e.ecosystem == Ecosystem.TOOLCHAIN and e.name == "rust-std"
    ] != [("rust-std", rust)]:
        errors.append("Missing or mismatched embedded Rust standard-library inventory")
    return tuple(errors)


def packaged_proofs(entry: Dependency) -> tuple[Proof, ...]:
    return tuple(
        proof
        for proof in entry.proofs
        if proof.role != ProofRole.LOCK
        and Path(proof.member or urlsplit(proof.url).path).suffix.lower()
        not in {".rs", ".toml", ".json", ".svg"}
    )


def packaged_path(proof: Proof) -> str:
    return "licenses/third-party/" + Path(proof.path).name


def expected_files(repo: Path, inventory: Inventory) -> tuple[str, ...]:
    # Public legal materials are independent of the private audit corpus.
    names = {"LICENSE", NOTICE}
    names.update(
        path.relative_to(repo).as_posix() for path in (repo / "licenses/third-party").glob("*.txt")
    )
    return tuple(sorted(names))


def archive_contents(path: Path, wheel: bool) -> tuple[str, dict[str, bytes]]:
    if wheel:
        with ZipFile(path) as archive:
            names = archive.namelist()
            if len(names) != len(set(names)):
                raise ValueError("Duplicate wheel archive members")
            roots = [n.removesuffix("METADATA") for n in names if n.endswith(".dist-info/METADATA")]
            if len(roots) != 1:
                raise ValueError("Wheel metadata is not unique")
            return roots[0] + "licenses/", {
                n: archive.read(n) for n in names if not n.endswith("/")
            }
    with tarfile.open(path) as archive:
        members = archive.getmembers()
        if len(members) != len({m.name for m in members}):
            raise ValueError("Duplicate sdist archive members")
        contents: dict[str, bytes] = {}
        for member in members:
            if member.issym() or member.islnk():
                raise ValueError("License archive contains links")
            if member.isfile():
                stream = archive.extractfile(member)
                if stream is not None:
                    contents[member.name] = stream.read()
        sdist_roots = {PurePosixPath(n).parts[0] for n in contents}
        if len(sdist_roots) != 1:
            raise ValueError("sdist root is not unique")
        return sdist_roots.pop() + "/", contents


@dataclass(frozen=True, slots=True)
class CargoTarget:
    kind: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CargoPackage:
    id: str
    name: str
    version: str
    source: str | None
    targets: tuple[CargoTarget, ...]


@dataclass(frozen=True, slots=True)
class CargoKind:
    kind: str | None


@dataclass(frozen=True, slots=True)
class CargoEdge:
    pkg: str
    dep_kinds: tuple[CargoKind, ...]


@dataclass(frozen=True, slots=True)
class CargoNode:
    id: str
    deps: tuple[CargoEdge, ...]
    features: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CargoResolve:
    root: str
    nodes: tuple[CargoNode, ...]


@dataclass(frozen=True, slots=True)
class CargoMetadata:
    packages: tuple[CargoPackage, ...]
    resolve: CargoResolve


@dataclass(frozen=True, slots=True)
class BuildGraph:
    runtime: frozenset[tuple[str, str]]
    build: frozenset[tuple[str, str]]
    sha256: str


CARGO_ADAPTER = TypeAdapter(CargoMetadata)


def graph_file(artifact: Path, target: str) -> Path:
    return artifact.parent.parent / "licenses" / f"{target}.cargo.json"


def capture_graph(repo: Path, target: str, path: Path) -> None:
    from scripts.artifacts import Targets

    targets = Targets.model_validate_json((repo / ".github/release-targets.json").read_bytes())
    selected = next(t for t in targets.wheels if t.id == target)
    config = tomllib.loads((repo / "pyproject.toml").read_text())["tool"]["maturin"]
    command = [
        "cargo",
        "metadata",
        "--locked",
        "--offline",
        "--format-version",
        "1",
        "--manifest-path",
        str(repo / "datasift-core/Cargo.toml"),
        "--filter-platform",
        selected.rust_target,
    ]
    if config.get("features"):
        command.extend(["--features", ",".join(config["features"])])
    if config.get("no-default-features", False):
        command.append("--no-default-features")
    if config.get("all-features", False):
        command.append("--all-features")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(subprocess.check_output(command, cwd=repo))


def resolve_graph(repo: Path, target: str, path: Path) -> BuildGraph:
    if path.is_symlink():
        raise ValueError("Resolved Cargo graph must not be a symlink")
    if not path.is_file():
        capture_graph(repo, target, path)
    content = path.read_bytes()
    metadata = CARGO_ADAPTER.validate_json(content)
    packages = {p.id: p for p in metadata.packages}
    nodes = {n.id: n for n in metadata.resolve.nodes}
    pending = [(metadata.resolve.root, False)]
    visited: set[tuple[str, bool]] = set()
    runtime: set[tuple[str, str]] = set()
    build: set[tuple[str, str]] = set()
    while pending:
        identifier, host = pending.pop()
        if (identifier, host) in visited:
            continue
        visited.add((identifier, host))
        package = packages[identifier]
        host = host or any("proc-macro" in t.kind for t in package.targets)
        if identifier != metadata.resolve.root:
            (build if host else runtime).add((package.name, package.version))
        for edge in nodes[identifier].deps:
            pending.extend(
                (edge.pkg, host or kind.kind == "build")
                for kind in edge.dep_kinds
                if kind.kind != "dev"
            )
    return BuildGraph(frozenset(runtime), frozenset(build), sha256(content))


def scope_for(entry: Dependency, target: str, graph: BuildGraph | None) -> Scope:
    uses = {category for use in entry.usage if use.target == target for category in use.categories}
    if entry.ecosystem == Ecosystem.CARGO:
        identity = entry.name, entry.version
        if graph is not None and identity in graph.runtime:
            return Scope.DISTRIBUTED
        if (graph is not None and identity in graph.build) or target == "sdist":
            return Scope.BUILD
        return Scope.UNUSED
    if entry.ecosystem == Ecosystem.TOOLCHAIN and entry.name == "rust-std":
        return Scope.DISTRIBUTED if graph is not None else Scope.UNUSED
    if entry.ecosystem == Ecosystem.SYSTEM:
        return Scope.SYSTEM if Use.EXTERNAL in uses else Scope.UNUSED
    categories = (
        (Use.EXTERNAL, Scope.EXTERNAL_RUNTIME),
        (Use.DEV, Scope.DEV),
        (Use.BUILD, Scope.BUILD),
    )
    return next((scope for use, scope in categories if use in uses), Scope.UNUSED)


def native_findings(
    contents: dict[str, bytes], inventory: Inventory, target: str
) -> tuple[NativeImports | None, tuple[str, ...]]:
    errors: list[str] = []
    imports = None
    natives = [
        b
        for n, b in contents.items()
        if n.startswith("chooong/datasift/rust.") and n.endswith((".so", ".pyd"))
    ]
    if len(natives) != 1:
        errors.append("Native extension is missing or duplicated")
    else:
        try:
            imports = inspect_native(natives[0])
        except (ValueError, UnicodeError, struct.error) as error:
            errors.append(str(error))
    bundled = [
        n
        for n in contents
        if n.endswith((".so", ".dll", ".dylib", ".pyd"))
        and not n.startswith("chooong/datasift/rust.")
    ]
    if bundled:
        errors.append("Uninventoried bundled native libraries: " + ", ".join(bundled))
    foreign_python = [
        name
        for name in contents
        if name.endswith(".py") and not name.startswith("chooong/datasift/")
    ]
    if foreign_python:
        errors.append("Uninventoried bundled Python modules: " + ", ".join(foreign_python))
    return imports, tuple(errors)


def component_findings(
    inventory: Inventory,
    repo: Path,
    target: str,
    graph: BuildGraph | None,
    prefix: str,
    contents: dict[str, bytes],
) -> tuple[tuple[ComponentResult, ...], tuple[str, ...]]:
    errors: list[str] = []
    components: list[ComponentResult] = []
    checked: set[tuple[str, str]] = set()
    for entry in inventory.dependencies:
        scope = scope_for(entry, target, graph)
        if scope != Scope.DISTRIBUTED:
            components.append(
                ComponentResult(
                    entry.identifier,
                    target,
                    Status.NOT_DISTRIBUTED,
                    (f"{scope.value}: no component code is redistributed in this artifact",),
                    scope,
                )
            )
            continue
        checked.add((entry.name, entry.version))
        reasons = list(component_errors(entry, repo))
        reasons.extend(
            f"Missing or changed required license/NOTICE: {packaged_path(proof)}"
            for proof in packaged_proofs(entry)
            if sha256(contents.get(prefix + packaged_path(proof), b"")) != proof.sha256
        )
        components.append(
            ComponentResult(
                entry.identifier,
                target,
                Status.FAIL if reasons else Status.PASS,
                tuple(reasons),
                scope,
            )
        )
    if graph is not None and graph.runtime - checked:
        errors.append(
            "Uninventoried redistributed Rust dependencies: " + str(sorted(graph.runtime - checked))
        )
    if any(c.status == Status.FAIL for c in components):
        errors.append("Unresolved redistributed dependency license obligations block release")
    return tuple(components), tuple(errors)


def audit_artifact(path: Path, repo: Path, target: str) -> ArtifactResult:
    inventory = read_inventory(repo)
    wheel = path.suffix == ".whl"
    errors = list(inventory_errors(repo, inventory))
    if target not in {*inventory.targets, "sdist"}:
        errors.append("Unsupported license release target")
    graph = resolve_graph(repo, target, graph_file(path, target)) if wheel else None
    prefix, contents = archive_contents(path, wheel)
    if any("compliance" in PurePosixPath(name).parts for name in contents):
        errors.append("Internal compliance data must not be distributed")
    metadata_path = prefix.removesuffix("licenses/") + "METADATA" if wheel else prefix + "PKG-INFO"
    metadata = BytesParser().parsebytes(contents.get(metadata_path, b""))
    declared_files = metadata.get_all("License-File", [])
    expected = expected_files(repo, inventory)
    if set(declared_files) != set(expected) or len(declared_files) != len(expected):
        errors.append("Missing, duplicate or unexpected License-File metadata")
    errors.extend(
        f"Missing or changed packaged license evidence: {name}"
        for name in expected_files(repo, inventory)
        if not safe_path(repo, name).is_file()
        or contents.get(prefix + name) != safe_path(repo, name).read_bytes()
    )
    imports = None
    if wheel:
        imports, native_errors = native_findings(contents, inventory, target)
        errors.extend(native_errors)
    components, component_issues = component_findings(
        inventory, repo, target, graph, prefix, contents
    )
    errors.extend(component_issues)
    return ArtifactResult(
        path.name,
        sha256(path.read_bytes()),
        target,
        Status.FAIL if errors else Status.PASS,
        tuple(errors),
        imports,
        components,
        graph.sha256 if graph is not None else None,
        tuple(str(value) for value in metadata.get_all("Requires-Dist", [])),
        tuple(f"{name}@{version}" for name, version in sorted(graph.build))
        if graph is not None
        else (),
    )


def require_artifact(path: Path, repo: Path, target: str) -> None:
    report = audit_artifact(path, repo, target)
    if report.status != Status.PASS:
        raise ValueError("License gate FAIL: " + "; ".join(report.errors))


def source_archive(origin: Origin, cache: Path, fetch: bool) -> Path:
    if not re.fullmatch(r"[0-9a-f]{64}", origin.sha256):
        raise ValueError("Invalid upstream source digest")
    source = cache / origin.sha256
    if source.is_symlink():
        raise ValueError("Upstream source cache must not contain symlinks")
    if not source.exists() and fetch:
        if urlsplit(origin.url).scheme != "https":
            raise ValueError("Upstream evidence must use HTTPS")
        with urlopen(origin.url, timeout=60) as response:
            source.write_bytes(response.read())
    if not source.is_file() or sha256(source.read_bytes()) != origin.sha256:
        raise ValueError(f"Missing or untrusted upstream source: {origin.url}")
    return source


def source_member(source: Path, member: str | None) -> bytes:
    if member is None:
        return source.read_bytes()
    if is_zipfile(source):
        with ZipFile(source) as archive:
            return archive.read(member)
    with tarfile.open(source) as archive:
        stream = archive.extractfile(member)
        if stream is None:
            raise ValueError("Missing original license member")
        return stream.read()


def verify_sources(inventory: Inventory, cache: Path, fetch: bool) -> None:
    cache.mkdir(parents=True, exist_ok=True)
    origins = {
        e.source_sha256: Origin(e.source, e.source_sha256)
        for e in inventory.dependencies
        if e.ecosystem != Ecosystem.SYSTEM
    }
    origins.update(
        {
            p.source_sha256: Origin(p.url, p.source_sha256)
            for e in inventory.dependencies
            for p in e.proofs
        }
    )
    with ThreadPoolExecutor(max_workers=8) as executor:
        # Each content-addressed destination has exactly one writer.
        results = executor.map(
            lambda origin: source_archive(origin, cache, fetch), origins.values()
        )
        for _ in results:
            pass
    checked: set[tuple[str, str, str | None]] = set()
    for entry in inventory.dependencies:
        for proof in entry.proofs:
            key = proof.url, proof.source_sha256, proof.member
            if key in checked:
                continue
            checked.add(key)
            source = cache / proof.source_sha256
            if sha256(source_member(source, proof.member)) != proof.sha256:
                raise ValueError(f"Upstream license bytes differ: {proof.path}")


def write_audit(paths: tuple[Path, ...], repo: Path, output: Path) -> Audit:
    artifacts: list[ArtifactResult] = []
    for path in paths:
        target = "sdist"
        if path.suffix == ".whl":
            from scripts.artifacts import Targets

            targets = Targets.model_validate_json(
                (repo / ".github/release-targets.json").read_bytes()
            )
            matches = [t.id for t in targets.wheels if path.name.endswith(t.platform_tag + ".whl")]
            if len(matches) != 1:
                raise ValueError("Wheel has no unique supported release target")
            target = matches[0]
        artifacts.append(audit_artifact(path, repo, target))
    status = (
        Status.PASS
        if artifacts and all(a.status == Status.PASS for a in artifacts)
        else Status.FAIL
    )
    result = Audit(1, sha256((repo / INVENTORY).read_bytes()), status, tuple(artifacts))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(AUDIT_ADAPTER.dump_json(result, indent=2) + b"\n")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("audit", "verify-sources"))
    parser.add_argument("--repo", type=Path, default=REPO)
    parser.add_argument("--dist", type=Path, default=Path("dist"))
    parser.add_argument("--output", type=Path, default=Path("license-audit.json"))
    parser.add_argument("--cache", type=Path, default=Path(".cache/license-sources"))
    parser.add_argument("--fetch", action="store_true")
    args = parser.parse_args()
    if args.command == "verify-sources":
        verify_sources(read_inventory(args.repo), args.cache, args.fetch)
    else:
        paths = tuple(sorted((*args.dist.glob("*.whl"), *args.dist.glob("*.tar.gz"))))
        result = write_audit(paths, args.repo, args.output)
        sys.stdout.write(f"License audit {result.status}: {len(result.artifacts)} artifacts\n")
        if result.status != Status.PASS:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
