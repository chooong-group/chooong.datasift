"""Synthetic licensing evidence for release-gate unit tests, never release approval."""

from dataclasses import replace
from pathlib import Path

from scripts.licenses import (
    CARGO_ADAPTER,
    INVENTORY,
    INVENTORY_ADAPTER,
    NOTICE,
    CargoEdge,
    CargoKind,
    CargoMetadata,
    CargoNode,
    CargoPackage,
    CargoResolve,
    CargoTarget,
    Dependency,
    Ecosystem,
    Inventory,
    LockBinding,
    Proof,
    ProofRole,
    Status,
    graph_file,
    packaged_path,
    read_inventory,
    sha256,
)


def synthetic_licenses(repo: Path, source: Path) -> None:
    inventory = read_inventory(source)
    license_bytes = (repo / "LICENSE").read_bytes()
    proof_path = "compliance/texts/" + sha256(license_bytes) + ".txt"
    (repo / proof_path).parent.mkdir(parents=True, exist_ok=True)
    (repo / proof_path).write_bytes(license_bytes)
    dependencies: list[Dependency] = []
    for entry in inventory.dependencies:
        if entry.ecosystem not in {
            Ecosystem.CARGO,
            Ecosystem.PYTHON,
            Ecosystem.BUILD,
            Ecosystem.TOOLCHAIN,
        }:
            continue
        proof = Proof(
            proof_path,
            sha256(license_bytes),
            entry.source,
            entry.source_sha256,
            None,
            ProofRole.LICENSE,
        )
        proofs = (proof,)
        public = repo / packaged_path(proof)
        public.parent.mkdir(parents=True, exist_ok=True)
        public.write_bytes(license_bytes)
        dependencies.append(
            replace(
                entry,
                declared_license="Apache-2.0",
                selected_license="Apache-2.0",
                copyright=("Synthetic fixture, not upstream authorship",),
                proofs=proofs,
                status=Status.PASS,
                rationale="Synthetic gate fixture; never native/license acceptance",
                blockers=(),
            )
        )
    result = Inventory(
        1,
        inventory.project_version,
        tuple(LockBinding(b.path, sha256((repo / b.path).read_bytes())) for b in inventory.locks),
        inventory.targets,
        tuple(dependencies),
    )
    (repo / INVENTORY).write_bytes(INVENTORY_ADAPTER.dump_json(result, indent=2))
    (repo / NOTICE).write_text("Synthetic test notices, not a real distribution license audit.\n")


def synthetic_graph(artifact: Path, target: str, inventory: Inventory) -> Path:
    packages = [
        CargoPackage(
            "root", "datasift-core", inventory.project_version, None, (CargoTarget(("cdylib",)),)
        )
    ]
    nodes: list[CargoNode] = []
    edges: list[CargoEdge] = []
    for entry in inventory.dependencies:
        if entry.ecosystem != Ecosystem.CARGO:
            continue
        identifier = entry.identifier
        packages.append(
            CargoPackage(
                identifier,
                entry.name,
                entry.version,
                "registry+https://github.com/rust-lang/crates.io-index",
                (CargoTarget(("lib",)),),
            )
        )
        nodes.append(CargoNode(identifier, (), ()))
        edges.append(CargoEdge(identifier, (CargoKind(None),)))
    nodes.append(CargoNode("root", tuple(edges), ()))
    metadata = CargoMetadata(tuple(packages), CargoResolve("root", tuple(nodes)))
    path = graph_file(artifact, target)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(CARGO_ADAPTER.dump_json(metadata))
    return path


def synthetic_native(system: str) -> bytes:
    data = bytearray(512)
    if system == "Darwin":
        data[:4] = bytes.fromhex("cffaedfe")
        return bytes(data)
    if system == "Windows":
        data[:2] = b"MZ"
        data[0x3C:0x40] = (128).to_bytes(4, "little")
        data[128:132] = b"PE\0\0"
        data[152:154] = (0x20B).to_bytes(2, "little")
        return bytes(data)
    data[:6] = b"\x7fELF\x02\x01"
    data[32:40] = (64).to_bytes(8, "little")
    data[54:56] = (56).to_bytes(2, "little")
    data[56:58] = (2).to_bytes(2, "little")
    data[64:68] = (1).to_bytes(4, "little")
    data[96:104] = (512).to_bytes(8, "little")
    data[120:124] = (2).to_bytes(4, "little")
    data[128:136] = (176).to_bytes(8, "little")
    data[152:160] = (32).to_bytes(8, "little")
    data[176:184] = (5).to_bytes(8, "little")
    data[184:192] = (208).to_bytes(8, "little")
    return bytes(data)
