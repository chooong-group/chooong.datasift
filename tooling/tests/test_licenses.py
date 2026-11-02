"""License gate tests use synthetic fixtures; none approve upstream or native builds."""

import io
import json
import tarfile
from dataclasses import replace
from pathlib import Path, PureWindowsPath
from unittest.mock import patch
from zipfile import ZipFile

import pytest
from pydantic import ValidationError

from scripts.license_binary import inspect_native
from scripts.licenses import (
    BuildGraph,
    Ecosystem,
    Scope,
    Status,
    Usage,
    Use,
    audit_artifact,
    component_errors,
    inventory_errors,
    native_findings,
    read_inventory,
    scope_for,
    selection_valid,
    sha256,
    verify_sources,
)
from tooling.tests.fixtures import SyntheticBundle
from tooling.tests.license_fixtures import synthetic_native


@pytest.mark.parametrize(
    ("declared", "chosen", "valid"),
    [
        ("MIT OR LGPL-2.1-or-later", "MIT", True),
        ("(MIT OR Apache-2.0) AND Unicode-3.0", "MIT AND Unicode-3.0", True),
        ("(MIT OR Apache-2.0) AND Unicode-3.0", "MIT", False),
        ("Apache-2.0 WITH LLVM-exception", "Apache-2.0", False),
        ("Apache-2.0 WITH LLVM-exception", "Apache-2.0 WITH LLVM-exception", True),
        ("MIT", "MIT AND BSD-3-Clause", False),
        ("MIT OR Apache-2.0", "MIT OR Apache-2.0", False),
        ("Apache-2.0 AND MIT", "MIT", False),
    ],
)
def test_spdx_choices_preserve_and_obligations_and_exceptions(
    declared: str,
    chosen: str,
    valid: bool,
) -> None:
    assert selection_valid(declared, chosen) is valid


@pytest.mark.parametrize("system", ["Darwin", "Linux", "Windows"])
def test_native_import_readers_do_not_execute_binaries(system: str) -> None:
    result = inspect_native(synthetic_native(system))
    assert result.libraries == ()
    with pytest.raises((ValueError, IndexError)):
        inspect_native(b"not a native extension")


def test_external_native_import_is_reported_without_claiming_redistribution(
    release_checkout: Path,
) -> None:
    data = bytearray(synthetic_native("Darwin"))
    data[16:20] = (1).to_bytes(4, "little")
    data[32:36] = (12).to_bytes(4, "little")
    data[36:40] = (48).to_bytes(4, "little")
    data[40:44] = (24).to_bytes(4, "little")
    data[56:72] = b"unreviewed.dylib\0"
    imports, errors = native_findings(
        {"chooong/datasift/rust.abi3.so": bytes(data)},
        read_inventory(release_checkout),
        "macos-arm64",
    )
    assert imports is not None
    assert imports.libraries == ("unreviewed.dylib",)
    assert errors == ()  # An import is not evidence of redistributing the referenced library.


def test_inventory_unknown_fields_are_rejected(release_checkout: Path) -> None:
    payload = json.loads((release_checkout / "compliance/inventory.json").read_text())
    payload["dependencies"][0]["approve_unknown_terms"] = True
    (release_checkout / "compliance/inventory.json").write_text(json.dumps(payload))
    with pytest.raises(ValidationError, match="unexpected_keyword_argument"):
        read_inventory(release_checkout)


@pytest.mark.parametrize(
    "expression",
    [
        "GPL-3.0-only",
        "AGPL-3.0-only",
        "LGPL-2.1-only",
        "MPL-2.0",
        "CDDL-1.0",
        "LicenseRef-Custom",
        "MIT WITH LLVM-exception",
    ],
)
def test_unapproved_static_licenses_are_not_blanket_approved(
    release_checkout: Path,
    expression: str,
) -> None:
    original = read_inventory(release_checkout).dependencies[0]
    entry = replace(
        original, declared_license=expression, selected_license=expression, redistributed=True
    )
    assert any(
        "requires review" in reason or "invalid SPDX" in reason
        for reason in component_errors(entry, release_checkout)
    )


