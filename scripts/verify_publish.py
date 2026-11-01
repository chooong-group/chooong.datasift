"""Recheck authenticated SHA256SUMS without installing code in an OIDC-enabled job."""

import argparse
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class FileDigest:
    sha256: str
    filename: str

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[0-9a-f]{64}", self.sha256):
            raise ValueError("Invalid SHA-256")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.+-]*", self.filename):
            raise ValueError("Unsafe distribution filename")


def digest(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def verify(directory: Path, expected: str) -> None:
    checksums = directory / "SHA256SUMS"
    if checksums.is_symlink() or digest(checksums) != expected:
        raise ValueError("Checksum manifest does not match the gate output")
    records: list[FileDigest] = []
    for line in checksums.read_text().splitlines():
        sha256, filename = line.split("  ", 1)
        records.append(FileDigest(sha256=sha256, filename=filename))
    if not records or len({record.filename for record in records}) != len(records):
        raise ValueError("Empty or duplicate checksum records")
    files = tuple((directory / "dist").iterdir())
    if {path.name for path in files} != {record.filename for record in records}:
        raise ValueError("Unexpected or missing distribution")
    for record in records:
        path = directory / "dist" / record.filename
        if path.is_symlink() or digest(path) != record.sha256:
            raise ValueError("Distribution changed after final tests")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("checksums_sha256")
    args = parser.parse_args()
    verify(args.directory, args.checksums_sha256)


if __name__ == "__main__":
    main()
