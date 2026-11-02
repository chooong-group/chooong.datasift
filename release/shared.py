"""Version source, Git checks and release notes shared by the two entry points."""

import json
import re
import subprocess
import tomllib
from dataclasses import dataclass
from http import HTTPStatus
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

from packaging.version import Version
from pydantic import BaseModel, ConfigDict

from scripts.artifacts import CargoFile, ProjectFile

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "chooong-group/chooong.datasift"
RELEASE_FILES = (
    "pyproject.toml",
    "datasift-core/Cargo.toml",
    "datasift-core/Cargo.lock",
    "uv.lock",
    "CHANGELOG.md",
)


class _Index(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)
    releases: dict[str, object]


class LockedPackage(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)
    name: str
    version: str


class Lockfile(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)
    package: tuple[LockedPackage, ...]


@dataclass(frozen=True, slots=True)
class FileChange:
    path: Path
    before: str
    after: str


@dataclass(frozen=True, slots=True)
class Plan:
    version: str
    changes: tuple[FileChange, ...]


def run(repo: Path, *command: str) -> str:
    return subprocess.check_output(list(command), cwd=repo, text=True).strip()


def git(repo: Path, *args: str) -> str:
    return run(repo, "git", *args)


def current_version(repo: Path) -> str:
    return ProjectFile.model_validate(
        tomllib.loads((repo / "pyproject.toml").read_text())
    ).project.version


def validate_version(value: str) -> str:
    version = Version(value)
    if not re.fullmatch(r"\d+\.\d+\.\d+", value) or str(version) != value:
        raise ValueError("Release preparation supports canonical final PEP 440 X.Y.Z versions")
    return value


def published_versions() -> frozenset[Version]:
    try:
        with urlopen("https://pypi.org/pypi/chooong.datasift/json", timeout=30) as response:
            index = _Index.model_validate_json(response.read())
    except HTTPError as error:
        if error.code == HTTPStatus.NOT_FOUND:
            return frozenset()
        raise
    return frozenset(Version(value) for value in index.releases)


def changed_paths(repo: Path) -> set[str]:
    tracked = git(repo, "diff", "--name-only", "HEAD").splitlines()
    untracked = git(repo, "ls-files", "--others", "--exclude-standard").splitlines()
    return set(tracked) | set(untracked)


def release_notes(repo: Path, version: str) -> str:
    text = (repo / "CHANGELOG.md").read_text(encoding="utf-8")
    heading = f"## {version}\n"
    if text.count(heading) != 1:
        raise ValueError("Prepare exactly one changelog section for this release first")
    notes = text.split(heading, 1)[1].split("\n## ", 1)[0].strip()
    if not notes:
        raise ValueError("Release notes must not be empty")
    return notes


def verify_prepared(repo: Path, version: str) -> None:
    if current_version(repo) != version:
        raise ValueError("Project version differs from the prepared release")
    cargo = CargoFile.model_validate(tomllib.loads((repo / "datasift-core/Cargo.toml").read_text()))
    if cargo.package.version != version:
        raise ValueError("Cargo version differs from the prepared release")
    for name, package in (
        ("uv.lock", "chooong-datasift"),
        ("datasift-core/Cargo.lock", "datasift-core"),
    ):
        lock = Lockfile.model_validate(tomllib.loads((repo / name).read_text()))
        entries = [entry for entry in lock.package if entry.name == package]
        if len(entries) != 1 or entries[0].version != version:
            raise ValueError(f"{name} is not synchronized")
    release_notes(repo, version)


def version_change(path: Path, section: str, version: str) -> FileChange:
    before = path.read_text(encoding="utf-8")
    pattern = rf'(\[{re.escape(section)}\]\n(?:(?!\n\[).)*?\nversion = )"[^"]+"'
    compiled: re.Pattern[str] = re.compile(pattern, re.S)
    after, count = compiled.subn(lambda match: match.group(1) + json.dumps(version), before)
    if count != 1:
        raise ValueError(f"Cannot identify one version field in {path.name}")
    return FileChange(path, before, after)


def lock_change(path: Path, package: str, version: str) -> FileChange:
    before = path.read_text(encoding="utf-8")
    pattern = rf'(\[\[package\]\]\nname = "{re.escape(package)}"\nversion = )"[^"]+"'
    compiled: re.Pattern[str] = re.compile(pattern)
    after, count = compiled.subn(lambda match: match.group(1) + json.dumps(version), before)
    if count != 1:
        raise ValueError(f"Cannot identify the project entry in {path.name}")
    return FileChange(path, before, after)