def test_actual_graph_overrides_global_distribution_flag(release_checkout: Path) -> None:
    original = read_inventory(release_checkout).dependencies[0]
    graph = BuildGraph(frozenset({(original.name, original.version)}), frozenset(), "0" * 64)
    tool = replace(
        original,
        declared_license="MPL-2.0",
        selected_license="MPL-2.0",
        redistributed=False,
        usage=(Usage("linux-x86_64", (Use.DEV,)),),
    )
    assert scope_for(tool, "linux-x86_64", graph) == Scope.DISTRIBUTED
    assert component_errors(tool, release_checkout)


def test_unknown_assessments_and_stale_or_incomplete_locks_block(release_checkout: Path) -> None:
    inventory = read_inventory(release_checkout)
    assert inventory_errors(release_checkout, inventory) == ()
    assert component_errors(
        replace(inventory.dependencies[0], status=Status.FAIL), release_checkout
    )
    missing = replace(inventory, dependencies=inventory.dependencies[1:])
    assert inventory_errors(release_checkout, missing) == ()
    # A lockfile-only entry is not automatically redistributed. Runtime graph coverage
    # is checked separately when the actual wheel is inspected.
    with (release_checkout / "datasift-core/Cargo.lock").open("a") as handle:
        handle.write("\n# changed input\n")
    assert any("stale" in error for error in inventory_errors(release_checkout, inventory))


def test_external_python_native_dependency_is_not_embedded(release_checkout: Path) -> None:
    original = read_inventory(release_checkout).dependencies[0]
    entry = replace(
        original,
        ecosystem=Ecosystem.PYTHON,
        name="pydantic-core",
        usage=tuple(Usage(t, (Use.EXTERNAL,)) for t in read_inventory(release_checkout).targets),
    )
    graph = BuildGraph(frozenset(), frozenset(), "0" * 64)
    assert scope_for(entry, "linux-x86_64", graph) == Scope.EXTERNAL_RUNTIME


@pytest.mark.parametrize("change", ["missing", "changed", "metadata", "extra_library", "duplicate"])
def test_wheel_license_bytes_and_metadata_are_checked_inside_archive(
    synthetic_bundle: SyntheticBundle,
    change: str,
) -> None:
    bundle = synthetic_bundle
    artifact = next((bundle.root / "dist").glob("*macosx_11_0_arm64.whl"))
    assert audit_artifact(artifact, bundle.repo, "macos-arm64").status == Status.PASS
    with ZipFile(artifact) as archive:
        contents = {n: archive.read(n) for n in archive.namelist()}
    notice = next(n for n in contents if n.endswith("/licenses/THIRD_PARTY_NOTICES.txt"))
    if change == "missing":
        del contents[notice]
    elif change == "changed":
        contents[notice] += b"changed"
    elif change == "metadata":
        metadata = next(n for n in contents if n.endswith("/METADATA"))
        contents[metadata] = contents[metadata].replace(b"License-File:", b"Unreviewed-File:")
    elif change == "extra_library":
        contents["chooong/datasift/unreviewed.dylib"] = b"unreviewed binary"
    with ZipFile(artifact, "w") as archive:
        for name, data in contents.items():
            archive.writestr(name, data)
        if change == "duplicate":
            with pytest.warns(UserWarning, match="Duplicate name"):
                archive.writestr(notice, contents[notice])
    if change == "duplicate":
        with pytest.raises(ValueError, match="Duplicate"):
            audit_artifact(artifact, bundle.repo, "macos-arm64")
    else:
        assert audit_artifact(artifact, bundle.repo, "macos-arm64").status == Status.FAIL


