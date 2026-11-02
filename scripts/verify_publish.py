"""Recheck authenticated SHA256SUMS without installing code in an OIDC-enabled job."""

import argparse
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlopen


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


@dataclass(frozen=True, slots=True)
class PublishedFile:
    digest: FileDigest
    url: str


def published_files(content: bytes) -> tuple[PublishedFile, ...]:
    payload: object = json.loads(content)
    if not isinstance(payload, dict) or not isinstance(payload.get("urls"), list):
        raise ValueError("Invalid PyPI JSON response")
    result: list[PublishedFile] = []
    for entry in payload["urls"]:
        if not isinstance(entry, dict) or entry.get("yanked") is not False:
            raise ValueError("Missing or yanked publication")
        filename = entry.get("filename")
        url = entry.get("url")
        digests = entry.get("digests")
        if not isinstance(filename, str) or not isinstance(url, str):
            raise ValueError("Missing filename/download URL")
        if not isinstance(digests, dict) or not isinstance(digests.get("sha256"), str):
            raise ValueError("Missing published SHA-256")
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.netloc != "files.pythonhosted.org":
            raise ValueError("Unexpected PyPI download origin")
        result.append(PublishedFile(FileDigest(digests["sha256"], filename), url))
    if not result or len({item.digest.filename for item in result}) != len(result):
        raise ValueError("Empty or duplicate publication")
    return tuple(result)


def verify_pypi(directory: Path, expected: str, version: str) -> None:
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version):
        raise ValueError("Invalid release version")
    verify(directory, expected)
    with urlopen(f"https://pypi.org/pypi/chooong.datasift/{version}/json", timeout=30) as response:
        files = published_files(response.read())
    local = {path.name for path in (directory / "dist").iterdir()}
    if local != {item.digest.filename for item in files}:
        raise ValueError("PyPI has an incomplete or unexpected release file set")
    for item in files:
        if digest(directory / "dist" / item.digest.filename) != item.digest.sha256:
            raise ValueError("PyPI metadata differs from the validated artifact")
        with urlopen(item.url, timeout=60) as response:
            downloaded = hashlib.file_digest(response, "sha256").hexdigest()
        if downloaded != item.digest.sha256:
            raise ValueError("Published bytes differ from the validated artifact")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("checksums_sha256")
    parser.add_argument("--pypi-version")
    args = parser.parse_args()
    if args.pypi_version is None:
        verify(args.directory, args.checksums_sha256)
    else:
        verify_pypi(args.directory, args.checksums_sha256, args.pypi_version)


if __name__ == "__main__":
    main()