def test_sdist_checks_packaged_notices(synthetic_bundle: SyntheticBundle) -> None:
    bundle = synthetic_bundle
    artifact = next((bundle.root / "dist").glob("*.tar.gz"))
    assert audit_artifact(artifact, bundle.repo, "sdist").status == Status.PASS
    with tarfile.open(artifact) as archive:
        contents = [(m, archive.extractfile(m).read()) for m in archive.getmembers() if m.isfile()]
    with tarfile.open(artifact, "w:gz") as archive:
        for member, data in contents:
            if not member.name.endswith("/THIRD_PARTY_NOTICES.txt"):
                archive.addfile(member, io.BytesIO(data))
    assert audit_artifact(artifact, bundle.repo, "sdist").status == Status.FAIL


def test_original_sources_are_replayed_by_hash_without_network(
    release_checkout: Path,
    tmp_path: Path,
) -> None:
    inventory = read_inventory(release_checkout)
    entry = inventory.dependencies[0]
    proof = entry.proofs[0]
    data = (release_checkout / proof.path).read_bytes()
    replay = replace(proof, source_sha256=sha256(data), member=None)
    sample = replace(
        inventory, dependencies=(replace(entry, source_sha256=sha256(data), proofs=(replay,)),)
    )
    (tmp_path / sha256(data)).write_bytes(data)
    verify_sources(sample, tmp_path, False)
    (tmp_path / sha256(data)).write_bytes(b"tampered archive")
    with pytest.raises(ValueError, match="untrusted upstream source"):
        verify_sources(sample, tmp_path, False)


def test_foreign_platform_and_host_dependencies_do_not_block(
    synthetic_bundle: SyntheticBundle,
) -> None:
    from scripts.licenses import CARGO_ADAPTER, INVENTORY_ADAPTER, Scope

    bundle = synthetic_bundle
    inventory = read_inventory(bundle.repo)
    artifact = next((bundle.root / "dist").glob("*manylinux_2_28_x86_64.whl"))
    path = artifact.parent.parent / "licenses/linux-x86_64.cargo.json"
    graph = CARGO_ADAPTER.validate_json(path.read_bytes())
    selected = [e for e in inventory.dependencies if e.ecosystem == Ecosystem.CARGO][:3]
    foreign, host, macro = selected
    bad = {e.identifier for e in selected}
    inventory = replace(
        inventory,
        dependencies=tuple(
            replace(e, status=Status.FAIL, blockers=("unresolved test license",))
            if e.identifier in bad
            else e
            for e in inventory.dependencies
        ),
    )
    (bundle.repo / "compliance/inventory.json").write_bytes(INVENTORY_ADAPTER.dump_json(inventory))
    root = next(n for n in graph.resolve.nodes if n.id == graph.resolve.root)
    from scripts.licenses import CargoKind, CargoTarget

    root = replace(
        root,
        deps=tuple(
            replace(edge, dep_kinds=(CargoKind("build"),)) if edge.pkg == host.identifier else edge
            for edge in root.deps
            if edge.pkg != foreign.identifier
        ),
    )
    graph = replace(
        graph,
        packages=tuple(
            replace(p, targets=(CargoTarget(("proc-macro",)),)) if p.id == macro.identifier else p
            for p in graph.packages
        ),
        resolve=replace(
            graph.resolve, nodes=tuple(root if n.id == root.id else n for n in graph.resolve.nodes)
        ),
    )
    path.write_bytes(CARGO_ADAPTER.dump_json(graph))
    result = audit_artifact(artifact, bundle.repo, "linux-x86_64")
    assert result.status == Status.PASS
    results = {r.identifier: r for r in result.dependencies}
    assert results[foreign.identifier].scope == Scope.UNUSED
    assert results[host.identifier].scope == Scope.BUILD
    assert results[macro.identifier].scope == Scope.BUILD
    assert all(results[e.identifier].status == Status.NOT_DISTRIBUTED for e in selected)


def test_real_runtime_risk_blocks_even_when_inventory_claims_development_only(
    synthetic_bundle: SyntheticBundle,
) -> None:
    from scripts.licenses import INVENTORY_ADAPTER

    bundle = synthetic_bundle
    inventory = read_inventory(bundle.repo)
    entry = next(e for e in inventory.dependencies if e.ecosystem == Ecosystem.CARGO)
    bad = replace(
        entry,
        redistributed=False,
        status=Status.FAIL,
        usage=tuple(Usage(t, (Use.DEV,)) for t in inventory.targets),
        blockers=("Missing required upstream NOTICE",),
    )
    inventory = replace(
        inventory, dependencies=tuple(bad if e == entry else e for e in inventory.dependencies)
    )
    (bundle.repo / "compliance/inventory.json").write_bytes(INVENTORY_ADAPTER.dump_json(inventory))
    artifact = next((bundle.root / "dist").glob("*manylinux_2_28_x86_64.whl"))
    result = audit_artifact(artifact, bundle.repo, "linux-x86_64")
    assert result.status == Status.FAIL
    finding = next(r for r in result.dependencies if r.identifier == entry.identifier)
    assert finding.scope == Scope.DISTRIBUTED
    assert "Missing required upstream NOTICE" in finding.reasons


def test_external_python_build_tools_and_foreign_systems_are_informational(
    synthetic_bundle: SyntheticBundle,
) -> None:
    from scripts.licenses import INVENTORY_ADAPTER

    bundle = synthetic_bundle
    inventory = read_inventory(bundle.repo)
    source = next(e for e in inventory.dependencies if e.ecosystem == Ecosystem.CARGO)
    external = tuple(
        replace(
            source,
            name=name,
            ecosystem=ecosystem,
            status=Status.FAIL,
            declared_license="LicenseRef-Unknown",
            selected_license="LicenseRef-Unknown",
            proofs=(),
            copyright=(),
            blockers=("Not distributed; upstream terms were not assessed",),
            usage=tuple(Usage(t, (use,)) for t in inventory.targets),
        )
        for name, ecosystem, use in (
            ("pydantic-core", Ecosystem.PYTHON, Use.EXTERNAL),
            ("maturin", Ecosystem.BUILD, Use.BUILD),
            ("pytest", Ecosystem.PYTHON, Use.DEV),
        )
    )
    system = replace(
        source,
        name="kernel32.dll",
        ecosystem=Ecosystem.SYSTEM,
        status=Status.FAIL,
        proofs=(),
        copyright=(),
        usage=tuple(
            Usage(t, (Use.EXTERNAL,) if t.startswith("windows") else (Use.LOCKED,))
            for t in inventory.targets
        ),
    )
    inventory = replace(inventory, dependencies=(*inventory.dependencies, *external, system))
    (bundle.repo / "compliance/inventory.json").write_bytes(INVENTORY_ADAPTER.dump_json(inventory))
    artifact = next((bundle.root / "dist").glob("*manylinux_2_28_x86_64.whl"))
    result = audit_artifact(artifact, bundle.repo, "linux-x86_64")
    assert result.status == Status.PASS
    foreign = next(r for r in result.dependencies if r.identifier == system.identifier)
    assert foreign.scope == Scope.UNUSED
    assert foreign.status == Status.NOT_DISTRIBUTED
    assert all(r.status != Status.FAIL for r in result.dependencies)


def test_sdist_contains_no_internal_audit_data(synthetic_bundle: SyntheticBundle) -> None:
    artifact = next((synthetic_bundle.root / "dist").glob("*.tar.gz"))
    with tarfile.open(artifact) as archive:
        assert all("/compliance/" not in name for name in archive.getnames())
    result = audit_artifact(artifact, synthetic_bundle.repo, "sdist")
    assert result.status == Status.PASS
    assert all(r.status == Status.NOT_DISTRIBUTED for r in result.dependencies)


def test_reviewed_zlib_notice_has_the_actual_copyright() -> None:
    from scripts.licenses import REPO

    inventory = read_inventory(REPO)
    zlib = next(
        e
        for e in inventory.dependencies
        if e.ecosystem == Ecosystem.CARGO and e.name == "zlib-rs" and e.version == "0.6.8"
    )
    assert any("Trifecta Tech Foundation" in line for line in zlib.copyright)
    assert component_errors(zlib, REPO) == ()


def test_actual_notice_payload_excludes_internal_inventory(
    synthetic_bundle: SyntheticBundle,
) -> None:
    artifact = next((synthetic_bundle.root / "dist").glob("*macosx_11_0_arm64.whl"))
    with ZipFile(artifact) as archive:
        names = archive.namelist()
    assert not any("compliance/" in name for name in names)
    assert any("/licenses/licenses/third-party/" in name for name in names)
    assert any(name.endswith("/licenses/THIRD_PARTY_NOTICES.txt") for name in names)


def test_missing_notice_remains_blocking_when_metadata_omits_it(
    synthetic_bundle: SyntheticBundle,
) -> None:
    bundle = synthetic_bundle
    artifact = next((bundle.root / "dist").glob("*macosx_11_0_arm64.whl"))
    with ZipFile(artifact) as archive:
        contents = {n: archive.read(n) for n in archive.namelist()}
    proof = read_inventory(bundle.repo).dependencies[0].proofs[0]
    required = next(
        n for n in contents if n.endswith("/licenses/third-party/" + Path(proof.path).name)
    )
    del contents[required]
    metadata = next(n for n in contents if n.endswith("/METADATA"))
    contents[metadata] = b"\n".join(
        line
        for line in contents[metadata].split(b"\n")
        if not line.startswith(b"License-File: licenses/third-party/")
    )
    with ZipFile(artifact, "w") as archive:
        for name, content in contents.items():
            archive.writestr(name, content)
    report = audit_artifact(artifact, bundle.repo, "macos-arm64")
    assert report.status == Status.FAIL
    assert any(
        "required license/NOTICE" in reason
        for component in report.dependencies
        for reason in component.reasons
    )


def test_missing_actual_runtime_entry_blocks(synthetic_bundle: SyntheticBundle) -> None:
    from scripts.licenses import INVENTORY_ADAPTER

    bundle = synthetic_bundle
    inventory = read_inventory(bundle.repo)
    removed = next(e for e in inventory.dependencies if e.ecosystem == Ecosystem.CARGO)
    inventory = replace(
        inventory,
        dependencies=tuple(e for e in inventory.dependencies if e != removed),
    )
    (bundle.repo / "compliance/inventory.json").write_bytes(INVENTORY_ADAPTER.dump_json(inventory))
    artifact = next((bundle.root / "dist").glob("*manylinux_2_28_x86_64.whl"))
    result = audit_artifact(artifact, bundle.repo, "linux-x86_64")
    assert result.status == Status.FAIL
    assert any(
        "Uninventoried redistributed Rust" in error and removed.name in error
        for error in result.errors
    )


def test_copied_external_python_code_requires_review(synthetic_bundle: SyntheticBundle) -> None:
    artifact = next((synthetic_bundle.root / "dist").glob("*macosx_11_0_arm64.whl"))
    with ZipFile(artifact, "a") as archive:
        archive.writestr("foreign_package/__init__.py", "# Copied third-party code\n")
    result = audit_artifact(artifact, synthetic_bundle.repo, "macos-arm64")
    assert result.status == Status.FAIL
    assert any("Uninventoried bundled Python" in error for error in result.errors)


def test_windows_license_paths_use_portable_archive_names(release_checkout: Path) -> None:
    from scripts.licenses import expected_files

    inventory = read_inventory(release_checkout)
    windows_name = PureWindowsPath("licenses/third-party/original.txt")
    with patch.object(Path, "relative_to", return_value=windows_name):
        names = expected_files(release_checkout, inventory)
    assert names == ("LICENSE", "THIRD_PARTY_NOTICES.txt", "licenses/third-party/original.txt")
    assert all("\\" not in name for name in names)
